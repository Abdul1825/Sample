import httpx
import json
import os
from django.conf import settings
from decimal import Decimal, InvalidOperation
import asyncio # For concurrent API calls

class AISignalGenerator:
    def __init__(self, config=None):
        self.config = config if config else {}
        self.api_key = getattr(settings, 'OPENROUTER_API_KEY', os.environ.get('OPENROUTER_API_KEY'))

        self.primary_model_name = getattr(settings, 'OPENROUTER_MODEL_NAME', "mistralai/mistral-7b-instruct:free")
        self.secondary_model_name = getattr(settings, 'OPENROUTER_MODEL_NAME_2', None)
        self.tertiary_model_name = getattr(settings, 'OPENROUTER_MODEL_NAME_3', None)

        self.model_names_to_query = [self.primary_model_name]
        if self.secondary_model_name and self.secondary_model_name.strip():
            self.model_names_to_query.append(self.secondary_model_name.strip())
        if self.tertiary_model_name and self.tertiary_model_name.strip():
            self.model_names_to_query.append(self.tertiary_model_name.strip())
        # Remove duplicates if any model is specified multiple times
        self.model_names_to_query = sorted(list(set(self.model_names_to_query)))


        if not self.api_key:
            print("WARNING: AISignalGenerator - OPENROUTER_API_KEY not found.")

        self.client = httpx.AsyncClient(timeout=45.0) # Increased timeout for potentially multiple calls
        print(f"AISignalGenerator initialized. Primary model: {self.primary_model_name}. All models to query: {self.model_names_to_query}")

    async def close_client(self):
        await self.client.aclose()

    def _construct_prompt(self, processed_data):
        symbol = processed_data.get('symbol', 'N/A')
        last_price = processed_data.get('last_price', 'N/A')
        sma = processed_data.get('sma', 'N/A')
        rsi = processed_data.get('rsi', 'N/A')
        macd_line = processed_data.get('macd_line', 'N/A')
        macd_signal = processed_data.get('macd_signal', 'N/A')
        macd_histogram = processed_data.get('macd_histogram', 'N/A')
        bb_middle = processed_data.get('bb_middle', 'N/A')
        bb_upper = processed_data.get('bb_upper', 'N/A')
        bb_lower = processed_data.get('bb_lower', 'N/A')
        recent_prices_list = processed_data.get('recent_price_trend', []) # Expect a list of price strings
        recent_prices_str = ", ".join(recent_prices_list) if recent_prices_list else "N/A"


        prompt = (
            f"You are an expert trading analysis AI. Based on the following real-time market data for {symbol}, "
            f"provide a trading decision (BUY, SELL, or HOLD). Explain your reasoning. "
            f"Also, provide a confidence score (0.0 to 1.0) for your decision, and if BUY or SELL, "
            f"suggest a stop-loss price and a take-profit price.\n\n"
            f"Market Data for {symbol}:\n"
            f"- Current Price: {last_price}\n"
            f"- Recent Price Trend (last {len(recent_prices_list)} prices, latest first if applicable, or just recent sequence): [{recent_prices_str}]\n" # Added trend
            f"- 20-period SMA: {sma}\n"
            f"- 14-period RSI: {rsi}\n"
            f"- MACD (12,26,9): Line={macd_line}, Signal={macd_signal}, Histogram={macd_histogram}\n"
            f"- Bollinger Bands (20,2): Middle={bb_middle}, Upper={bb_upper}, Lower={bb_lower}\n\n"
            f"Your analysis should consider all these indicators and the recent price trend.\n\n"
            f"Respond *only* with a valid JSON object formatted exactly as follows:\n"
            f'{{"decision": "BUY|SELL|HOLD", "reason": "Your detailed reasoning here.", "confidence_score": <float_0_to_1>, '
            f'"suggested_stop_loss": <float_price_or_null>, "suggested_take_profit": <float_price_or_null>}}\n'
            f"Ensure numbers are actual numbers and use null for SL/TP if not applicable."
        )
        return prompt

    async def _query_single_model(self, prompt, model_name_to_query):
        if not self.api_key: return {"error": "API key not set"}
        try:
            response = await self.client.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={"model": model_name_to_query, "messages": [{"role": "user", "content": prompt}]}
            )
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException:
            return {"error": f"Timeout querying {model_name_to_query}"}
        except httpx.NetworkError as e:
            return {"error": f"Network error querying {model_name_to_query}: {e}"}
        except httpx.HTTPStatusError as e:
            error_body_text = e.response.text[:200] # Limit error body length
            return {"error": f"HTTP {e.response.status_code} querying {model_name_to_query}. Details: {error_body_text}"}
        except Exception as e:
            return {"error": f"Unexpected error querying {model_name_to_query}: {str(e)[:200]}"}

    def _parse_ai_response(self, ai_response_json, symbol, last_price_str, processed_data_for_signal, model_name_queried):
        # This function now parses a single model's response and includes the model name.
        # The merging of processed_data will happen in generate_signal after all responses are gathered.
        try:
            if ai_response_json.get("error"): # Check if it's an error dict from _query_single_model
                print(f"AISignalGenerator: Error from model {model_name_queried}: {ai_response_json['error']}")
                return {"model_name": model_name_queried, "decision": "ERROR", "reason": ai_response_json['error']}

            content_str = ai_response_json['choices'][0]['message']['content']
            if content_str.startswith("```json"): content_str = content_str[7:]
            if content_str.startswith("```"): content_str = content_str[3:]
            if content_str.endswith("```"): content_str = content_str[:-3]
            content_str = content_str.strip()

            signal_json_from_ai = json.loads(content_str)

            decision = signal_json_from_ai.get('decision', 'HOLD').upper()
            reason = signal_json_from_ai.get('reason', 'N/A')
            confidence = signal_json_from_ai.get('confidence_score', 0.5)
            stop_loss = signal_json_from_ai.get('suggested_stop_loss')
            take_profit = signal_json_from_ai.get('suggested_take_profit')

            try: confidence = float(confidence)
            except: confidence = 0.5

            def parse_price(val):
                if val is None: return None
                try: return Decimal(str(val))
                except: return None

            parsed_signal = {
                "model_name": model_name_queried,
                "decision": decision,
                "reason": reason,
                "confidence": confidence,
                "suggested_stop_loss": parse_price(stop_loss),
                "suggested_take_profit": parse_price(take_profit),
                "price_at_signal_generation": parse_price(last_price_str) # Price when AI was queried
            }
            return parsed_signal

        except Exception as e:
            error_info = str(ai_response_json)[:200] # Get first 200 chars of response if parsing fails
            print(f"AISignalGenerator: Error parsing response from {model_name_queried}: {e}. Response: {error_info}...")
            return {"model_name": model_name_queried, "decision": "ERROR", "reason": f"Parsing error: {e}"}


    async def generate_signal(self, processed_data):
        if not self.api_key: print("AISignalGenerator: API key not set."); return None
        if not processed_data or 'last_price' not in processed_data or 'symbol' not in processed_data:
            print("AISignalGenerator: Invalid processed data."); return None

        symbol = processed_data.get('symbol')
        last_price_str = processed_data.get('last_price')
        prompt = self._construct_prompt(processed_data)

        # Query all configured models concurrently
        tasks = [self._query_single_model(prompt, model_name) for model_name in self.model_names_to_query]
        all_responses_json = await asyncio.gather(*tasks)

        parsed_signals_from_models = []
        for i, resp_json in enumerate(all_responses_json):
            model_name = self.model_names_to_query[i]
            parsed = self._parse_ai_response(resp_json, symbol, last_price_str, processed_data, model_name)
            parsed_signals_from_models.append(parsed)

        # Basic Consensus Logic (Primary model's decision is leading)
        primary_signal_parsed = None
        for p_signal in parsed_signals_from_models:
            if p_signal["model_name"] == self.primary_model_name:
                primary_signal_parsed = p_signal
                break

        if not primary_signal_parsed or primary_signal_parsed["decision"] == "ERROR":
            print(f"AISignalGenerator: Primary model {self.primary_model_name} failed or returned error.")
            return None # Or handle fallback if desired

        if primary_signal_parsed["decision"] == "HOLD":
            print(f"AISignalGenerator: Primary model ({self.primary_model_name}) recommends HOLD for {symbol}.")
            return None # No actionable signal for HOLD

        # Consensus details
        agreed_decisions = [s["decision"] for s in parsed_signals_from_models if s["decision"] == primary_signal_parsed["decision"]]
        consensus_count = len(agreed_decisions)
        total_queried = len(self.model_names_to_query)

        # Construct final signal dictionary
        final_signal_dict = {k: v for k, v in processed_data.items()} # Start with all indicators

        # Convert numeric strings in final_signal_dict to Decimals where appropriate
        for key_to_convert in ['sma', 'rsi', 'macd_line', 'macd_signal', 'macd_histogram', 'bb_middle', 'bb_upper', 'bb_lower', 'last_price']:
            if key_to_convert in final_signal_dict:
                try: final_signal_dict[key_to_convert] = Decimal(str(final_signal_dict[key_to_convert]))
                except (InvalidOperation, TypeError, ValueError): pass

        final_signal_dict.update({
            'symbol': symbol,
            'signal_type': primary_signal_parsed["decision"],
            'price': primary_signal_parsed["price_at_signal_generation"], # Price from primary model context
            'confidence': primary_signal_parsed["confidence"], # From primary model
            'reason': primary_signal_parsed["reason"], # From primary model
            'ai_model': self.primary_model_name, # Primary model is the source of the main signal
            'suggested_stop_loss': primary_signal_parsed["suggested_stop_loss"],
            'suggested_take_profit': primary_signal_parsed["suggested_take_profit"],
            'consensus_models_queried': total_queried,
            'consensus_models_agreed': consensus_count,
            'all_ai_responses': parsed_signals_from_models # Store all raw parsed responses for logging/DB
        })

        print(f"AISignalGenerator: Final signal for {symbol}: {primary_signal_parsed['decision']} (Confidence: {primary_signal_parsed['confidence']:.2f}). Consensus: {consensus_count}/{total_queried}.")
        return final_signal_dict

    def process_market_data_for_ai(self, market_data): # Remains largely the same
        if market_data and market_data.get('s') and market_data.get('c'):
            return {
                'symbol': market_data.get('s'), 'last_price': market_data.get('c'),
                'price_change_percent': market_data.get('P'), 'high_price': market_data.get('h'),
                'low_price': market_data.get('l'), 'volume': market_data.get('v'),
                'timestamp': market_data.get('E')
            }
        return None
