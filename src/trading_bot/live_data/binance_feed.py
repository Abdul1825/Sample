import asyncio
import json
import os
import random
import httpx
from django.conf import settings
from binance import AsyncClient, BinanceSocketManager
import logging

logger = logging.getLogger('trading_bot.live_data.binance_feed')

async def process_message(msg):
    """Processes incoming WebSocket messages (original version for direct script run)."""
    if msg and 'stream' in msg and 'data' in msg:
        stream_type = msg['stream']
        data = msg['data']
        if data.get('e') == 'error':
            logger.error(f"WS process_message - Error: {data.get('m')}")
            return False
        else:
            if '@ticker' in stream_type:
                logger.debug(f"WS Ticker: {data.get('s')}, Px: {data.get('c')}, Chg%: {data.get('P')}%")
            else:
                logger.debug(f"WS Received other: {json.dumps(data)}")
        return True
    else:
        logger.warning(f"WS process_message - Non-standard: {msg}")
        return True

async def listen_to_binance_ws_integrated(symbol, message_processor_callback, client_options=None):
    api_key = client_options.get('API_KEY') if client_options else None
    api_secret = client_options.get('API_SECRET') if client_options else None
    stale_connection_timeout = float(getattr(settings, 'BINANCE_WS_STALE_TIMEOUT', 180.0))
    initial_reconnect_delay = float(getattr(settings, 'BINANCE_WS_INITIAL_RECONNECT_DELAY', 5.0))
    max_reconnect_delay = float(getattr(settings, 'BINANCE_WS_MAX_RECONNECT_DELAY', 120.0))
    current_reconnect_delay = initial_reconnect_delay
    stream_name = f"{symbol.lower()}@ticker" # Define stream_name here for use in CancelledError log

    while True:
        client = None
        try:
            if api_key and api_secret:
                client = await AsyncClient.create(api_key, api_secret)
            else:
                client = await AsyncClient.create()
            bsm = BinanceSocketManager(client)
            logger.info(f"Connecting to WebSocket stream: {stream_name}...")
            async with bsm.multiplex_socket([stream_name]) as ms:
                logger.info(f"Successfully connected to {stream_name}.")
                current_reconnect_delay = initial_reconnect_delay
                while True:
                    try:
                        msg = await asyncio.wait_for(ms.recv(), timeout=stale_connection_timeout)
                        if not await message_processor_callback(msg):
                            logger.info(f"Message processor for {stream_name} indicated stop. Terminating listener.")
                            if client: await client.close_connection()
                            return
                    except asyncio.TimeoutError:
                        logger.warning(f"No message on {stream_name} for {stale_connection_timeout}s (stale). Reconnecting...")
                        break
                    except Exception as e:
                        logger.error(f"Error during message handling for {stream_name}: {e}. Reconnecting...", exc_info=True)
                        break
        except httpx.NetworkError as e:
            logger.error(f"NetworkError connecting WS for {symbol}: {e}. Retrying...", exc_info=True)
        except httpx.HTTPStatusError as e:
             logger.error(f"HTTPStatusError connecting WS for {symbol}: {e.response.status_code if hasattr(e, 'response') else ''}. Retrying...", exc_info=True)
        except asyncio.CancelledError:
            logger.info(f"WebSocket connection for {stream_name} cancelled by application. Exiting.")
            if client: await client.close_connection()
            return
        except Exception as e:
            logger.error(f"Error connecting/operating WS for {stream_name}: {e}. Retrying...", exc_info=True)
        finally:
            if client:
                logger.debug(f"Closing client session for {stream_name} before potential retry.")
                await client.close_connection()
                logger.debug(f"Client session for {stream_name} closed.")
        jitter = random.uniform(0, current_reconnect_delay * 0.1)
        actual_delay = min(current_reconnect_delay + jitter, max_reconnect_delay)
        logger.info(f"Will attempt to reconnect WS for {symbol} in {actual_delay:.2f} seconds...")
        await asyncio.sleep(actual_delay)
        current_reconnect_delay = min(current_reconnect_delay * 2, max_reconnect_delay)

async def listen_to_binance_ws(symbol='btcusdt'):
    async def standalone_processor(msg):
        return await process_message(msg)
    await listen_to_binance_ws_integrated(symbol, standalone_processor, client_options={})

async def main():
    logger.info("Running binance_feed.py standalone...")
    await listen_to_binance_ws('btcusdt')

if __name__ == "__main__":
    # Basic logging setup for standalone run, if settings are not configured.
    if not logging.getLogger('trading_bot.binance_feed').handlers:
        logging.basicConfig(level=logging.INFO, format='%(levelname)s %(asctime)s %(name)s - %(message)s')

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Standalone binance_feed.py script interrupted by user.")
    finally:
        logger.info("Standalone binance_feed.py script finished.")
