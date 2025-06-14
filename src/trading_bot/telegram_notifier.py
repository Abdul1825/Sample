import telegram
import os
import asyncio
from decimal import Decimal, InvalidOperation

# Attempt to load Django settings
django_settings_loaded = False
try:
    from django.conf import settings
    django_settings_loaded = True
except ImportError:
    # Django settings not available (e.g., running standalone)
    pass

# Load sensitive info: from Django settings if available, else from environment variables
if django_settings_loaded:
    TELEGRAM_BOT_TOKEN = getattr(settings, 'TELEGRAM_BOT_TOKEN', os.environ.get('TELEGRAM_BOT_TOKEN'))
    TELEGRAM_CHAT_ID = getattr(settings, 'TELEGRAM_CHAT_ID', os.environ.get('TELEGRAM_CHAT_ID'))
else:
    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')


async def send_telegram_message(message_text, bot_token=None, chat_id=None):
    """
    Sends a message to a specified Telegram chat.
    """
    token_to_use = bot_token if bot_token else TELEGRAM_BOT_TOKEN
    chat_id_to_use = chat_id if chat_id else TELEGRAM_CHAT_ID

    if not token_to_use:
        print("Error: Telegram Bot Token not provided or found in Django settings or environment.")
        return False
    if not chat_id_to_use:
        print("Error: Telegram Chat ID not provided or found in Django settings or environment.")
        return False

    try:
        bot = telegram.Bot(token=token_to_use)
        await bot.send_message(chat_id=chat_id_to_use, text=message_text, parse_mode=telegram.constants.ParseMode.MARKDOWN_V2)
        print(f"Telegram message sent to chat ID {chat_id_to_use}")
        return True
    except telegram.error.TelegramError as e:
        print(f"Error sending Telegram message: {e}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return False

def escape_markdown_v2(text_to_escape):
    """Helper function to escape text for MarkdownV2 parsing."""
    if not isinstance(text_to_escape, str):
        text_to_escape = str(text_to_escape)
    # List of special characters that need to be escaped
    escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    # Escape each character with a preceding backslash
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

    sma = format_price(signal_data.get('sma'))
    rsi = format_float(signal_data.get('rsi'))
    macd_line = format_price(signal_data.get('macd_line')) # Key from processed_data
    macd_signal_val = format_price(signal_data.get('macd_signal')) # Key from processed_data
    macd_hist = format_price(signal_data.get('macd_histogram')) # Key from processed_data

    bb_middle = format_price(signal_data.get('bb_middle'))
    bb_upper = format_price(signal_data.get('bb_upper'))
    bb_lower = format_price(signal_data.get('bb_lower'))

    # Consensus Info
    queried = signal_data.get('consensus_models_queried', 'N/A')
    agreed = signal_data.get('consensus_models_agreed', 'N/A')
    consensus_str = f"`{agreed}/{queried}`" if queried != 'N/A' else "`N/A`"

    # Recent Price Trend (from processed_data, should be in signal_data now)
    recent_prices_list = signal_data.get('recent_price_trend', []) # List of formatted price strings
    recent_prices_str = escape_markdown_v2(", ".join(recent_prices_list) if recent_prices_list else "N/A")


    header_emoji = "🚀" if signal_type == "BUY" else "🔻" if signal_type == "SELL" else "➡️"
    message_title = escape_markdown_v2(f"{header_emoji} AI Signal: {signal_type} {symbol} {header_emoji}")

    core_info = [
        f"*Symbol:* `{symbol}`", f"*Type:* `{signal_type}`", f"*Signal Price:* `{price_at_signal}`",
        f"*AI Model:* `{ai_model}`", f"*Confidence:* `{ai_confidence}`",
        f"*Consensus (Agree/Query):* {consensus_str}",
    ]
    if stop_loss != "N/A": core_info.append(f"*Suggested SL:* `{stop_loss}`")
    if take_profit != "N/A": core_info.append(f"*Suggested TP:* `{take_profit}`")

    trend_info = [f"*Recent Prices (last {len(recent_prices_list)}):* `[{recent_prices_str}]`"]

    indicators_info = [
        f"*Indicators at Signal:*",
        f"  SMA: `{sma}` | RSI: `{rsi}`",
        f"  MACD: L=`{macd_line}` S=`{macd_signal_val}` H=`{macd_hist}`",
        f"  BBands: M=`{bb_middle}` U=`{bb_upper}` L=`{bb_lower}`",
    ]
    reasoning_info = [f"*AI Reasoning:*", f"_{ai_reason}_"]
    disclaimer = f"_Disclaimer: Trading involves risk\._"

    message_parts = [message_title, "", "\n".join(core_info), "", "\n".join(trend_info), "", "\n".join(indicators_info), "", "\n".join(reasoning_info), "", disclaimer]
    return "\n".join(message_parts).strip()

async def main():
    # This main function now uses the globally defined (settings-aware) tokens/chat_id
    print(f"Attempting to send a test message using token: {TELEGRAM_BOT_TOKEN[:5] if TELEGRAM_BOT_TOKEN else 'None'}... and chat_id: {TELEGRAM_CHAT_ID}")

    test_message_content = "Hello from the Trading Bot Script! This is a *test* message using `MarkdownV2`."
    escaped_test_message = escape_markdown_v2(test_message_content)
    test_message_sent = await send_telegram_message(escaped_test_message) # Uses global tokens by default

    if test_message_sent:
        print("Test message sent successfully.")
    else:
        print("Failed to send test message.")

    sample_signal = {
        'symbol': 'BTC-USDT',
        'signal_type': 'BUY',
        'price': 49000.12345678,
        'confidence': 0.85,
        'reason': 'AI model detected a strong upward trend. RSI < 30. Critical point!'
    }
    formatted_signal_message = format_signal_to_message(sample_signal)
    print("\nFormatted Signal Message:\n", formatted_signal_message)

    signal_message_sent = await send_telegram_message(formatted_signal_message) # Uses global tokens by default
    if signal_message_sent:
        print("Signal message sent successfully.")
    else:
        print("Failed to send signal message.")

if __name__ == "__main__":
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("\nWARNING: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set (checked settings then environment).")
        print("Skipping send_telegram_message tests in __main__ block.")
    else:
        try:
            asyncio.run(main())
        except RuntimeError as e:
            if " asyncio.run() cannot be called from a running event loop" in str(e):
                print("Skipping __main__ due to existing event loop. This is normal in some environments.")
            else:
                raise
