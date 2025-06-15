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
import httpx
import random # For jitter in retries

# --- Post-Signal Price Tracking ---
PRICE_TRACKING_INTERVALS = { # In seconds
    "5m": 5 * 60,
    "15m": 15 * 60,
    "30m": 30 * 60,
    "1hr": 60 * 60,
}
PRICE_TRACKING_FIELDS_MAP = { # Maps interval key to model field name
    "5m": "price_at_plus_5m",
    "15m": "price_at_plus_15m",
    "30m": "price_at_plus_30m",
    "1hr": "price_at_plus_1hr",
}

async def fetch_current_price_http(symbol: str, http_client: httpx.AsyncClient) -> Decimal | None:
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol.upper()}"
    try:
        response = await http_client.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        return Decimal(data['price'])
    except httpx.HTTPStatusError as e:
        print(f"PriceFetch: HTTP error for {symbol}: {e.response.status_code} - {e.response.text[:100]}")
    except httpx.RequestError as e:
        print(f"PriceFetch: Request error for {symbol}: {e}")
    except (json.JSONDecodeError, KeyError, InvalidOperation) as e:
        print(f"PriceFetch: Error parsing price data for {symbol}: {e}")
    except Exception as e:
        print(f"PriceFetch: Unexpected error for {symbol}: {e}")
    return None

def update_signal_with_future_price(signal_id: int, field_name: str, price: Decimal):
    try:
        signal = Signal.objects.get(pk=signal_id)
        setattr(signal, field_name, price)
        signal.save(update_fields=[field_name])
    except Signal.DoesNotExist:
        print(f"DBUpdate: Signal ID {signal_id} not found for updating {field_name}.")
    except Exception as e:
        print(f"DBUpdate: Error updating {field_name} for Signal ID {signal_id}: {e}")

update_signal_with_future_price_async = sync_to_async(update_signal_with_future_price, thread_sensitive=True)

async def track_post_signal_prices(signal_id: int, symbol: str, stats: dict):
    async with httpx.AsyncClient(timeout=15.0) as http_client:
        sorted_intervals = sorted(PRICE_TRACKING_INTERVALS.items(), key=lambda item: item[1])
        for interval_key, delay_seconds in sorted_intervals:
            await asyncio.sleep(delay_seconds)
            future_price = await fetch_current_price_http(symbol, http_client)
            if future_price is not None:
                field_name = PRICE_TRACKING_FIELDS_MAP[interval_key]
                try:
                    await update_signal_with_future_price_async(signal_id, field_name, future_price)
                    stats["post_signal_price_fetch_success"] = stats.get("post_signal_price_fetch_success", 0) + 1
                except Exception as e_db_update:
                    print(f"PriceTrackTask: DB update failed for {field_name}, Signal ID {signal_id}: {e_db_update}")
                    stats["post_signal_price_fetch_failure"] = stats.get("post_signal_price_fetch_failure", 0) + 1
            else:
                print(f"PriceTrackTask: Failed to fetch price for {symbol} at {interval_key} (Signal ID: {signal_id})")
                stats["post_signal_price_fetch_failure"] = stats.get("post_signal_price_fetch_failure", 0) + 1
            await asyncio.sleep(0.1)

def save_signal_to_db(signal_data: dict):
    try:
        def to_decimal_or_none(value, precision='0.00000001'):
            if value is None: return None
            try:
                if isinstance(value, Decimal): return value.quantize(Decimal(precision))
                return Decimal(str(value)).quantize(Decimal(precision))
            except (InvalidOperation, TypeError, ValueError) as e:
                print(f"Warning: DB Save - Could not convert '{value}' (type: {type(value)}) to Decimal. Storing as None. Error: {e}")
                return None
        def to_float_or_none(value):
            if value is None: return None
            try: return float(value)
            except (ValueError, TypeError):
                print(f"Warning: DB Save - Could not convert '{value}' to float. Storing as None.")
                return None
        def to_int_or_none(value):
            if value is None: return None
            try: return int(value)
            except (ValueError, TypeError):
                print(f"Warning: DB Save - Int conversion error for '{value}'. Storing None.")
                return None

        signal_obj = Signal(
            symbol=signal_data.get('symbol'), signal_type=signal_data.get('signal_type'),
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
            consensus_models_queried=to_int_or_none(signal_data.get('consensus_models_queried')),
            consensus_models_agreed=to_int_or_none(signal_data.get('consensus_models_agreed')),
            raw_ai_responses=signal_data.get('all_ai_responses'),
            ai_key_indicators_note=signal_data.get('key_indicators_note')
        )
        signal_obj.save()
        return signal_obj.id
    except Exception as e:
        print(f"Error saving signal to database: {e}")
        print(f"Signal data that failed DB save: {{key: type(value).__name__ for key, value in signal_data.items()}}")
        traceback.print_exc()
        return None

