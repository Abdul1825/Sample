import asyncio
import csv
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import logging
from django.core.management.base import BaseCommand, CommandParser
from django.conf import settings # To access AI model names, call delays etc.

from trading_bot.ai_signal_generator import AISignalGenerator
from trading_bot.backtester.engine import Backtester # Assuming engine.py is created
from trading_bot.historical_data_loader import KLINE_FIELDS # Use KLINE_FIELDS for CSV header

logger = logging.getLogger('trading_bot.management.commands.run_backtest')

class Command(BaseCommand):
    help = 'Runs a backtest of the AI trading strategy using historical kline data.'

    def add_arguments(self, parser: CommandParser):
        parser.add_argument('datafile', type=str, help='Path to the historical kline data CSV file.')
        parser.add_argument('--initial_capital', type=float, default=10000.0, help='Initial capital for the backtest.')
        parser.add_argument('--commission_pct', type=float, default=0.001, help='Commission percentage per trade (e.g., 0.001 for 0.1%).')

        parser.add_argument('--price_history_len', type=int, default=60, help='Max length of price history deque for indicators.')
        parser.add_argument('--recent_trend_len', type=int, default=5, help='Number of recent prices for AI trend context.')
        parser.add_argument('--sma_window', type=int, default=20, help='SMA window.')
        parser.add_argument('--rsi_window', type=int, default=14, help='RSI window.')
        parser.add_argument('--macd_short', type=int, default=12, help='MACD short EMA window.')
        parser.add_argument('--macd_long', type=int, default=26, help='MACD long EMA window.')
        parser.add_argument('--macd_signal_period', type=int, default=9, help='MACD signal EMA window.')
        parser.add_argument('--bb_window', type=int, default=20, help='Bollinger Bands window.')

    def load_historical_data_from_csv(self, filepath: str) -> list[dict]:
        data = []
        try:
            with open(filepath, 'r', newline='') as csvfile:
                reader = csv.DictReader(csvfile)
                if not reader.fieldnames:
                    logger.error(f"CSV file {filepath} is empty or has no header.")
                    return []

                decimal_fields = ['open', 'high', 'low', 'close', 'volume',
                                  'quote_asset_volume', 'taker_buy_base_asset_volume',
                                  'taker_buy_quote_asset_volume']
                int_fields = ['timestamp', 'close_time', 'number_of_trades']

                for row_num, row in enumerate(reader):
                    try:
                        formatted_row = {}
                        for field in reader.fieldnames: # Use actual fieldnames from CSV header
                            if field in decimal_fields:
                                formatted_row[field] = Decimal(row[field])
                            elif field in int_fields:
                                formatted_row[field] = int(row[field])
                            else:
                                formatted_row[field] = row[field]
                        data.append(formatted_row)
                    except (InvalidOperation, ValueError, TypeError) as e:
                        logger.error(f"Error converting data in CSV row {row_num + 1} from {filepath}: {row}. Error: {e}", exc_info=True)
                        continue
            logger.info(f"Loaded {len(data)} klines from {filepath}")
            return data
        except FileNotFoundError:
            logger.error(f"Historical data file not found: {filepath}")
            return []
        except Exception as e:
            logger.error(f"Error loading historical data from {filepath}: {e}", exc_info=True)
            return []

    async def handle_async(self, *args, **options):
        datafile = options['datafile']
        initial_capital = Decimal(str(options['initial_capital']))
        commission_pct = Decimal(str(options['commission_pct']))

        historical_data = self.load_historical_data_from_csv(datafile)
        if not historical_data:
            self.stderr.write(self.style.ERROR("No historical data loaded. Exiting backtest."))
            return

        ai_generator = AISignalGenerator()

        backtester_params = {
            'historical_data': historical_data,
            'initial_capital': initial_capital,
            'commission_pct': commission_pct,
            'ai_generator': ai_generator,
            'price_history_len': options['price_history_len'],
            'sma_window': options['sma_window'],
            'rsi_window': options['rsi_window'],
            'macd_short': options['macd_short'],
            'macd_long': options['macd_long'],
            'macd_signal_period': options['macd_signal_period'],
            'bb_window': options['bb_window'],
            'recent_trend_len': options['recent_trend_len']
        }

        backtester = Backtester(**backtester_params)

        self.stdout.write(self.style.SUCCESS("Initializing backtest..."))
        try:
            await backtester.run_backtest()
            backtester.display_results()
        except Exception as e:
            logger.error("Critical error during backtest run.", exc_info=True)
            self.stderr.write(self.style.ERROR(f"Backtest failed: {e}"))
        finally:
            if hasattr(ai_generator, 'close_client'):
                await ai_generator.close_client()
            self.stdout.write(self.style.SUCCESS("Backtest process finished."))

    def handle(self, *args, **options):
        try:
            asyncio.run(self.handle_async(*args, **options))
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Backtest interrupted by user."))
        except Exception as e:
            logger.error("Unhandled error in backtest command handle.", exc_info=True)
            self.stderr.write(self.style.ERROR(f"An unexpected error occurred: {e}"))
