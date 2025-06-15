import asyncio
import csv
import os
from datetime import datetime, timezone
from django.core.management.base import BaseCommand, CommandParser
from trading_bot.historical_data_loader import fetch_historical_klines, KLINE_FIELDS
import logging

logger = logging.getLogger('trading_bot.management.commands.download_historical_data')

class Command(BaseCommand):
    help = 'Downloads historical kline data from Binance and saves it to a CSV file.'

    def add_arguments(self, parser: CommandParser):
        parser.add_argument('symbol', type=str, help='Trading symbol (e.g., BTCUSDT).')
        parser.add_argument('interval', type=str, help='Kline interval (e.g., 1m, 5m, 1h, 1d).')
        parser.add_argument('startdate', type=str, help='Start date (YYYY-MM-DD).')
        parser.add_argument('--enddate', type=str, help='End date (YYYY-MM-DD, optional, defaults to current date).')
        parser.add_argument('--outputdir', type=str, default='historical_data', help='Directory to save CSV files (default: historical_data).')
        parser.add_argument('--limit', type=int, default=1000, help='Limit for klines per API request (max 1000).')

    def handle(self, *args, **options):
        symbol = options['symbol'].upper()
        interval = options['interval']
        start_date_str = options['startdate']
        end_date_str = options['enddate']
        output_dir_base = options['outputdir']
        limit = options['limit']

        try:
            start_dt = datetime.strptime(start_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            start_time_ms = int(start_dt.timestamp() * 1000)
        except ValueError:
            self.stderr.write(self.style.ERROR("Invalid start date format. Please use YYYY-MM-DD."))
            logger.error("Invalid start date format provided.", exc_info=True)
            return

        end_time_ms = None
        if end_date_str:
            try:
                end_dt = datetime.strptime(end_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                end_time_ms = int(datetime(end_dt.year, end_dt.month, end_dt.day, 23, 59, 59, 999000, tzinfo=timezone.utc).timestamp() * 1000)
            except ValueError:
                self.stderr.write(self.style.ERROR("Invalid end date format. Please use YYYY-MM-DD."))
                logger.error("Invalid end date format provided.", exc_info=True)
                return
        else:
            end_time_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        self.stdout.write(self.style.SUCCESS(f"Fetching data for {symbol} ({interval}) from {start_date_str} to {end_date_str or 'now'}..."))
        logger.info(f"Initiating kline fetch: Symbol={symbol}, Interval={interval}, Start={start_date_str}, End={end_date_str or 'now'}")

        try:
            klines = asyncio.run(fetch_historical_klines(symbol, interval, start_time_ms, end_time_ms, limit))
        except Exception as e:
            logger.error(f"Error during asyncio.run(fetch_historical_klines): {e}", exc_info=True)
            self.stderr.write(self.style.ERROR(f"Failed to fetch klines: {e}"))
            return

        if not klines:
            self.stdout.write(self.style.WARNING("No klines data fetched."))
            logger.warning(f"No klines data returned for {symbol} ({interval}) for the specified period.")
            return

        output_symbol_dir = os.path.join(output_dir_base, symbol)
        output_interval_dir = os.path.join(output_symbol_dir, interval)
        try:
            os.makedirs(output_interval_dir, exist_ok=True)
        except OSError as e:
            logger.error(f"Could not create directory {output_interval_dir}: {e}", exc_info=True)
            self.stderr.write(self.style.ERROR(f"Could not create output directory: {e}"))
            return

        end_date_filename_part = datetime.fromtimestamp(end_time_ms/1000, tz=timezone.utc).strftime("%Y-%m-%d")
        filename = f"{symbol}_{interval}_{start_date_str}_to_{end_date_filename_part}.csv"
        filepath = os.path.join(output_interval_dir, filename)

        try:
            with open(filepath, 'w', newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=KLINE_FIELDS)
                writer.writeheader()
                for kline_dict in klines:
                    writer.writerow(kline_dict)
            self.stdout.write(self.style.SUCCESS(f"Successfully saved {len(klines)} klines to {filepath}"))
            logger.info(f"Saved {len(klines)} klines to {filepath}")
        except IOError as e:
            logger.error(f"Error writing klines to CSV file {filepath}: {e}", exc_info=True)
            self.stderr.write(self.style.ERROR(f"Error writing to CSV: {e}"))
        except Exception as e:
            logger.error(f"Unexpected error during CSV writing: {e}", exc_info=True)
            self.stderr.write(self.style.ERROR(f"An unexpected error occurred during CSV writing: {e}"))
