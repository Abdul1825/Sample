import httpx
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import logging
import os # For creating directories
import asyncio # For asyncio.sleep

logger = logging.getLogger('trading_bot.historical_data_loader')

KLINE_FIELDS = [
    "timestamp", "open", "high", "low", "close", "volume",
    "close_time", "quote_asset_volume", "number_of_trades",
    "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"
]

def format_kline(raw_kline: list) -> dict | None:
    """Converts a raw kline list from Binance into a dictionary with Decimal types for price/volume."""
    if len(raw_kline) != len(KLINE_FIELDS):
        logger.warning(f"Unexpected kline data length: {len(raw_kline)}. Expected: {len(KLINE_FIELDS)}")
        return None

    kline_dict = {}
    try:
        kline_dict[KLINE_FIELDS[0]] = int(raw_kline[0]) # timestamp (Open time)
        kline_dict[KLINE_FIELDS[1]] = Decimal(str(raw_kline[1])) # open
        kline_dict[KLINE_FIELDS[2]] = Decimal(str(raw_kline[2])) # high
        kline_dict[KLINE_FIELDS[3]] = Decimal(str(raw_kline[3])) # low
        kline_dict[KLINE_FIELDS[4]] = Decimal(str(raw_kline[4])) # close
        kline_dict[KLINE_FIELDS[5]] = Decimal(str(raw_kline[5])) # volume
        kline_dict[KLINE_FIELDS[6]] = int(raw_kline[6]) # close_time
        kline_dict[KLINE_FIELDS[7]] = Decimal(str(raw_kline[7])) # quote_asset_volume
        kline_dict[KLINE_FIELDS[8]] = int(raw_kline[8]) # number_of_trades
        kline_dict[KLINE_FIELDS[9]] = Decimal(str(raw_kline[9])) # taker_buy_base_asset_volume
        kline_dict[KLINE_FIELDS[10]] = Decimal(str(raw_kline[10])) # taker_buy_quote_asset_volume
        kline_dict[KLINE_FIELDS[11]] = str(raw_kline[11]) # ignore - keep as string
        return kline_dict
    except (InvalidOperation, ValueError, TypeError) as e:
        logger.error(f"Error formatting kline data '{raw_kline}': {e}", exc_info=True)
        return None

async def fetch_historical_klines(
    symbol: str,
    interval: str,
    start_time_ms: int,
    end_time_ms: int = None,
    limit: int = 1000
) -> list[dict]:
    """
    Fetches historical klines from Binance, handling pagination.
    Returns a list of formatted kline dictionaries.
    """
    all_klines_formatted = []
    current_start_time_ms = start_time_ms
    base_url = "https://api.binance.com/api/v3/klines"

    async with httpx.AsyncClient(timeout=20.0) as client:
        while True:
            params = {
                "symbol": symbol.upper(),
                "interval": interval,
                "startTime": current_start_time_ms,
                "limit": limit
            }
            if end_time_ms:
                params["endTime"] = end_time_ms

            logger.info(f"Fetching klines for {symbol} ({interval}) from {datetime.fromtimestamp(current_start_time_ms/1000, tz=timezone.utc)} (limit: {limit})")

            try:
                response = await client.get(base_url, params=params)
                response.raise_for_status()
                raw_klines = response.json()

                if not raw_klines:
                    logger.info(f"No more klines received for {symbol} from {datetime.fromtimestamp(current_start_time_ms/1000, tz=timezone.utc)}.")
                    break

                formatted_batch = []
                for k in raw_klines:
                    formatted_k = format_kline(k)
                    if formatted_k:
                        formatted_batch.append(formatted_k)
                all_klines_formatted.extend(formatted_batch)

                last_kline_close_time = raw_klines[-1][6]
                current_start_time_ms = last_kline_close_time + 1

                if end_time_ms and current_start_time_ms > end_time_ms:
                    logger.info(f"Reached specified end_time_ms for {symbol}.")
                    break

                if len(raw_klines) < limit:
                    logger.info(f"Fetched fewer klines ({len(raw_klines)}) than limit ({limit}). Assuming end of data for {symbol}.")
                    break

                await asyncio.sleep(0.2)

            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error fetching klines for {symbol}: {e.response.status_code} - {e.response.text[:200]}", exc_info=True)
                break
            except httpx.RequestError as e:
                logger.error(f"Request error fetching klines for {symbol}: {e}", exc_info=True)
                break
            except (json.JSONDecodeError, Exception) as e:
                logger.error(f"Error processing kline data for {symbol}: {e}", exc_info=True)
                break

    logger.info(f"Finished fetching. Total klines retrieved for {symbol} ({interval}): {len(all_klines_formatted)}")
    return all_klines_formatted
