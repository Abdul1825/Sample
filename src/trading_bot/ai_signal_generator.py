import httpx # For making HTTP requests to OpenRouter
import json
import os
from decimal import Decimal, InvalidOperation
from django.conf import settings # To get OPENROUTER_API_KEY

class AISignalGenerator:
    def __init__(self, config=None):
        """
        Initialize the AI Signal Generator.
        'config' can be a dictionary with settings. OPENROUTER_API_KEY is expected.
        """
        self.config = config if config else {}
        self.api_key = getattr(settings, 'OPENROUTER_API_KEY', os.environ.get('OPENROUTER_API_KEY'))
        self.model_name = getattr(settings, 'OPENROUTER_MODEL_NAME', "mistralai/mistral-7b-instruct:free") # Default free model

        if not self.api_key:
            print("WARNING: OPENROUTER_API_KEY not found in Django settings or environment variables.")

        # HTTP client that can be reused for multiple requests
        self.client = httpx.AsyncClient(timeout=30.0) # 30 seconds timeout
        print(f"AISignalGenerator initialized with model: {self.model_name}")

    async def close_client(self):
        """Closes the HTTP client session."""
        await self.client.aclose()

    def _construct_prompt(self, processed_data):
        """
        Constructs a detailed prompt for the AI model including multiple technical indicators.
        Asks for a structured JSON response including decision, reason, confidence, SL, and TP.
        """
        symbol = processed_data.get('symbol', 'N/A')
        last_price = processed_data.get('last_price', 'N/A')
        sma = processed_data.get('sma', 'N/A')
        rsi = processed_data.get('rsi', 'N/A')
        macd_line = processed_data.get('macd', 'N/A') # MACD line
        # Note: MACD signal/histogram might be N/A if not fully implemented yet in utils
        bb_middle = processed_data.get('bb_middle', 'N/A')
        bb_upper = processed_data.get('bb_upper', 'N/A')
        bb_lower = processed_data.get('bb_lower', 'N/A')

        prompt = (
            f"You are an expert trading analysis AI. Based on the following real-time market data for {symbol}, "
            f"provide a trading decision (BUY, SELL, or HOLD). Explain your reasoning. "
            f"Also, provide a confidence score (0.0 to 1.0) for your decision, and if BUY or SELL, "
            f"suggest a stop-loss price and a take-profit price.\n\n"
            f"Market Data for {symbol}:\n"
            f"- Current Price: {last_price}\n"
            f"- 20-period SMA: {sma}\n"
            f"- 14-period RSI: {rsi}\n"
            f"- MACD Line (12,26): {macd_line}\n"
            f"- Bollinger Bands (20,2): Middle={bb_middle}, Upper={bb_upper}, Lower={bb_lower}\n\n"
            f"Your analysis should consider these indicators. For example, is the price near Bollinger Bands? "
            f"What does RSI suggest about overbought/oversold conditions? How is MACD trending?\n\n"
            f"Respond *only* with a valid JSON object formatted exactly as follows:\n"
            f'{{"decision": "BUY|SELL|HOLD", "reason": "Your detailed reasoning here.", "confidence_score": <float_0_to_1>, '
            f'"suggested_stop_loss": <float_price_or_null>, "suggested_take_profit": <float_price_or_null>}}\n'
            f"Ensure numbers are actual numbers (e.g., 0.75, 50000.50) not strings in the JSON, and use null for SL/TP if not applicable (e.g. for HOLD)."
        )
        return prompt

    async def _query_openrouter_api(self, prompt):
        """
        Queries the OpenRouter API with the given prompt.
        """
        if not self.api_key:
            print("AISignalGenerator: Error - OpenRouter API key is not set.")
            return None

        try:
            response = await self.client.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model_name,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ]
                }
            )
            response.raise_for_status()  # Raise an exception for HTTP errors (4XX or 5XX)
            return response.json()
        except httpx.TimeoutException:
            print(f"AISignalGenerator: Timeout occurred while querying OpenRouter API for model {self.model_name}.")
            return None
        except httpx.NetworkError as e:
            print(f"AISignalGenerator: Network error occurred while querying OpenRouter API: {e}")
            return None
        except httpx.HTTPStatusError as e:
            # Log more details for HTTPStatusError, especially for 4xx errors
            error_details = f"HTTP error: {e.response.status_code} {e.response.reason_phrase}."
            try:
                error_body = e.response.json() # Try to get JSON error body
                error_details += f" Details: {error_body.get('error', {}).get('message', e.response.text)}"
            except json.JSONDecodeError:
                error_details += f" Details: {e.response.text}" # Fallback to raw text
            print(f"AISignalGenerator: Error querying OpenRouter ({self.model_name}): {error_details}")
            if e.response.status_code == 401: # Unauthorized
                print("AISignalGenerator: Hint: Check if your OpenRouter API key is correct and has funds/access.")
            elif e.response.status_code == 429: # Rate limit
                print("AISignalGenerator: Hint: You might be hitting OpenRouter API rate limits.")
            return None
        except httpx.RequestError as e: # Catch other request errors
            print(f"AISignalGenerator: Request error querying OpenRouter: {e}")
            return None
        except json.JSONDecodeError as e: # If OpenRouter returns non-JSON response unexpectedly
            print(f"AISignalGenerator: Error decoding JSON response from OpenRouter: {e}")
            return None
        except Exception as e:
            print(f"AISignalGenerator: Unexpected error querying OpenRouter: {e}")
            return None

    def _parse_ai_response(self, ai_response_json, symbol, last_price_str, sma_value=None): # last_price is string here
        """
        Parses the AI's structured JSON response.
        sma_value is passed for inclusion in the final signal dict if needed, though AI might use it too.
        """
        try:
            content_str = ai_response_json['choices'][0]['message']['content']
            # Remove potential markdown backticks if AI wraps JSON in them
            if content_str.startswith("```json"): content_str = content_str[7:]
            if content_str.startswith("```"): content_str = content_str[3:]
            if content_str.endswith("```"): content_str = content_str[:-3]
            content_str = content_str.strip()

            signal_json = json.loads(content_str)

            decision = signal_json.get('decision', 'HOLD').upper()
            reason = signal_json.get('reason', 'No reason provided by AI.')
            confidence = signal_json.get('confidence_score', 0.5) # Default confidence
            stop_loss = signal_json.get('suggested_stop_loss')
            take_profit = signal_json.get('suggested_take_profit')

            # Validate types, convert if necessary
            try:
                confidence = float(confidence)
            except (ValueError, TypeError):
                print(f"Warning: Could not parse confidence '{confidence}' as float. Defaulting to 0.5.")
                confidence = 0.5

            try:
                current_price_decimal = Decimal(str(last_price_str))
            except InvalidOperation:
                print(f"Error: Invalid last_price_str '{last_price_str}' for Decimal conversion.")
                return None # Cannot proceed without a valid price

            def parse_price_field(price_field):
                if price_field is None or isinstance(price_field, (str, int, float)):
                    try:
                        return Decimal(str(price_field)) if price_field is not None else None
                    except (InvalidOperation, ValueError, TypeError):
                        print(f"Warning: Could not parse price field '{price_field}' as Decimal. Setting to None.")
                        return None
                return None

            stop_loss_decimal = parse_price_field(stop_loss)
            take_profit_decimal = parse_price_field(take_profit)

            if decision in ['BUY', 'SELL']:
                signal_dict = {
                    'symbol': symbol,
                    'signal_type': decision,
                    'price': current_price_decimal, # Use Decimal price
                    'confidence': confidence,
                    'reason': reason,
                    'ai_model': self.model_name,
                    'suggested_stop_loss': stop_loss_decimal,
                    'suggested_take_profit': take_profit_decimal
                }
                if sma_value is not None: # Ensure sma_value is also Decimal or compatible string
                    try: signal_dict['sma'] = Decimal(str(sma_value))
                    except: signal_dict['sma'] = str(sma_value) # Fallback to string if not Decimal-able

                return signal_dict
            elif decision == 'HOLD':
                print(f"AISignalGenerator: AI recommends HOLD for {symbol}. Reason: {reason}, Confidence: {confidence:.2f}")
                return None
            else:
                print(f"AISignalGenerator: Unknown decision '{decision}' from AI.")
                return None

        except (json.JSONDecodeError, KeyError, TypeError, IndexError) as e:
            print(f"AISignalGenerator: Error parsing AI response JSON: {e}. Response content: '{content_str[:500]}...'") # Log part of content
            return None
        except Exception as e:
            print(f"AISignalGenerator: Unexpected error during AI response parsing: {e}. Response: {ai_response_json}")
            return None


    async def generate_signal(self, processed_data):
        """
        Process incoming processed_data, query AI, and generate a trading signal.
        'processed_data' is expected to include 'symbol', 'last_price', and optionally 'sma'.
        """
        if not self.api_key:
            print("AISignalGenerator: Cannot generate signal, OpenRouter API key not set.")
            return None

        if not processed_data or 'last_price' not in processed_data or 'symbol' not in processed_data:
            print("AISignalGenerator: Invalid or incomplete processed data for AI.")
            return None

        symbol = processed_data.get('symbol')
        last_price = processed_data.get('last_price')
        sma_value = processed_data.get('sma') # Get SMA from processed_data

        prompt = self._construct_prompt(processed_data)
        # print(f"AISignalGenerator: Querying AI for {symbol} with prompt: {prompt[:100]}...")

        ai_response_json = await self._query_openrouter_api(prompt)

        if ai_response_json:
            return self._parse_ai_response(ai_response_json, symbol, last_price, sma_value) # Pass sma_value
        else:
            print(f"AISignalGenerator: No valid response from AI for {symbol}.")
            return None

    def process_market_data_for_ai(self, market_data):
        """
        Transforms raw market data into a format suitable for the AI model.
        (This function is largely the same as before but is crucial input for the AI)
        """
        if market_data and market_data.get('s') and market_data.get('c'):
            processed = {
                'symbol': market_data.get('s'),
                'last_price': market_data.get('c'),
                'price_change_percent': market_data.get('P'),
                'high_price': market_data.get('h'),
                'low_price': market_data.get('l'),
                'volume': market_data.get('v'),
                'timestamp': market_data.get('E')
                # Add more fields or calculated indicators here in the future
            }
            return processed
        print(f"AISignalGenerator: Could not process raw market data: {market_data}")
        return None

