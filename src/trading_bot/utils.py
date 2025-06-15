import logging
from collections import deque
from decimal import Decimal, InvalidOperation
import traceback

logger = logging.getLogger('trading_bot.utils')

def calculate_sma(prices_deque: deque, window: int) -> Decimal | None:
    """Calculates the Simple Moving Average (SMA) from a deque of prices."""
    if not prices_deque or len(prices_deque) < window:
        return None
    try:
        relevant_prices = list(prices_deque)[-window:]
        sum_of_prices = sum(Decimal(str(p)) for p in relevant_prices)
        return sum_of_prices / Decimal(window)
    except InvalidOperation:
        logger.error("Non-numeric value in SMA calculation.", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Error calculating SMA: {e}", exc_info=True)
        return None

def update_price_history(price_str: str, price_history_deque: deque):
    """Adds a new price to the deque. Converts to Decimal."""
    try:
        price = Decimal(price_str)
        price_history_deque.append(price)
    except InvalidOperation:
        logger.warning(f"Could not convert price '{price_str}' to Decimal. Not adding to history.")

# --- Advanced Technical Indicators ---

def calculate_ema(prices: list[Decimal], window: int) -> Decimal | None:
    """Calculates the Exponential Moving Average (EMA)."""
    if not prices or len(prices) < window:
        return None
    multiplier = Decimal(2) / Decimal(window + 1)
    initial_sma_prices = prices[:window]
    if len(initial_sma_prices) < window:
        return None
    try:
        ema = sum(initial_sma_prices) / Decimal(window)
        for i in range(window, len(prices)):
            ema = (prices[i] * multiplier) + (ema * (Decimal(1) - multiplier))
        return ema
    except (InvalidOperation, TypeError) as e:
        logger.error(f"Error calculating EMA: {e}. Ensure prices are Decimal.", exc_info=True)
        return None

def calculate_rsi(prices_deque: deque, window: int = 14) -> Decimal | None:
    """Calculates the Relative Strength Index (RSI)."""
    if not prices_deque or len(prices_deque) <= window:
        return None
    prices = list(prices_deque)
    gains = []
    losses = []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        if change > 0:
            gains.append(change); losses.append(Decimal(0))
        else:
            losses.append(abs(change)); gains.append(Decimal(0))
    if len(gains) < window: return None
    try:
        avg_gain = sum(gains[:window]) / Decimal(window)
        avg_loss = sum(losses[:window]) / Decimal(window)
        for i in range(window, len(gains)):
            avg_gain = (avg_gain * (window - 1) + gains[i]) / Decimal(window)
            avg_loss = (avg_loss * (window - 1) + losses[i]) / Decimal(window)
        if avg_loss == Decimal(0): return Decimal(100)
        rs = avg_gain / avg_loss
        rsi = Decimal(100) - (Decimal(100) / (Decimal(1) + rs))
        return rsi
    except Exception as e: # Catch any other unexpected error
        logger.error(f"Error calculating RSI: {e}", exc_info=True)
        return None


def calculate_macd(prices_deque: deque, short_window: int = 12, long_window: int = 26, signal_window: int = 9) -> dict[str, Decimal | None] | None:
    if not prices_deque or len(prices_deque) < long_window:
        return None
    prices = list(prices_deque)
    try:
        def _calculate_ema_series(series_prices: list[Decimal], window: int) -> list[Decimal | None]:
            if not series_prices or len(series_prices) < window:
                return [None] * len(series_prices)
            multiplier = Decimal(2) / Decimal(window + 1)
            ema_values = [None] * (window - 1)
            initial_sma_sum = sum(series_prices[i] for i in range(window))
            current_ema = initial_sma_sum / Decimal(window)
            ema_values.append(current_ema)
            for i in range(window, len(series_prices)):
                current_ema = (series_prices[i] * multiplier) + (current_ema * (Decimal(1) - multiplier))
                ema_values.append(current_ema)
            return ema_values

        ema_short_series = _calculate_ema_series(prices, short_window)
        ema_long_series = _calculate_ema_series(prices, long_window)
        macd_line_series = []
        min_len_for_macd_calc = long_window -1
        if len(prices) <= min_len_for_macd_calc: return None
        for i in range(min_len_for_macd_calc, len(prices)):
            if ema_short_series[i] is not None and ema_long_series[i] is not None:
                macd_line_series.append(ema_short_series[i] - ema_long_series[i])
        if len(macd_line_series) < signal_window:
            latest_macd_line = macd_line_series[-1] if macd_line_series else None
            return {"macd": latest_macd_line, "signal": None, "histogram": None}
        signal_line = calculate_ema(macd_line_series, signal_window) # Use the main calculate_ema
        latest_macd_line = macd_line_series[-1] if macd_line_series else None
        histogram_value = None
        if latest_macd_line is not None and signal_line is not None:
            histogram_value = latest_macd_line - signal_line
        return {"macd": latest_macd_line, "signal": signal_line, "histogram": histogram_value}
    except Exception as e:
        logger.error(f"Error in MACD calculation: {e}", exc_info=True)
        return None

def calculate_bollinger_bands(prices_deque: deque, window: int = 20, num_std_dev: int = 2) -> dict[str, Decimal | None] | None:
    if not prices_deque or len(prices_deque) < window:
        return None
    prices_for_window = list(prices_deque)[-window:]
    try:
        middle_band = sum(prices_for_window) / Decimal(window)
        sum_sq_diff = sum([(price - middle_band) ** 2 for price in prices_for_window])
        variance = sum_sq_diff / Decimal(window)
        std_dev = variance.sqrt()
        upper_band = middle_band + (Decimal(num_std_dev) * std_dev)
        lower_band = middle_band - (Decimal(num_std_dev) * std_dev)
        return {"middle": middle_band, "upper": upper_band, "lower": lower_band}
    except Exception as e:
        logger.error(f"Error in Bollinger Bands calculation: {e}", exc_info=True)
        return None
