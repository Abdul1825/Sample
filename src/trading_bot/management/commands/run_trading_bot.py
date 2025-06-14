import asyncio
import os
import json
from collections import deque
from decimal import Decimal, InvalidOperation
from django.core.management.base import BaseCommand
from django.conf import settings
from asgiref.sync import sync_to_async

from trading_bot.models import Signal
from trading_bot.live_data.binance_feed import listen_to_binance_ws_integrated
from trading_bot.ai_signal_generator import AISignalGenerator
from trading_bot.telegram_notifier import send_telegram_message, format_signal_to_message
from trading_bot.utils import (
    calculate_sma,
    update_price_history,
    calculate_rsi,
    calculate_macd,
    calculate_bollinger_bands
)
import csv
from datetime import datetime
import traceback

def save_signal_to_db(signal_data: dict):
    """Saves a signal dictionary to the Signal model in the database."""
    try:
        def to_decimal_or_none(value, precision='0.00000001'):
            if value is None: return None
            try:
                if isinstance(value, Decimal):
                    return value.quantize(Decimal(precision))
                return Decimal(str(value)).quantize(Decimal(precision))
            except (InvalidOperation, TypeError, ValueError) as e:
                print(f"Warning: DB Save - Could not convert '{value}' (type: {type(value)}) to Decimal. Storing as None. Error: {e}")
                return None

        def to_float_or_none(value):
            if value is None: return None
            try:
                return float(value)
            except (ValueError, TypeError):
                print(f"Warning: DB Save - Could not convert '{value}' to float. Storing as None.")
                return None

        signal_obj = Signal(
            symbol=signal_data.get('symbol'),
            signal_type=signal_data.get('signal_type'),
            price=to_decimal_or_none(signal_data.get('price')),

            ai_model=signal_data.get('ai_model'),
            ai_confidence_score=to_float_or_none(signal_data.get('confidence')),
            ai_reason=signal_data.get('reason'),
            suggested_stop_loss=to_decimal_or_none(signal_data.get('suggested_stop_loss')),
            suggested_take_profit=to_decimal_or_none(signal_data.get('suggested_take_profit')),

            sma_value=to_decimal_or_none(signal_data.get('sma')),
            rsi_value=to_decimal_or_none(signal_data.get('rsi'), precision='0.01'),

            macd_value=to_decimal_or_none(signal_data.get('macd_line')),
            macd_signal_value=to_decimal_or_none(signal_data.get('macd_signal')),
            macd_histogram_value=to_decimal_or_none(signal_data.get('macd_histogram')),

            bollinger_upper=to_decimal_or_none(signal_data.get('bb_upper')),
            bollinger_middle=to_decimal_or_none(signal_data.get('bb_middle')),
            bollinger_lower=to_decimal_or_none(signal_data.get('bb_lower')),

            # New consensus fields
            consensus_models_queried=to_int_or_none(signal_data.get('consensus_models_queried')),
            consensus_models_agreed=to_int_or_none(signal_data.get('consensus_models_agreed')),
            raw_ai_responses=signal_data.get('all_ai_responses') # Should be JSON-serializable (list of dicts)
        )
        signal_obj.save()
        # print(f"Successfully saved signal for {signal_data.get('symbol')} to database.") # Can be too verbose
    except Exception as e:
        print(f"Error saving signal to database: {e}")
        # It's helpful to see the data that caused the error
        print(f"Signal data that failed DB save: {{key: type(value).__name__ for key, value in signal_data.items()}}")
        traceback.print_exc()
        # Propagate failure for stats counting
        raise # This will be caught by the caller of sync_to_async if not handled there

save_signal_to_db_async = sync_to_async(save_signal_to_db, thread_sensitive=True)

