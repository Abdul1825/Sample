import asyncio
import os
import json
from django.core.management.base import BaseCommand
from django.conf import settings # To load configurations

# Assuming these modules are structured to be importable
# May need to adjust imports based on final project structure and PYTHONPATH
from trading_bot.live_data.binance_feed import listen_to_binance_ws_integrated
from trading_bot.ai_signal_generator import AISignalGenerator
from trading_bot.telegram_notifier import send_telegram_message, format_signal_to_message, escape_markdown_v2

# Helper function to be passed to listen_to_binance_ws_integrated
# This function will contain the logic to process messages, generate signals, and send notifications.
async def process_binance_message_for_bot(msg, ai_generator, symbol):
    """
    Processes a message from Binance WebSocket, generates a signal, and sends a notification.
    This function is called by listen_to_binance_ws_integrated.
    """
    if msg and 'stream' in msg and 'data' in msg:
        data = msg['data']
        if data.get('e') == 'error':
            print(f"Error message received from WebSocket: {data.get('m')}")
            return True # Continue listener, error is handled

        if settings.PRINT_WS_MESSAGES:
            print(f"Raw data for AI: {data}")

        processed_data_for_ai = ai_generator.process_market_data_for_ai(data)
        if not processed_data_for_ai:
            # print(f"Could not process market data for AI: {data}") # Too verbose for continuous run
            return True # Continue listener

        if settings.PRINT_WS_MESSAGES:
            print(f"Processed data for AI: {processed_data_for_ai}")

        signal = ai_generator.generate_signal(processed_data_for_ai)

        if signal:
            print(f"Signal Generated: {signal}")
            # TODO: Ensure the signal is saved to the database (Signal model)
            # from trading_bot.models import Signal as SignalModel
            # await database_sync_to_async(SignalModel.objects.create)(**signal_data_for_model)

            formatted_message = format_signal_to_message(signal)
            token = settings.TELEGRAM_BOT_TOKEN
            chat_id = settings.TELEGRAM_CHAT_ID

            if not token or not chat_id:
                print("Telegram token or chat_id not configured in Django settings. Cannot send signal.")
            else:
                success = await send_telegram_message(formatted_message, bot_token=token, chat_id=chat_id)
                if success:
                    print(f"Signal for {symbol} successfully sent to Telegram.")
                else:
                    print(f"Failed to send signal for {symbol} to Telegram.")
        return True
    else:
        if settings.PRINT_WS_MESSAGES:
            print(f"Received non-standard or empty message: {msg}")
        return True

class Command(BaseCommand):
    help = 'Runs the live trading bot, listening to Binance feed, generating signals, and notifying via Telegram.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--symbol',
            type=str,
            default='BTCUSDT',
            help='Trading symbol to monitor (e.g., BTCUSDT, ETHUSDT). Default is BTCUSDT.'
        )

    async def handle_async(self, *args, **options):
        symbol_arg = options['symbol'].upper()
        self.stdout.write(self.style.SUCCESS(f"Starting trading bot for symbol: {symbol_arg}..."))

        ai_config = {
            'BINANCE_API_KEY': settings.BINANCE_API_KEY,
            'BINANCE_API_SECRET': settings.BINANCE_API_SECRET,
            # Add any other AI related config from settings if needed
        }
        ai_generator = AISignalGenerator(config=ai_config)

        self.stdout.write(f"AISignalGenerator initialized.")
        self.stdout.write(f"Telegram Bot Token: {'Set' if settings.TELEGRAM_BOT_TOKEN else 'Not Set'}")
        self.stdout.write(f"Telegram Chat ID: {'Set' if settings.TELEGRAM_CHAT_ID else 'Not Set'}")
        self.stdout.write(f"Binance API Key: {'Set' if settings.BINANCE_API_KEY else 'Not Set'}")
        self.stdout.write(f"Binance API Secret: {'Set' if settings.BINANCE_API_SECRET else 'Not Set'}")
        self.stdout.write(f"Print WebSocket Messages: {settings.PRINT_WS_MESSAGES}")

        client_options = {
            'API_KEY': settings.BINANCE_API_KEY,
            'API_SECRET': settings.BINANCE_API_SECRET,
        }

        async def message_handler_callback(msg):
            return await process_binance_message_for_bot(msg, ai_generator, symbol_arg)

        try:
            await listen_to_binance_ws_integrated(symbol_arg, message_handler_callback, client_options=client_options)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nBot stopped by user (KeyboardInterrupt)."))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"An critical error occurred in the bot: {e}"))
        finally:
            self.stdout.write(self.style.SUCCESS("Trading bot shut down."))

    def handle(self, *args, **options):
        try:
            asyncio.run(self.handle_async(*args, **options))
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Async handler interrupted. Shutting down."))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Critical error in handle_async execution: {e}"))
