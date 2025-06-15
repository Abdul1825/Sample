import httpx
import json
import os
from django.conf import settings
from decimal import Decimal, InvalidOperation
import asyncio
import random # For jitter in retries
import logging

logger = logging.getLogger('trading_bot.ai_signal_generator')

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
        self.model_names_to_query = sorted(list(set(self.model_names_to_query)))

        if not self.api_key:
            logger.warning("OPENROUTER_API_KEY not found in settings or environment.")

        self.max_retries = getattr(settings, 'AI_API_MAX_RETRIES', 3)
        self.initial_retry_delay = getattr(settings, 'AI_API_INITIAL_RETRY_DELAY', 5)
        self.max_retry_delay = getattr(settings, 'AI_API_MAX_RETRY_DELAY', 60)

        self.client = httpx.AsyncClient(timeout=60.0)
        self.follow_up_confidence_threshold = Decimal(str(getattr(settings, 'AI_FOLLOW_UP_CONFIDENCE_THRESHOLD', 0.65)))
        logger.info(f"AISignalGenerator initialized. Primary: {self.primary_model_name}. All: {self.model_names_to_query}. Retries: {self.max_retries}. Follow-up threshold: {self.follow_up_confidence_threshold}")

    async def close_client(self):
        await self.client.aclose()

    def _construct_initial_prompt(self, processed_data):
        symbol = processed_data.get('symbol', 'N/A')
        last_price = processed_data.get('last_price', 'N/A')
        sma = processed_data.get('sma', 'N/A'); rsi = processed_data.get('rsi', 'N/A')
        macd_line = processed_data.get('macd_line', 'N/A'); macd_signal = processed_data.get('macd_signal', 'N/A'); macd_histogram = processed_data.get('macd_histogram', 'N/A')
        bb_middle = processed_data.get('bb_middle', 'N/A'); bb_upper = processed_data.get('bb_upper', 'N/A'); bb_lower = processed_data.get('bb_lower', 'N/A')
        recent_prices_list = processed_data.get('recent_price_trend', [])
        recent_prices_str = ", ".join(map(str, recent_prices_list)) if recent_prices_list else "N/A"
        risk_profile_statement = "When formulating your response, including suggested stop-loss and take-profit levels, please assume a 'moderate' risk tolerance."
        prompt = (
            f"You are an expert trading analysis AI. {risk_profile_statement} "
            f"Based on the following real-time market data for {symbol}, provide a trading decision (BUY, SELL, or HOLD). Explain your reasoning in detail. "
            f"Also, provide a confidence score (0.0 to 1.0) for your decision, and if BUY or SELL, suggest a stop-loss price and a take-profit price. "
            f"Finally, please identify the 1-2 technical indicators that most heavily influenced your decision and summarize this in a brief note.\n\n"
            f"Market Data for {symbol}:\n- Current Price: {last_price}\n- Recent Price Trend (last {len(recent_prices_list)} prices): [{recent_prices_str}]\n"
            f"- 20-period SMA: {sma}\n- 14-period RSI: {rsi}\n- MACD (12,26,9): Line={macd_line}, Signal={macd_signal}, Histogram={macd_histogram}\n"
            f"- Bollinger Bands (20,2): Middle={bb_middle}, Upper={bb_upper}, Lower={bb_lower}\n\n"
            f"Your analysis should consider all these indicators and the recent price trend, keeping the moderate risk tolerance in mind.\n\n"
            f"Respond *only* with a valid JSON object formatted exactly as follows:\n"
            f'{{"decision": "BUY|SELL|HOLD", "reason": "Your detailed reasoning here.", "confidence_score": <float_0_to_1>, '
            f'"suggested_stop_loss": <float_price_or_null>, "suggested_take_profit": <float_price_or_null>, '
            f'"key_indicators_note": "Brief note on 1-2 main influential indicators."}}\n'
            f"Ensure numbers are actual numbers and use null for SL/TP if not applicable. The key_indicators_note should be a string."
        )
        return prompt

    def _construct_follow_up_prompt(self, previous_decision, previous_reason, previous_confidence):
        return (
            f"Your previous decision was {previous_decision} with a confidence of {previous_confidence:.2f}. "
            f"The stated reason was: '{previous_reason}'. This confidence is somewhat low. Can you elaborate further on the key factors supporting your decision, "
            f"and also explicitly mention the main counter-arguments or risks you see with this current assessment? "
            f"If your further analysis changes your decision, confidence, SL, or TP, please provide the updated values. "
            f"Respond *only* with a valid JSON object in the same format as before."
        )

    async def _query_single_model(self, messages: list, model_name_to_query: str):
        if not self.api_key: return {"error": "API key not set"}
        current_retry = 0; delay = self.initial_retry_delay; last_exception = None
        while current_retry <= self.max_retries:
            try:
                response = await self.client.post(url="https://openrouter.ai/api/v1/chat/completions", headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}, json={"model": model_name_to_query, "messages": messages})
                response.raise_for_status(); return response.json()
            except httpx.TimeoutException as e: last_exception = e; error_msg = f"Timeout querying {model_name_to_query}"
            except httpx.NetworkError as e: last_exception = e; error_msg = f"Network error querying {model_name_to_query}: {e}"
            except httpx.HTTPStatusError as e:
                last_exception = e; error_body_text = e.response.text[:200]; error_msg = f"HTTP {e.response.status_code} querying {model_name_to_query}. Details: {error_body_text}"
                if 400 <= e.response.status_code < 500 and e.response.status_code not in [429]:
                    logger.warning(f"Client error for {model_name_to_query}: {error_msg}. Not retrying."); return {"error": error_msg, "no_retry": True}
            except json.JSONDecodeError as e: last_exception = e; error_msg = f"JSONDecodeError from {model_name_to_query}: {str(e)[:100]}"
                logger.error(f"{error_msg}. Not retrying."); return {"error": error_msg, "no_retry": True}
            except Exception as e: last_exception = e; error_msg = f"Unexpected error querying {model_name_to_query}: {str(e)[:200]}"

            logger.warning(f"Attempt {current_retry + 1}/{self.max_retries + 1} for {model_name_to_query} failed: {error_msg}")
            current_retry += 1;
            if current_retry > self.max_retries: break
            jitter = random.uniform(0, delay * 0.1); actual_delay = min(delay + jitter, self.max_retry_delay)
            logger.info(f"Retrying API call for {model_name_to_query} in {actual_delay:.2f} seconds...")
            await asyncio.sleep(actual_delay); delay = min(delay * 2, self.max_retry_delay)
        final_error_msg = f"Max retries ({self.max_retries}) exceeded for {model_name_to_query}. Last error: {str(last_exception)[:200]}"
        logger.error(final_error_msg); return {"error": final_error_msg, "max_retries_exceeded": True}

    def _parse_ai_response_content(self, response_content_str: str):
        if response_content_str.startswith("```json"): response_content_str = response_content_str[7:]
        if response_content_str.startswith("```"): response_content_str = response_content_str[3:]
        if response_content_str.endswith("```"): response_content_str = response_content_str[:-3]
        response_content_str = response_content_str.strip(); return json.loads(response_content_str)

    def _extract_signal_from_parsed_json(self, signal_json, model_name, last_price_str_for_signal):
        decision = signal_json.get('decision', 'HOLD').upper(); reason = signal_json.get('reason', 'N/A'); confidence = signal_json.get('confidence_score', 0.5)
        stop_loss = signal_json.get('suggested_stop_loss'); take_profit = signal_json.get('suggested_take_profit'); key_indicators_note = signal_json.get('key_indicators_note', None)
        try: confidence = float(confidence)
        except: confidence = 0.5
        def parse_price(val):
            if val is None: return None
            try: return Decimal(str(val))
            except: return None
        return {"model_name": model_name, "decision": decision, "reason": reason, "confidence": confidence,
                "suggested_stop_loss": parse_price(stop_loss), "suggested_take_profit": parse_price(take_profit),
                "price_at_signal_generation": parse_price(last_price_str_for_signal), "key_indicators_note": key_indicators_note}

    async def generate_signal(self, processed_data):
        if not self.api_key: logger.error("API key not set."); return None
        if not processed_data or 'last_price' not in processed_data or 'symbol' not in processed_data:
            logger.warning("Invalid or incomplete processed data for AI."); return None
        symbol = processed_data.get('symbol'); last_price_str = processed_data.get('last_price')
        initial_prompt_content = self._construct_initial_prompt(processed_data)
        all_models_conversation_history = {}
        tasks = []
        for model_name in self.model_names_to_query:
            messages = [{"role": "user", "content": initial_prompt_content}]; all_models_conversation_history[model_name] = list(messages)
            tasks.append(self._query_single_model(messages, model_name))
        initial_responses_json = await asyncio.gather(*tasks)
        parsed_signals_from_models = []
        primary_model_first_response_parsed = None
        for i, resp_json in enumerate(initial_responses_json):
            model_name = self.model_names_to_query[i]; current_parsed_signal = {"model_name": model_name, "decision": "ERROR", "reason": "Initial query failed or no content"}
            if resp_json and not resp_json.get("error"):
                try:
                    ai_content_str = resp_json['choices'][0]['message']['content']; all_models_conversation_history[model_name].append({"role": "assistant", "content": ai_content_str})
                    parsed_content_json = self._parse_ai_response_content(ai_content_str)
                    current_parsed_signal = self._extract_signal_from_parsed_json(parsed_content_json, model_name, last_price_str)
                except Exception as e: current_parsed_signal["reason"] = f"Error parsing initial response: {e}. Resp: {str(resp_json)[:100]}"; logger.error(current_parsed_signal["reason"], exc_info=True)
            elif resp_json and resp_json.get("error"): current_parsed_signal["reason"] = resp_json.get("error")
            if current_parsed_signal["decision"] == "ERROR": logger.error(f"Error from {model_name} (initial): {current_parsed_signal['reason']}")
            parsed_signals_from_models.append(current_parsed_signal)
            if model_name == self.primary_model_name: primary_model_first_response_parsed = current_parsed_signal

        if primary_model_first_response_parsed and primary_model_first_response_parsed["decision"] not in ["ERROR", "HOLD"] and Decimal(str(primary_model_first_response_parsed.get("confidence", 0.0))) < self.follow_up_confidence_threshold:
            logger.info(f"Primary model confidence {primary_model_first_response_parsed['confidence']:.2f} below threshold {self.follow_up_confidence_threshold}. Asking follow-up.")
            follow_up_prompt_content = self._construct_follow_up_prompt(primary_model_first_response_parsed["decision"], primary_model_first_response_parsed["reason"], primary_model_first_response_parsed["confidence"])
            all_models_conversation_history[self.primary_model_name].append({"role": "user", "content": follow_up_prompt_content})
            follow_up_response_json = await self._query_single_model(all_models_conversation_history[self.primary_model_name], self.primary_model_name)
            if follow_up_response_json and not follow_up_response_json.get("error"):
                try:
                    ai_content_str_fu = follow_up_response_json['choices'][0]['message']['content']; all_models_conversation_history[self.primary_model_name].append({"role": "assistant", "content": ai_content_str_fu})
                    parsed_content_json_fu = self._parse_ai_response_content(ai_content_str_fu)
                    primary_model_first_response_parsed = self._extract_signal_from_parsed_json(parsed_content_json_fu, self.primary_model_name, last_price_str)
                    primary_model_first_response_parsed["reason"] = f"[Follow-up] {primary_model_first_response_parsed['reason']}"
                    for idx, sig in enumerate(parsed_signals_from_models):
                        if sig["model_name"] == self.primary_model_name: parsed_signals_from_models[idx] = primary_model_first_response_parsed; break
                except Exception as e: logger.error(f"Error parsing follow-up for primary model: {e}. Resp: {str(follow_up_response_json)[:100]}", exc_info=True)
            elif follow_up_response_json and follow_up_response_json.get("error"): logger.error(f"API Error from {self.primary_model_name} (follow-up): {follow_up_response_json.get('error')}")

        if not primary_model_first_response_parsed or primary_model_first_response_parsed["decision"] == "ERROR":
            logger.error(f"Primary model {self.primary_model_name} failed or ended with error after potential follow-up."); return None
        if primary_model_first_response_parsed["decision"] == "HOLD":
            logger.info(f"Primary model ({self.primary_model_name}) recommends HOLD for {symbol} after potential follow-up."); return None

        agreed_decisions = [s["decision"] for s in parsed_signals_from_models if s["decision"] == primary_model_first_response_parsed["decision"]]
        consensus_count = len(agreed_decisions); total_queried = len(self.model_names_to_query)
        final_signal_dict = {k: v for k, v in processed_data.items()}
        for key_to_convert in ['sma', 'rsi', 'macd_line', 'macd_signal', 'macd_histogram', 'bb_middle', 'bb_upper', 'bb_lower', 'last_price'] + ['recent_price_trend']:
            if key_to_convert in final_signal_dict:
                if key_to_convert == 'recent_price_trend' and isinstance(final_signal_dict[key_to_convert], list):
                    try: final_signal_dict[key_to_convert] = [Decimal(str(p)) for p in final_signal_dict[key_to_convert]]
                    except: pass
                else:
                    try: final_signal_dict[key_to_convert] = Decimal(str(final_signal_dict[key_to_convert]))
                    except: pass
        final_signal_dict.update({
            'symbol': symbol, 'signal_type': primary_model_first_response_parsed["decision"],
            'price': primary_model_first_response_parsed["price_at_signal_generation"],
            'confidence': primary_model_first_response_parsed["confidence"], 'reason': primary_model_first_response_parsed["reason"],
            'ai_model': self.primary_model_name,
            'suggested_stop_loss': primary_model_first_response_parsed["suggested_stop_loss"],
            'suggested_take_profit': primary_model_first_response_parsed["suggested_take_profit"],
            'key_indicators_note': primary_model_first_response_parsed.get("key_indicators_note"),
            'consensus_models_queried': total_queried, 'consensus_models_agreed': consensus_count,
            'all_ai_responses': all_models_conversation_history
        })
        logger.info(f"Final signal for {symbol}: {final_signal_dict['signal_type']} (Conf: {final_signal_dict['confidence']:.2f}). Consensus: {consensus_count}/{total_queried}.")
        return final_signal_dict

    def process_market_data_for_ai(self, market_data):
        if market_data and market_data.get('s') and market_data.get('c'):
            return {'symbol': market_data.get('s'), 'last_price': market_data.get('c'),
                    'price_change_percent': market_data.get('P'), 'high_price': market_data.get('h'),
                    'low_price': market_data.get('l'), 'volume': market_data.get('v'),
                    'timestamp': market_data.get('E')}
        logger.warning(f"Could not process raw market data: {str(market_data)[:200]}")
        return None
