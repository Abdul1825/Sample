import telegram
import os
import asyncio
from decimal import Decimal, InvalidOperation
import logging

logger = logging.getLogger('trading_bot.telegram_notifier')

# Attempt to load Django settings
django_settings_loaded = False
try:
    from django.conf import settings
    django_settings_loaded = True
except ImportError:
    pass

# Load sensitive info
if django_settings_loaded and hasattr(settings, 'TELEGRAM_BOT_TOKEN'):
    TELEGRAM_BOT_TOKEN = settings.TELEGRAM_BOT_TOKEN
else:
    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

if django_settings_loaded and hasattr(settings, 'TELEGRAM_CHAT_ID'):
    TELEGRAM_CHAT_ID = settings.TELEGRAM_CHAT_ID
else:
    TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')


async def send_telegram_message(message_text, bot_token=None, chat_id=None):
    token_to_use = bot_token if bot_token else TELEGRAM_BOT_TOKEN
    chat_id_to_use = chat_id if chat_id else TELEGRAM_CHAT_ID

    if not token_to_use:
        logger.error("Telegram Bot Token not provided or found in env/settings.")
        return False
    if not chat_id_to_use:
        logger.error("Telegram Chat ID not provided or found in env/settings.")
        return False

    try:
        bot = telegram.Bot(token=token_to_use)
        await bot.send_message(chat_id=chat_id_to_use, text=message_text, parse_mode=telegram.constants.ParseMode.MARKDOWN_V2)
        logger.info(f"Telegram message sent to chat ID {chat_id_to_use}. Length: {len(message_text)}")
        return True
    except telegram.error.TelegramError as e:
        logger.error(f"Error sending Telegram message: {e}", exc_info=True)
        if "token" in str(e).lower(): # Basic check, can be more specific
             logger.warning("Hint: Telegram bot token might be invalid or expired.")
        if "chat not found" in str(e).lower() or "peer id invalid" in str(e).lower():
             logger.warning(f"Hint: Ensure Telegram chat ID {chat_id_to_use} is correct and bot has access.")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending Telegram message: {e}", exc_info=True)
        return False

def escape_markdown_v2(text_to_escape):
    if not isinstance(text_to_escape, str):
        text_to_escape = str(text_to_escape)
    escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    return "".join([f'\\{char}' if char in escape_chars else char for char in text_to_escape])

def format_signal_to_message(signal_data):
    if not signal_data: return escape_markdown_v2("No signal data to format.")

    def format_price(value, default_precision=8):
        if value is None: return "N/A"
        try: return escape_markdown_v2(f"{Decimal(str(value)):.{default_precision}f}")
        except: return escape_markdown_v2(str(value))
    def format_float(value, precision=2):
        if value is None: return "N/A"
        try: return escape_markdown_v2(f"{float(value):.{precision}f}")
        except: return escape_markdown_v2(str(value))

    symbol = escape_markdown_v2(signal_data.get('symbol', 'N/A'))
    signal_type = escape_markdown_v2(signal_data.get('signal_type', 'N/A').upper())
    price_at_signal = format_price(signal_data.get('price'))
    ai_model = escape_markdown_v2(signal_data.get('ai_model', 'N/A'))
    ai_confidence = format_float(signal_data.get('confidence', 0.0) * 100, precision=2) + "%"
    ai_reason = escape_markdown_v2(signal_data.get('reason', 'N/A'))
    stop_loss = format_price(signal_data.get('suggested_stop_loss'))
    take_profit = format_price(signal_data.get('suggested_take_profit'))
    key_indicators_note = escape_markdown_v2(signal_data.get('key_indicators_note', 'N/A'))

    sma = format_price(signal_data.get('sma'))
    rsi = format_float(signal_data.get('rsi'))
    macd_line = format_price(signal_data.get('macd_line'))
    macd_signal_val = format_price(signal_data.get('macd_signal'))
    macd_hist = format_price(signal_data.get('macd_histogram'))

    bb_middle = format_price(signal_data.get('bb_middle'))
    bb_upper = format_price(signal_data.get('bb_upper'))
    bb_lower = format_price(signal_data.get('bb_lower'))

    queried = signal_data.get('consensus_models_queried', 'N/A')
    agreed = signal_data.get('consensus_models_agreed', 'N/A')
    consensus_str = f"`{agreed}/{queried}`" if queried != 'N/A' and agreed != 'N/A' else "`N/A`"

    recent_prices_list = signal_data.get('recent_price_trend', [])
    recent_prices_str = escape_markdown_v2(", ".join(map(str,recent_prices_list)) if recent_prices_list else "N/A")


    header_emoji = "🚀" if signal_type == "BUY" else "🔻" if signal_type == "SELL" else "➡️"
    message_title = escape_markdown_v2(f"{header_emoji} AI Signal: {signal_type} {symbol} {header_emoji}")

    core_info = [
        f"*Symbol:* `{symbol}`", f"*Type:* `{signal_type}`", f"*Signal Price:* `{price_at_signal}`",
        f"*AI Model:* `{ai_model}`", f"*Confidence:* `{ai_confidence}`",
        f"*Consensus (Agree/Total):* {consensus_str}",
    ]
    if stop_loss != "N/A": core_info.append(f"*Suggested SL:* `{stop_loss}`")
    if take_profit != "N/A": core_info.append(f"*Suggested TP:* `{take_profit}`")

    trend_info = [f"*Recent Prices (last {len(recent_prices_list)}):* `[{recent_prices_str}]`"] if recent_prices_list and recent_prices_str != "N/A" else []

    indicators_info = [
        f"*Indicators at Signal:*",
        f"  SMA: `{sma}` | RSI: `{rsi}`",
        f"  MACD: L=`{macd_line}` S=`{macd_signal_val}` H=`{macd_hist}`",
        f"  BBands: M=`{bb_middle}` U=`{bb_upper}` L=`{bb_lower}`",
    ]
    # Only include key indicators note if it's not N/A
    key_indicators_section = [f"*Key Indicators Note:* _{key_indicators_note}_"] if key_indicators_note != "N/A" else []

    reasoning_info = [f"*AI Reasoning:*", f"_{ai_reason}_"]
    disclaimer = f"_Disclaimer: Trading involves risk\._"

    message_parts = [message_title, "", "\n".join(core_info)]
    if trend_info: message_parts.extend(["", "\n".join(trend_info)])
    message_parts.extend(["", "\n".join(indicators_info)])
    if key_indicators_section: message_parts.extend(["", "\n".join(key_indicators_section)])
    message_parts.extend(["", "\n".join(reasoning_info), "", disclaimer])

    return "\n".join(message_parts).strip()

