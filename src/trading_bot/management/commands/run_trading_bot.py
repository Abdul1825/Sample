import asyncio
import os
import json
from collections import deque
from decimal import Decimal, InvalidOperation # Ensure Decimal and InvalidOperation are imported
from django.core.management.base import BaseCommand
from django.conf import settings
from asgiref.sync import sync_to_async # For saving to DB from async code

from trading_bot.models import Signal # Import the Signal model
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

# Database saving function (to be wrapped with sync_to_async)
def save_signal_to_db(signal_data: dict):
    """Saves a signal dictionary to the Signal model in the database."""
    try:
        # Convert price fields from string/float to Decimal if they aren't already
        # AISignalGenerator's _parse_ai_response should be returning Decimals for prices now.

        # Helper to ensure correct Decimal conversion or None
        def to_decimal_or_none(value, precision='0.00000001'): # Default 8 decimal places
            if value is None: return None
            try:
                return Decimal(str(value)).quantize(Decimal(precision))
            except (InvalidOperation, TypeError, ValueError): # Catch more errors during conversion
                print(f"Warning: Could not convert '{value}' to Decimal for DB save. Storing as None.")
                return None

        # Helper for float or None
        def to_float_or_none(value):
            if value is None: return None
            try:
                return float(value)
            except (ValueError, TypeError):
                print(f"Warning: Could not convert '{value}' to float for DB save. Storing as None.")
                return None

        signal_obj = Signal(
            symbol=signal_data.get('symbol'),
            signal_type=signal_data.get('signal_type'),
            price=to_decimal_or_none(signal_data.get('price')),

            ai_model=signal_data.get('ai_model'),
            ai_confidence_score=to_float_or_none(signal_data.get('confidence')), # confidence from AI
            ai_reason=signal_data.get('reason'),
            suggested_stop_loss=to_decimal_or_none(signal_data.get('suggested_stop_loss')),
            suggested_take_profit=to_decimal_or_none(signal_data.get('suggested_take_profit')),

            # Technical Indicators
            sma_value=to_decimal_or_none(signal_data.get('sma')),
            rsi_value=to_decimal_or_none(signal_data.get('rsi'), precision='0.01'), # RSI typically 2 decimal places

            macd_value=to_decimal_or_none(signal_data.get('macd')),
            # macd_signal_value and macd_histogram_value might be None if not calculated
            macd_signal_value=to_decimal_or_none(signal_data.get('macd_signal_line')), # Key name might differ
            macd_histogram_value=to_decimal_or_none(signal_data.get('macd_histogram')), # Key name might differ

            bollinger_upper=to_decimal_or_none(signal_data.get('bb_upper')),
            bollinger_middle=to_decimal_or_none(signal_data.get('bb_middle')),
            bollinger_lower=to_decimal_or_none(signal_data.get('bb_lower')),
        )
        signal_obj.save()
        print(f"Successfully saved signal for {signal_data.get('symbol')} to database.")
    except Exception as e:
        print(f"Error saving signal to database: {e}")
        print(f"Signal data that failed: {signal_data}")

# Async wrapper for DB saving
save_signal_to_db_async = sync_to_async(save_signal_to_db, thread_sensitive=True)


