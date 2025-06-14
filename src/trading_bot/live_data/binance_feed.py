import asyncio
import json
import os
from binance import AsyncClient, BinanceSocketManager

# Existing process_message function (can be used by the original main or for other purposes)
async def process_message(msg):
    """Processes incoming WebSocket messages (original version for direct script run)."""
    if msg and 'stream' in msg and 'data' in msg:
        stream_type = msg['stream']
        data = msg['data']
        if data.get('e') == 'error': # Check .get('e') as 'e' might not always be present
            print(f"Error message received: {data.get('m')}")
            return False # Indicate error
        else:
            if '@ticker' in stream_type:
                print(f"Ticker: {data.get('s')}, Last Price: {data.get('c')}, Price Change Percent: {data.get('P')}%")
            else:
                print(f"Received: {json.dumps(data, indent=2)}")
        return True # Indicate success
    else:
        print(f"Received non-standard message: {msg}")
        return True # Continue running

async def listen_to_binance_ws_integrated(symbol, message_processor_callback, client_options=None):
    """
    Connects to Binance WebSocket for a given symbol's ticker stream
    and passes messages to an asynchronous message_processor_callback.
    'client_options' can contain API_KEY and API_SECRET if needed for private streams.
    """
    api_key = client_options.get('API_KEY') if client_options else None
    api_secret = client_options.get('API_SECRET') if client_options else None

    # Use provided API key/secret if available, otherwise create client without them (for public streams)
    if api_key and api_secret:
        client = await AsyncClient.create(api_key, api_secret)
    else:
        client = await AsyncClient.create()

    bsm = BinanceSocketManager(client)
    stream_name = f"{symbol.lower()}@ticker" # Defaulting to ticker stream for the bot

    print(f"Connecting to Binance WebSocket for integrated stream: {stream_name}...")
    try:
        async with bsm.multiplex_socket([stream_name]) as ms:
            while True:
                try:
                    # Timeout ensures we don't hang indefinitely if WebSocket goes silent without formal close
                    msg = await asyncio.wait_for(ms.recv(), timeout=60.0)
                    if not await message_processor_callback(msg):
                        print(f"Message processor for {stream_name} indicated to stop. Stopping listener.")
                        break
                except asyncio.TimeoutError:
                    print(f"No message received for {stream_name} in 60 seconds. Re-evaluating connection...")
                    # In a robust app, you might have reconnect logic here.
                    # For now, we'll break, and the management command can decide to restart.
                    break
                except Exception as e:
                    print(f"An error occurred while processing message for {stream_name}: {e}")
                    # Depending on error, might want to break or continue.
                    # Let callback decide if error is fatal by returning False.
                    await asyncio.sleep(1) # Brief pause before next recv attempt

    except asyncio.CancelledError:
        print(f"WebSocket connection for {stream_name} cancelled.")
    except Exception as e:
        print(f"Error connecting or during WebSocket operation for {stream_name}: {e}")
    finally:
        print(f"Closing Binance client session for {stream_name}.")
        await client.close_connection()
        print(f"Disconnected from {stream_name}.")

# Original listen_to_binance_ws for direct script execution (keeps original functionality)
async def listen_to_binance_ws(symbol='btcusdt'):
    """Connects to Binance WebSocket for a given symbol's ticker stream (original version)."""
    # This function now uses the generic process_message callback for standalone use.
    async def standalone_processor(msg):
        return await process_message(msg) # process_message is defined above

    # No API keys needed for public ticker stream by default for standalone run
    await listen_to_binance_ws_integrated(symbol, standalone_processor, client_options={})


async def main(): # For direct execution of this script
    # Example: Listen to BTCUSDT ticker using the original logic
    print("Running binance_feed.py in standalone mode (original functionality)...")
    await listen_to_binance_ws('btcusdt')
    # To listen to multiple streams:
    # await asyncio.gather(
    #     listen_to_binance_ws('btcusdt'),
    #     listen_to_binance_ws('ethusdt')
    # )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Script interrupted by user.")
    finally:
        print("Binance feed script (standalone) finished.")