async def main():
    logger.debug(f"Attempting to send a test message using token: {TELEGRAM_BOT_TOKEN[:5] if TELEGRAM_BOT_TOKEN else 'None'}... and chat_id: {TELEGRAM_CHAT_ID}")
    test_message_content = "Hello from the Trading Bot Script! This is a *test* message using `MarkdownV2`."
    escaped_test_message = escape_markdown_v2(test_message_content)
    test_message_sent = await send_telegram_message(escaped_test_message)
    if test_message_sent: logger.info("Test Telegram message sent successfully.")
    else: logger.error("Failed to send test Telegram message.")

    sample_signal = {
        'symbol': 'BTC-USDT', 'signal_type': 'BUY', 'price': Decimal('49000.12345678'),
        'confidence': 0.85, 'reason': 'AI model detected a strong upward trend. RSI < 30.',
        'ai_model': 'TestModel v1', 'suggested_stop_loss': Decimal('48000'), 'suggested_take_profit': Decimal('51000'),
        'sma': Decimal('48500.00000000'), 'rsi': Decimal('28.50'),
        'macd_line': Decimal('150.0'), 'macd_signal': Decimal('120.0'), 'macd_histogram': Decimal('30.0'),
        'bb_middle': Decimal('48000'), 'bb_upper': Decimal('49500'), 'bb_lower': Decimal('46500'),
        'recent_price_trend': [Decimal('48800'), Decimal('48900'), Decimal('49000.12345678')],
        'consensus_models_queried': 3, 'consensus_models_agreed': 2,
        'key_indicators_note': 'RSI oversold and MACD bullish crossover.'
    }
    formatted_signal_message = format_signal_to_message(sample_signal)
    logger.debug(f"Formatted Signal Message for Telegram:\n{formatted_signal_message}")
    signal_message_sent = await send_telegram_message(formatted_signal_message)
    if signal_message_sent: logger.info("Test signal Telegram message sent successfully.")
    else: logger.error("Failed to send test signal Telegram message.")

if __name__ == "__main__":
    if not logging.getLogger('trading_bot.telegram_notifier').handlers:
        logging.basicConfig(level=logging.DEBUG, format='%(levelname)s %(asctime)s %(name)s - %(message)s')

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set for standalone notifier test.")
        logger.info("Skipping send_telegram_message tests in notifier's __main__ block.")
    else:
        try:
            asyncio.run(main())
        except RuntimeError as e:
            if " asyncio.run() cannot be called from a running event loop" in str(e):
                logger.info("Skipping __main__ due to existing event loop. This is normal in some environments.")
            else:
                raise