async def process_binance_message_for_bot(
    msg, ai_generator, symbol,
    price_history_deque,
    sma_window, rsi_window, macd_short, macd_long, macd_signal_period, bb_window, # Renamed macd_signal to macd_signal_period
    signal_log_file_path
):
    if not (msg and 'stream' in msg and 'data' in msg): return True
    data = msg['data']
    if data.get('e') == 'error':
        print(f"Error message from WebSocket: {data.get('m')}"); return True

    current_price_str = data.get('c')
    if current_price_str: update_price_history(current_price_str, price_history_deque)
    else: print("Warning: No price in message."); return True

    processed_data_for_ai = ai_generator.process_market_data_for_ai(data)
    if not processed_data_for_ai: return True

    # Calculate indicators
    if sma_window > 0:
        sma = calculate_sma(price_history_deque, sma_window)
        if sma is not None: processed_data_for_ai['sma'] = f"{sma:.8f}"
    if rsi_window > 0:
        rsi = calculate_rsi(price_history_deque, rsi_window)
        if rsi is not None: processed_data_for_ai['rsi'] = f"{rsi:.2f}"
    if macd_long > 0:
        macd_values = calculate_macd(price_history_deque, macd_short, macd_long, macd_signal_period)
        if macd_values:
            if macd_values.get("macd") is not None: processed_data_for_ai['macd'] = f"{macd_values['macd']:.8f}"
            # TODO: Add macd_signal_line and macd_histogram to processed_data_for_ai if/when available from utils
    if bb_window > 0:
        bbands = calculate_bollinger_bands(price_history_deque, bb_window)
        if bbands:
            if bbands.get("middle") is not None: processed_data_for_ai['bb_middle'] = f"{bbands['middle']:.8f}"
            if bbands.get("upper") is not None: processed_data_for_ai['bb_upper'] = f"{bbands['upper']:.8f}"
            if bbands.get("lower") is not None: processed_data_for_ai['bb_lower'] = f"{bbands['lower']:.8f}"

    signal_dict_from_ai = await ai_generator.generate_signal(processed_data_for_ai) # This is the dict from AI

    if signal_dict_from_ai:
        # Combine AI signal with all calculated indicators for logging and DB
        # Ensure all keys in processed_data_for_ai (our indicators) are added to signal_dict_from_ai
        # if not already present (e.g. if AI didn't explicitly return them in its 'reason' or similar)
        final_signal_data_for_saving = processed_data_for_ai.copy() # Start with all indicators
        final_signal_data_for_saving.update(signal_dict_from_ai) # Overlay AI response (price, decision etc.)

        # Ensure 'price' in final_signal_data_for_saving is the price at signal generation time from AI dict
        # and not just the latest market price if they differ. AI dict should be authoritative for its fields.
        final_signal_data_for_saving['price'] = signal_dict_from_ai.get('price', current_price_str)


        print(f"Signal Generated (for DB/Log): {final_signal_data_for_saving}")

        # Save to DB (Async)
        await save_signal_to_db_async(final_signal_data_for_saving)

        # Log to CSV
        try:
            # Ensure fieldnames match the model fields + any other relevant info
            fieldnames = ['timestamp', 'symbol', 'signal_type', 'price',
                          'sma_value', 'rsi_value', 'macd_value', 'macd_signal_value', 'macd_histogram_value',
                          'bollinger_middle', 'bollinger_upper', 'bollinger_lower',
                          'ai_model', 'ai_confidence_score', 'ai_reason',
                          'suggested_stop_loss', 'suggested_take_profit']

            log_entry = {
                'timestamp': datetime.now().isoformat(),
                'symbol': final_signal_data_for_saving.get('symbol'),
                'signal_type': final_signal_data_for_saving.get('signal_type'),
                'price': final_signal_data_for_saving.get('price'),
                'sma_value': final_signal_data_for_saving.get('sma'), # Use 'sma' key as in processed_data
                'rsi_value': final_signal_data_for_saving.get('rsi'),
                'macd_value': final_signal_data_for_saving.get('macd'),
                'macd_signal_value': final_signal_data_for_saving.get('macd_signal_line'), # Match model field
                'macd_histogram_value': final_signal_data_for_saving.get('macd_histogram'), # Match model field
                'bollinger_middle': final_signal_data_for_saving.get('bb_middle'),
                'bollinger_upper': final_signal_data_for_saving.get('bb_upper'),
                'bollinger_lower': final_signal_data_for_saving.get('bb_lower'),
                'ai_model': final_signal_data_for_saving.get('ai_model'),
                'ai_confidence_score': final_signal_data_for_saving.get('confidence'), # Match AI output key
                'ai_reason': final_signal_data_for_saving.get('reason'),
                'suggested_stop_loss': final_signal_data_for_saving.get('suggested_stop_loss'),
                'suggested_take_profit': final_signal_data_for_saving.get('suggested_take_profit')
            }

            file_exists = os.path.exists(signal_log_file_path)
            with open(signal_log_file_path, 'a', newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
                if not file_exists or csvfile.tell() == 0: writer.writeheader()
                writer.writerow(log_entry)
            # print(f"Signal for {symbol} logged to {signal_log_file_path}") # Already printed if successful
        except Exception as e:
            print(f"Error logging signal to CSV: {e}")

        # Send Telegram notification using the original AI signal dict for formatting
        formatted_message = format_signal_to_message(signal_dict_from_ai)
        if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
            print("Telegram token or chat_id not configured. Cannot send signal.")
        else:
            success = await send_telegram_message(formatted_message,
                                                  bot_token=settings.TELEGRAM_BOT_TOKEN,
                                                  chat_id=settings.TELEGRAM_CHAT_ID)
            if success: print(f"Signal for {symbol} successfully sent to Telegram.")
            else: print(f"Failed to send signal for {symbol} to Telegram.")
    return True

class Command(BaseCommand):
    help = 'Runs the live trading bot with advanced indicators, AI signals, DB logging.'

    def add_arguments(self, parser):
        parser.add_argument('--symbol', type=str, default='BTCUSDT', help='Trading symbol.')
        parser.add_argument('--log_file', type=str, default='logs/trading_signals.csv', help='Signal log file path.') # Changed default
        parser.add_argument('--price_history_len', type=int, default=60, help='Max length of price history deque.')
        parser.add_argument('--sma_window', type=int, default=20, help='SMA window. 0 to disable.')
        parser.add_argument('--rsi_window', type=int, default=14, help='RSI window. 0 to disable.')
        parser.add_argument('--macd_short', type=int, default=12, help='MACD short EMA window.')
        parser.add_argument('--macd_long', type=int, default=26, help='MACD long EMA window. 0 to disable MACD.')
        parser.add_argument('--macd_signal_period', type=int, default=9, help='MACD signal EMA window period.') # Renamed from macd_signal
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

        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            try: os.makedirs(log_dir, exist_ok=True) # Added exist_ok=True
            except OSError as e:
                self.stderr.write(self.style.ERROR(f"Could not create log directory {log_dir}: {e}"))
                log_file = os.path.basename(log_file)
                self.stdout.write(self.style.WARNING(f"Logging to fallback file in current dir: {log_file}"))

        self.stdout.write(self.style.SUCCESS(f"Starting bot for {symbol}, Log: {log_file}, History: {price_history_len}"))
        self.stdout.write(self.style.SUCCESS(f"Indicators: SMA({sma_window}), RSI({rsi_window}), MACD({macd_short},{macd_long},{macd_signal_period}), BB({bb_window})"))

        ai_generator = AISignalGenerator()
        self.stdout.write(f"AI Model: {ai_generator.model_name}, Key: {'Set' if ai_generator.api_key else 'Not Set'}")

        price_history_deque = deque(maxlen=price_history_len)

        async def message_handler_callback(msg):
            return await process_binance_message_for_bot(
                msg, ai_generator, symbol, price_history_deque,
                sma_window, rsi_window, macd_short, macd_long, macd_signal_period, bb_window,
                log_file
            )

        try:
            # Ensure DB is accessible before starting (optional pre-flight check)
            # from django.db import connection
            # await sync_to_async(connection.ensure_connection, thread_sensitive=True)()
            # self.stdout.write(self.style.SUCCESS("Database connection confirmed."))

            await listen_to_binance_ws_integrated(symbol, message_handler_callback)
        # except OperationalError as e: # Example for specific DB error
            # self.stderr.write(self.style.ERROR(f"Database connection error: {e}. Ensure DB is running and migrations applied."))
        except KeyboardInterrupt: self.stdout.write(self.style.WARNING("\nBot stopped by user."))
        except Exception as e: self.stderr.write(self.style.ERROR(f"Critical error in bot: {e}"))
        finally:
            if hasattr(ai_generator, 'close_client'): await ai_generator.close_client()
            self.stdout.write(self.style.SUCCESS("Trading bot shut down."))

    def handle(self, *args, **options):
        try: asyncio.run(self.handle_async(*args, **options))
        except KeyboardInterrupt: self.stdout.write(self.style.WARNING("Interrupted. Shutting down."))
        except Exception as e: self.stderr.write(self.style.ERROR(f"Critical error in handle(): {e}"))