save_signal_to_db_async = sync_to_async(save_signal_to_db, thread_sensitive=True)

async def process_binance_message_for_bot(
    msg, ai_generator, symbol,
    price_history_deque,
    sma_window, rsi_window, macd_short, macd_long, macd_signal_period, bb_window,
    recent_trend_len,
    signal_log_file_path,
    stats
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

    stats["ai_total_primary_model_queries"] += 1
    signal_dict_from_ai = await ai_generator.generate_signal(processed_data_for_ai)

    if signal_dict_from_ai and signal_dict_from_ai.get('all_ai_responses'):
        for model_resp in signal_dict_from_ai.get('all_ai_responses', {}).values(): # all_ai_responses is a dict model_name: [messages]
            if isinstance(model_resp, list) and model_resp:
                last_message = model_resp[-1] # Check the last message (assistant's response)
                if isinstance(last_message, dict) and last_message.get('role') == 'assistant':
                    # This is a simplified check. AISignalGenerator's _parse_ai_response now returns a dict
                    # that includes an 'error' key if querying failed for that model, or 'decision':'ERROR'.
                    # The 'all_ai_responses' in signal_dict_from_ai is now a list of these parsed dicts.
                    pass # Covered by the next block

    if signal_dict_from_ai and signal_dict_from_ai.get('all_ai_responses'):
        for model_resp_parsed in signal_dict_from_ai['all_ai_responses']: # This is now list of parsed dicts
            if model_resp_parsed.get('decision') == 'ERROR':
                model_name_stat_key = f"ai_error_{model_resp_parsed.get('model_name', 'unknown_model').replace('/', '-')}"
                stats[model_name_stat_key] = stats.get(model_name_stat_key, 0) + 1


    if signal_dict_from_ai:
        if signal_dict_from_ai.get('signal_type') == 'BUY': stats["signals_generated_buy"] += 1
        elif signal_dict_from_ai.get('signal_type') == 'SELL': stats["signals_generated_sell"] += 1

        final_signal_data_for_saving = processed_data_for_ai.copy(); final_signal_data_for_saving.update(signal_dict_from_ai)
        final_signal_data_for_saving['price'] = signal_dict_from_ai.get('price', Decimal(current_price_str))

        saved_signal_id = None
        try:
            saved_signal_id = await save_signal_to_db_async(final_signal_data_for_saving)
            if saved_signal_id:
                stats["db_save_success"] += 1
                if final_signal_data_for_saving.get('signal_type') in ['BUY', 'SELL']:
                    asyncio.create_task(track_post_signal_prices(saved_signal_id, final_signal_data_for_saving.get('symbol'), stats))
            else: stats["db_save_failure"] += 1
        except Exception as e_db:
            print(f"DB Save Exception from call: {e_db}"); stats["db_save_failure"] += 1

        try:
            fieldnames = ['timestamp', 'symbol', 'signal_type', 'price', 'sma_value', 'rsi_value', 'macd_value', 'macd_signal_value', 'macd_histogram_value', 'bollinger_middle', 'bollinger_upper', 'bollinger_lower', 'ai_model', 'ai_confidence_score', 'ai_reason', 'suggested_stop_loss', 'suggested_take_profit', 'consensus_models_queried', 'consensus_models_agreed', 'all_ai_responses_summary', 'ai_key_indicators_note']
            all_responses_csv = final_signal_data_for_saving.get('all_ai_responses', [])
            summary_responses_csv = []
            if isinstance(all_responses_csv, dict): # It's a dict model_name: [messages]
                for model_name_key, messages_list in all_responses_csv.items():
                    # Attempt to get the final decision from the last assistant message
                    decision_for_model = "NO_DECISION"
                    if messages_list and isinstance(messages_list[-1], dict) and messages_list[-1].get('role') == 'assistant':
                        try:
                            # The content of assistant message is the JSON string for that model's output
                            assistant_content = json.loads(messages_list[-1]['content'])
                            decision_for_model = assistant_content.get('decision', 'NO_DECISION').split(':')[0]
                        except: # json.JSONDecodeError or other issues
                            decision_for_model = "PARSE_ERR"
                    summary_responses_csv.append(f"{model_name_key.split('/')[-1].split(':')[0]}:{decision_for_model}")

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
                'all_ai_responses_summary': "; ".join(summary_responses_csv) if summary_responses_csv else 'N/A',
                'ai_key_indicators_note': final_signal_data_for_saving.get('key_indicators_note', 'N/A')
            }
            file_exists = os.path.exists(signal_log_file_path)
            with open(signal_log_file_path, 'a', newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
                if not file_exists or csvfile.tell() == 0: writer.writeheader()
                writer.writerow(log_entry)
        except Exception as e_csv: print(f"Error logging signal to CSV: {e_csv}")

        formatted_message = format_signal_to_message(final_signal_data_for_saving)
        if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
            print("Telegram token or chat_id not configured."); stats["telegram_failure"] += 1
        else:
            success = await send_telegram_message(formatted_message, bot_token=settings.TELEGRAM_BOT_TOKEN, chat_id=settings.TELEGRAM_CHAT_ID)
            if success: stats["telegram_success"] += 1
            else: stats["telegram_failure"] += 1
    else:
        stats["ai_primary_model_holds_or_no_signal"] += 1
        # Log errors for individual models if generate_signal returned None
        # This requires AISignalGenerator to expose this info, e.g., via a property after call
        # For now, AISignalGenerator prints these errors internally.
        # If generate_signal returns None, it means the primary model failed or suggested HOLD.
        # We might not have the `all_ai_responses` structure if the primary fails very early.
        # The `ai_generator.model_names_to_query` can be used to check if specific error stats can be incremented.
        # This part of stats is tricky if AISG doesn't explicitly return all individual responses on primary failure.
        # However, AISG's `generate_signal` *does* return `all_ai_responses` (as conversation history) in the final dict.
        # If `signal_dict_from_ai` is None, we need a way to get those individual errors.
        # The current change in `NEW_PROCESS_FUNCTION_STATS_CONTENT` attempts to handle this by checking
        # `processed_data_for_ai.get('all_ai_responses',[])` but `processed_data_for_ai` does not get this.
        # This needs `ai_generator` to perhaps store `self.last_parsed_signals_from_models`
        if hasattr(ai_generator, 'last_parsed_signals_from_models_for_stats'): # Hypothetical attribute
            for model_resp_err in ai_generator.last_parsed_signals_from_models_for_stats:
                 if isinstance(model_resp_err, dict) and model_resp_err.get('decision') == 'ERROR':
                    model_name_stat_key_err = f"ai_error_{model_resp_err.get('model_name', 'unknown_model').replace('/', '-')}"
                    stats[model_name_stat_key_err] = stats.get(model_name_stat_key_err, 0) + 1

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
            "messages_received": 0,
            "signals_generated_buy": 0,
            "signals_generated_sell": 0,
            "ai_total_primary_model_queries": 0,
            "ai_primary_model_holds_or_no_signal": 0,
            "db_save_success": 0,
            "db_save_failure": 0,
            "telegram_success": 0,
            "telegram_failure": 0,
            "empty_or_error_ws_messages": 0,
            "post_signal_price_fetch_success": 0,
            "post_signal_price_fetch_failure": 0
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
        self.stdout.write(f"AI Models to Query: {ai_generator.model_names_to_query}, Primary: {ai_generator.primary_model_name}")
        self.stdout.write(f"OpenRouter API Key: {'Set' if ai_generator.api_key else 'Not Set'}")

        for model_name_stat in ai_generator.model_names_to_query:
            stats[f'ai_error_{model_name_stat.replace("/", "-")}'] = 0

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
            for key, value in sorted(stats.items()):
                self.stdout.write(f"{key.replace('_', ' ').capitalize()}: {value}")
            self.stdout.write(self.style.SUCCESS("--- End of Statistics ---"))
            self.stdout.write(self.style.SUCCESS("Trading bot shut down."))

    def handle(self, *args, **options):
        try: asyncio.run(self.handle_async(*args, **options))
        except KeyboardInterrupt: self.stdout.write(self.style.WARNING("Interrupted. Shutting down."))
        except Exception as e: self.stderr.write(self.style.ERROR(f"Critical error in handle(): {e}"))
