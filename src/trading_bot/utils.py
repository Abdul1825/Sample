from collections import deque
from decimal import Decimal, InvalidOperation

def calculate_sma(prices_deque: deque, window: int) -> Decimal | None:
    """Calculates the Simple Moving Average (SMA) from a deque of prices."""
    if not prices_deque or len(prices_deque) < window:
        return None
    try:
        relevant_prices = list(prices_deque)[-window:]
        sum_of_prices = sum(Decimal(str(p)) for p in relevant_prices)
        return sum_of_prices / Decimal(window)
    except InvalidOperation:
        print("Error: Non-numeric value encountered in SMA calculation.")
        return None
    except Exception as e:
        print(f"Error calculating SMA: {e}")
        return None

def update_price_history(price_str: str, price_history_deque: deque):
    """Adds a new price to the deque. Converts to Decimal."""
    try:
        price = Decimal(price_str)
        price_history_deque.append(price)
    except InvalidOperation:
        print(f"Warning: Could not convert price '{price_str}' to Decimal. Not adding to history.")


# --- Advanced Technical Indicators ---

def calculate_ema(prices: list[Decimal], window: int) -> Decimal | None:
    """Calculates the Exponential Moving Average (EMA)."""
    if not prices or len(prices) < window:
        return None
    # prices should be a list of Decimals
    # For EMA, the first value is a simple SMA
    # EMA_today = (Price_today * Multiplier) + EMA_yesterday * (1 - Multiplier)
    # Multiplier = 2 / (Window + 1)

    multiplier = Decimal(2) / Decimal(window + 1)

    # Initial SMA for the first EMA value
    initial_sma_prices = prices[:window]
    if len(initial_sma_prices) < window: # Should not happen if outer check is fine
        return None

    try:
        ema = sum(initial_sma_prices) / Decimal(window) # First EMA is an SMA

        # Apply EMA formula for the rest of the prices
        for i in range(window, len(prices)):
            ema = (prices[i] * multiplier) + (ema * (Decimal(1) - multiplier))
        return ema
    except (InvalidOperation, TypeError) as e:
        print(f"Error calculating EMA: {e}. Ensure prices are Decimal.")
        return None


def calculate_rsi(prices_deque: deque, window: int = 14) -> Decimal | None:
    """Calculates the Relative Strength Index (RSI)."""
    if not prices_deque or len(prices_deque) <= window: # Need at least window + 1 prices for gains/losses
        return None

    prices = list(prices_deque) # Work with a list copy
    # Calculate price changes (gains and losses)
    gains = []
    losses = []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        if change > 0:
            gains.append(change)
            losses.append(Decimal(0))
        else:
            losses.append(abs(change))
            gains.append(Decimal(0))

    if len(gains) < window: # Not enough data points for the first average gain/loss
        return None

    # Calculate average gain and average loss for the first period
    # Simple Moving Average for the first set of gains/losses
    avg_gain = sum(gains[:window]) / Decimal(window)
    avg_loss = sum(losses[:window]) / Decimal(window)

    # Smooth the average gain and loss for subsequent periods
    for i in range(window, len(gains)):
        avg_gain = (avg_gain * (window - 1) + gains[i]) / Decimal(window)
        avg_loss = (avg_loss * (window - 1) + losses[i]) / Decimal(window)

    if avg_loss == Decimal(0): # Avoid division by zero if all losses are zero
        return Decimal(100) # RSI is 100 if no losses

    rs = avg_gain / avg_loss
    rsi = Decimal(100) - (Decimal(100) / (Decimal(1) + rs))
    return rsi


def calculate_macd(prices_deque: deque, short_window: int = 12, long_window: int = 26, signal_window: int = 9) -> dict[str, Decimal | None] | None:
    """Calculates MACD, Signal Line, and Histogram."""
    if not prices_deque or len(prices_deque) < long_window: # Need enough prices for the longest EMA
        return None

    prices = list(prices_deque) # Work with a list of Decimals

    try:
        ema_short = calculate_ema(prices, short_window)
        ema_long = calculate_ema(prices, long_window)

        if ema_short is None or ema_long is None:
            return None # Not enough data for EMAs

        macd_line = ema_short - ema_long

        # To calculate the signal line, we need a history of MACD line values
        # This basic implementation can't do that directly from just prices_deque for signal line's EMA.
        # A more advanced implementation would store MACD values over time.
        # For this version, we'll return None for signal and histogram if we can't calculate them here.
        # OR, as a simplification for this step, we'll calculate signal line if we had enough historical MACD values.
        # This function is called with the latest prices_deque. We cannot easily get historical MACD values from it.
        # So, for now, signal_line and histogram will be None.
        # TODO: Refactor to allow MACD history for signal line calculation or accept MACD history.

        # For a full MACD implementation, you'd typically maintain a list of MACD values
        # and then calculate an EMA of those MACD values for the signal line.
        # For now, returning what we can:
        return {
            "macd": macd_line,
            "signal": None, # Placeholder: requires MACD history
            "histogram": None # Placeholder: requires MACD and signal
        }
    except Exception as e:
        print(f"Error in MACD calculation: {e}")
        return None


def calculate_bollinger_bands(prices_deque: deque, window: int = 20, num_std_dev: int = 2) -> dict[str, Decimal | None] | None:
    """Calculates Bollinger Bands (Middle, Upper, Lower)."""
    if not prices_deque or len(prices_deque) < window:
        return None

    prices_for_window = list(prices_deque)[-window:] # Use the most recent 'window' prices

    try:
        # Middle Band: Simple Moving Average
        middle_band = sum(prices_for_window) / Decimal(window)

        # Standard Deviation
        sum_sq_diff = sum([(price - middle_band) ** 2 for price in prices_for_window])
        variance = sum_sq_diff / Decimal(window)
        std_dev = variance.sqrt() # Decimal.sqrt()

        upper_band = middle_band + (Decimal(num_std_dev) * std_dev)
        lower_band = middle_band - (Decimal(num_std_dev) * std_dev)

        return {
            "middle": middle_band,
            "upper": upper_band,
            "lower": lower_band
        }
    except Exception as e:
        print(f"Error in Bollinger Bands calculation: {e}")
        return None
