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

def format_signal_to_message(signal_data): # signal_data is the dict from AISignalGenerator
    """
    Formats a signal dictionary into a MarkdownV2 string for Telegram.
    Includes AI confidence, SL/TP, and all technical indicators.
    """
    if not signal_data:
        return escape_markdown_v2("No signal data to format.")

    # Helper to format price or return 'N/A', then escape
    def format_price(value, default_precision=8):
        if value is None: return "N/A"
        try:
            # Ensure value is string for Decimal conversion if it's already float/int
            return escape_markdown_v2(f"{Decimal(str(value)):.{default_precision}f}")
        except (InvalidOperation, TypeError, ValueError):
            return escape_markdown_v2(str(value)) # Fallback to string if not Decimal-able

    # Helper to format float (like confidence, RSI) or return 'N/A', then escape
    def format_float(value, precision=2):
        if value is None: return "N/A"
        try:
            return escape_markdown_v2(f"{float(value):.{precision}f}")
        except (ValueError, TypeError):
            return escape_markdown_v2(str(value))

    symbol = escape_markdown_v2(signal_data.get('symbol', 'N/A'))
    signal_type = escape_markdown_v2(signal_data.get('signal_type', 'N/A').upper())
    price_at_signal = format_price(signal_data.get('price')) # Price from AI signal

    ai_model = escape_markdown_v2(signal_data.get('ai_model', 'N/A'))
    ai_confidence = format_float(signal_data.get('confidence', 0.0) * 100, precision=2) + "%" # Display as percentage
    ai_reason = escape_markdown_v2(signal_data.get('reason', 'N/A'))
    stop_loss = format_price(signal_data.get('suggested_stop_loss'))
    take_profit = format_price(signal_data.get('suggested_take_profit'))

    # Technical Indicators from the signal_data (which should now include them)
    sma = format_price(signal_data.get('sma')) # From processed_data merged into signal by run_trading_bot
    rsi = format_float(signal_data.get('rsi'))
    macd_line = format_price(signal_data.get('macd'))
    # macd_signal = format_price(signal_data.get('macd_signal_value')) # If available
    # macd_hist = format_price(signal_data.get('macd_histogram_value')) # If available

    bb_middle = format_price(signal_data.get('bb_middle'))
    bb_upper = format_price(signal_data.get('bb_upper'))
    bb_lower = format_price(signal_data.get('bb_lower'))

    # Header
    header_emoji = "🚀" if signal_type == "BUY" else "🔻" if signal_type == "SELL" else "➡️" # HOLD or other
    message_title = escape_markdown_v2(f"{header_emoji} AI Trading Signal: {signal_type} {symbol} {header_emoji}")

    # Core Signal Info
    core_info = [
        f"*Symbol:* `{symbol}`",
        f"*Type:* `{signal_type}`",
        f"*Signal Price:* `{price_at_signal}`",
        f"*AI Model:* `{ai_model}`",
        f"*Confidence:* `{ai_confidence}`",
    ]
    if stop_loss != "N/A": core_info.append(f"*Suggested SL:* `{stop_loss}`")
    if take_profit != "N/A": core_info.append(f"*Suggested TP:* `{take_profit}`")

    # Technical Indicators Block
    indicators_info = [
        f"*Indicators at Signal:*",
        f"  SMA (20p): `{sma}`", # Assuming 20p, adjust if window is dynamic in message
        f"  RSI (14p): `{rsi}`",
        f"  MACD Line: `{macd_line}`",
        # f"  MACD Signal: `{macd_signal}`", # Uncomment when available
        # f"  MACD Hist: `{macd_hist}`", # Uncomment when available
        f"  BB Middle: `{bb_middle}`",
        f"  BB Upper: `{bb_upper}`",
        f"  BB Lower: `{bb_lower}`",
    ]

    # AI Reasoning
    reasoning_info = [
        f"*AI Reasoning:*",
        f"_{ai_reason}_"
    ]

    disclaimer = f"_Disclaimer: Trading involves risk\. This is an AI\-generated signal, not financial advice\._"

    # Assemble message parts
    message_parts = [
        message_title,
        "", # Newline
        "\n".join(core_info),
        "", # Newline
        "\n".join(indicators_info),
        "", # Newline
        "\n".join(reasoning_info),
        "", # Newline
        disclaimer
    ]

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