# Example Usage (for testing this module directly - requires async context and API key):
async def _test_ai_signal_generator():
    # IMPORTANT: To test this, you need to set OPENROUTER_API_KEY environment variable
    # or ensure it's in a .env file loaded by your test runner.
    print("Testing AISignalGenerator...")
    if not os.environ.get('OPENROUTER_API_KEY') and not getattr(settings, 'OPENROUTER_API_KEY', None):
        print("Skipping AISignalGenerator test: OPENROUTER_API_KEY not found.")
        # Try to load from .env for local testing if Django settings not fully configured yet
        from dotenv import load_dotenv
        load_dotenv()
        if not os.environ.get('OPENROUTER_API_KEY'):
             print("Still no API Key after trying .env. AISignalGenerator test will likely fail to query API.")


    # Mock Django settings if not running in full Django context for testing
    class MockSettings:
        OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
        OPENROUTER_MODEL_NAME = "mistralai/mistral-7b-instruct:free"
        # Or use another free model: "nousresearch/nous-capybara-7b:free", "gryphe/mythomist-7b:free"

    global settings # Allow reassignment for this test block
    if not getattr(settings, 'OPENROUTER_API_KEY', None): # If Django settings not really loaded
        settings = MockSettings()


    generator = AISignalGenerator()

    sample_market_data = {
        's': 'BTCUSDT', 'c': '60000.00', 'P': '1.5', 'h': '60500.00', 'l': '59500.00', 'v': '1000', 'E': 1672515782134
    }
    processed_data = generator.process_market_data_for_ai(sample_market_data)

    if processed_data:
        print(f"Test: Processed data for AI: {processed_data}")
        signal = await generator.generate_signal(processed_data)
        if signal:
            print(f"Test: Generated Signal: {signal}")
        else:
            print("Test: No signal generated.")
    else:
        print("Test: Could not process sample market data.")

    await generator.close_client() # Important to close the client