async def process_binance_message_for_bot(
    msg, ai_generator, symbol,
    price_history_deque,
    sma_window, rsi_window, macd_short, macd_long, macd_signal_period, bb_window,
    recent_trend_len,
    signal_log_file_path,
    stats # Receive stats dictionary
):
    stats["messages_received"] += 1
    if not (msg and 'stream' in msg and 'data' in msg):
        stats["empty_or_error_ws_messages"] += 1
        return True

    data = msg['data']
    if data.get('e') == 'error':
        print(f"Error message from WebSocket: {data.get('m')}")
        stats["empty_or_error_ws_messages"] += 1
        return True

    current_price_str = data.get('c')
    if current_price_str: update_price_history(current_price_str, price_history_deque)
    else: print("Warning: No price in message."); stats["empty_or_error_ws_messages"] += 1; return True

    processed_data_for_ai = ai_generator.process_market_data_for_ai(data)
    if not processed_data_for_ai: stats["empty_or_error_ws_messages"] += 1; return True

    # Calculate indicators
    if sma_window > 0:
        sma = calculate_sma(price_history_deque, sma_window)
        if sma is not None: processed_data_for_ai['sma'] = f"{sma:.8f}"
    if rsi_window > 0:
        rsi = calculate_rsi(price_history_deque, rsi_window)
        if rsi is not None: processed_data_for_ai['rsi'] = f"{rsi:.2f}"
    if macd_long > 0:
        macd_results = calculate_macd(price_history_deque, macd_short, macd_long, macd_signal_period)
        if macd_results:
            if macd_results.get("macd") is not None: processed_data_for_ai['macd_line'] = f"{macd_results['macd']:.8f}"
            if macd_results.get("signal") is not None: processed_data_for_ai['macd_signal'] = f"{macd_results['signal']:.8f}"
            if macd_results.get("histogram") is not None: processed_data_for_ai['macd_histogram'] = f"{macd_results['histogram']:.8f}"
    if bb_window > 0:
        bbands = calculate_bollinger_bands(price_history_deque, bb_window)
        if bbands:
            if bbands.get("middle") is not None: processed_data_for_ai['bb_middle'] = f"{bbands['middle']:.8f}"
            if bbands.get("upper") is not None: processed_data_for_ai['bb_upper'] = f"{bbands['upper']:.8f}"
            if bbands.get("lower") is not None: processed_data_for_ai['bb_lower'] = f"{bbands['lower']:.8f}"
    if recent_trend_len > 0 and len(price_history_deque) >= recent_trend_len:
        trend_prices = list(price_history_deque)[-recent_trend_len:]
        processed_data_for_ai['recent_price_trend'] = [f"{p:.8f}" for p in trend_prices]

    stats["ai_total_queries"] += 1
    signal_dict_from_ai = await ai_generator.generate_signal(processed_data_for_ai)

    if signal_dict_from_ai:
        if signal_dict_from_ai.get('signal_type') == 'BUY': stats["signals_generated_buy"] += 1
        elif signal_dict_from_ai.get('signal_type') == 'SELL': stats["signals_generated_sell"] += 1

        final_signal_data_for_saving = processed_data_for_ai.copy(); final_signal_data_for_saving.update(signal_dict_from_ai)
        final_signal_data_for_saving['price'] = signal_dict_from_ai.get('price', current_price_str)

        print(f"Signal Generated: Type={final_signal_data_for_saving.get('signal_type')}, Price={final_signal_data_for_saving.get('price')}")

        try:
            await save_signal_to_db_async(final_signal_data_for_saving)
            stats["db_save_success"] += 1
            print(f"Signal for {symbol} saved to DB.")
        except Exception as e_db:
            print(f"DB Save Exception after successful signal generation: {e_db}")
            stats["db_save_failure"] += 1

        try:
            fieldnames = ['timestamp', 'symbol', 'signal_type', 'price', 'sma_value', 'rsi_value', 'macd_value', 'macd_signal_value', 'macd_histogram_value', 'bollinger_middle', 'bollinger_upper', 'bollinger_lower', 'ai_model', 'ai_confidence_score', 'ai_reason', 'suggested_stop_loss', 'suggested_take_profit', 'consensus_models_queried', 'consensus_models_agreed', 'all_ai_responses_summary']
            all_responses = final_signal_data_for_saving.get('all_ai_responses', [])
            summary_responses = []
            if isinstance(all_responses, list):
                for resp in all_responses:
                    if isinstance(resp, dict): summary_responses.append(f"{resp.get('model_name','?M?')}:{resp.get('decision','?D?').split(':')[0]}")
            log_entry = {
                'timestamp': datetime.now().isoformat(), 'symbol': final_signal_data_for_saving.get('symbol'),
                'signal_type': final_signal_data_for_saving.get('signal_type'), 'price': final_signal_data_for_saving.get('price'),
                'sma_value': final_signal_data_for_saving.get('sma'), 'rsi_value': final_signal_data_for_saving.get('rsi'),
                'macd_value': final_signal_data_for_saving.get('macd_line'), 'macd_signal_value': final_signal_data_for_saving.get('macd_signal'),
                'macd_histogram_value': final_signal_data_for_saving.get('macd_histogram'),
                'bollinger_middle': final_signal_data_for_saving.get('bb_middle'), 'bollinger_upper': final_signal_data_for_saving.get('bb_upper'),
                'bollinger_lower': final_signal_data_for_saving.get('bb_lower'),
                'ai_model': final_signal_data_for_saving.get('ai_model'), 'ai_confidence_score': final_signal_data_for_saving.get('confidence'),
                'ai_reason': final_signal_data_for_saving.get('reason'),
                'suggested_stop_loss': final_signal_data_for_saving.get('suggested_stop_loss'),
                'suggested_take_profit': final_signal_data_for_saving.get('suggested_take_profit'),
                'consensus_models_queried': final_signal_data_for_saving.get('consensus_models_queried'),
                'consensus_models_agreed': final_signal_data_for_saving.get('consensus_models_agreed'),
                'all_ai_responses_summary': "; ".join(summary_responses) if summary_responses else 'N/A'
            }
            file_exists = os.path.exists(signal_log_file_path)
            with open(signal_log_file_path, 'a', newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
                if not file_exists or csvfile.tell() == 0: writer.writeheader()
                writer.writerow(log_entry)
        except Exception as e_csv: print(f"Error logging signal to CSV: {e_csv}")

        formatted_message = format_signal_to_message(final_signal_data_for_saving)
        if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
            print("Telegram token or chat_id not configured.")
            stats["telegram_failure"] += 1
        else:
            success = await send_telegram_message(formatted_message,
                                                  bot_token=settings.TELEGRAM_BOT_TOKEN,
                                                  chat_id=settings.TELEGRAM_CHAT_ID)
            if success: stats["telegram_success"] += 1
            else: stats["telegram_failure"] += 1
    else:
        stats["ai_errors_or_hold"] += 1
    return True

class Command(BaseCommand):
    help = 'Runs the live trading bot with advanced indicators, AI signals, DB logging and stats.'

    def add_arguments(self, parser):
        parser.add_argument('--symbol', type=str, default='BTCUSDT', help='Trading symbol.')
        parser.add_argument('--log_file', type=str, default='logs/trading_signals.csv', help='Signal log file path.')
        parser.add_argument('--price_history_len', type=int, default=60, help='Max length of price history deque.')
        parser.add_argument('--recent_trend_len', type=int, default=5, help='Number of recent prices to include in AI prompt for trend context. 0 to disable.')
        parser.add_argument('--sma_window', type=int, default=20, help='SMA window. 0 to disable.')
        parser.add_argument('--rsi_window', type=int, default=14, help='RSI window. 0 to disable.')
        parser.add_argument('--macd_short', type=int, default=12, help='MACD short EMA window.')
        parser.add_argument('--macd_long', type=int, default=26, help='MACD long EMA window. 0 to disable MACD.')
        parser.add_argument('--macd_signal_period', type=int, default=9, help='MACD signal EMA window period.')
        parser.add_argument('--bb_window', type=int, default=20, help='Bollinger Bands window. 0 to disable.')

    async def handle_async(self, *args, **options):
        symbol = options['symbol'].upper()
        log_file = options['log_file']

        price_history_len = options['price_history_len']
        sma_window = options['sma_window']
        rsi_window = options['rsi_window']
        macd_short = options['macd_short']
        macd_long = options['macd_long']
        macd_signal_period = options['macd_signal_period']
        bb_window = options['bb_window']
        recent_trend_len = options['recent_trend_len']

        stats = {
            "messages_received": 0, "signals_generated_buy": 0, "signals_generated_sell": 0,
            "ai_total_queries": 0, "ai_errors_or_hold": 0,
            "db_save_success": 0, "db_save_failure": 0,
            "telegram_success": 0, "telegram_failure": 0,
            "empty_or_error_ws_messages": 0
        }

        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            try: os.makedirs(log_dir, exist_ok=True)
            except OSError as e:
                self.stderr.write(self.style.ERROR(f"Could not create log directory {log_dir}: {e}"))
                log_file = os.path.basename(log_file)
                self.stdout.write(self.style.WARNING(f"Logging to fallback file: {log_file}"))

        self.stdout.write(self.style.SUCCESS(f"Starting bot for {symbol}, Log: {log_file}, History: {price_history_len}, TrendLen: {recent_trend_len}"))
        self.stdout.write(self.style.SUCCESS(f"Indicators: SMA({sma_window}), RSI({rsi_window}), MACD({macd_short},{macd_long},{macd_signal_period}), BB({bb_window})"))

        ai_generator = AISignalGenerator()
        self.stdout.write(f"AI Models: {ai_generator.model_names_to_query}, Key: {'Set' if ai_generator.api_key else 'Not Set'}")

        price_history_deque = deque(maxlen=price_history_len)

        async def message_handler_callback(msg):
            return await process_binance_message_for_bot(
                msg, ai_generator, symbol, price_history_deque,
                sma_window, rsi_window, macd_short, macd_long, macd_signal_period, bb_window,
                recent_trend_len,
                log_file,
                stats
            )

        try:
            await listen_to_binance_ws_integrated(symbol, message_handler_callback)
        except KeyboardInterrupt: self.stdout.write(self.style.WARNING("\nBot stopped by user."))
        except Exception as e: self.stderr.write(self.style.ERROR(f"Critical error in bot: {e}\n{traceback.format_exc()}"))
        finally:
            if hasattr(ai_generator, 'close_client'): await ai_generator.close_client()

            self.stdout.write(self.style.SUCCESS("\n--- Operational Statistics ---"))
            for key, value in stats.items():
                self.stdout.write(f"{key.replace('_', ' ').capitalize()}: {value}")
            self.stdout.write(self.style.SUCCESS("--- End of Statistics ---"))
            self.stdout.write(self.style.SUCCESS("Trading bot shut down."))

    def handle(self, *args, **options):
        try: asyncio.run(self.handle_async(*args, **options))
        except KeyboardInterrupt: self.stdout.write(self.style.WARNING("Interrupted. Shutting down."))
        except Exception as e: self.stderr.write(self.style.ERROR(f"Critical error in handle(): {e}"))