if __name__ == '__main__':
    # This test needs to be run in an environment where Django settings are available
    # or mocked, and OPENROUTER_API_KEY is set.
    # Example: python -m dotenv run python src/trading_bot/ai_signal_generator.py
    # (after pip install python-dotenv)

    # A bit tricky to run directly due to Django settings dependency.
    # For now, this __main__ block is more for illustration of how to call it.
    # Proper testing would involve Django's test framework or careful mocking.
    print("To test AISignalGenerator directly, ensure OPENROUTER_API_KEY is set in your environment or .env file,")
    print("and run within a Django context or with mocked settings.")
    # asyncio.run(_test_ai_signal_generator()) # Uncomment carefully for local testing

    # To make it runnable for basic structure check without full Django:
    class MinimalSettings:
        OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY_TEST', None) # Use a test key if needed
        OPENROUTER_MODEL_NAME = "mistralai/mistral-7b-instruct:free"

    original_settings = settings # Store original settings
    settings = MinimalSettings()

    if settings.OPENROUTER_API_KEY:
        print(f"Running test with API key: {settings.OPENROUTER_API_KEY[:5]}...")
        asyncio.run(_test_ai_signal_generator())
    else:
        print("Skipping direct test run as OPENROUTER_API_KEY_TEST is not set.")

    settings = original_settings # Restore original settings
