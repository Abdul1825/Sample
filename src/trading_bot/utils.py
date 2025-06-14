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
    """
    Calculates MACD Line, Signal Line, and Histogram.
    Requires enough prices in prices_deque to compute all necessary EMAs.
    The EMAs are calculated over the historical price data to derive the MACD line series first.
    Then, an EMA of this MACD line series is calculated to get the signal line.
    """
    required_len_for_long_ema = long_window
    # For EMA of MACD line (signal line), we need at least `signal_window` MACD values.
    # Each MACD value needs `long_window` prices.
    # So, total prices needed = `long_window` (for first MACD value) + `signal_window - 1` (for subsequent MACD values for EMA)
    # However, calculate_ema itself takes a list and calculates EMA based on that list's length.

    if not prices_deque or len(prices_deque) < long_window: # Minimum for the initial EMAs
        # print(f"MACD: Not enough prices. Have {len(prices_deque)}, need {long_window}")
        return None

    prices = list(prices_deque) # Work with a list of Decimals

    try:
        # Calculate Short EMA series and Long EMA series
        # calculate_ema returns the *last* EMA value for the given price series and window.
        # To get a series of EMAs, we need to call it iteratively or adapt it.
        # Let's adapt calculate_ema to optionally return the full series.

        # Temporarily modify calculate_ema to return series for internal MACD use
        def _calculate_ema_series(series_prices: list[Decimal], window: int) -> list[Decimal | None]:
            if not series_prices or len(series_prices) < window:
                return [None] * len(series_prices) # Return None for all if not enough data for first EMA

            multiplier = Decimal(2) / Decimal(window + 1)
            ema_values = [None] * (window - 1) # No EMA for first window-1 periods

            # Initial SMA for the first EMA value
            initial_sma_sum = sum(series_prices[i] for i in range(window))
            current_ema = initial_sma_sum / Decimal(window)
            ema_values.append(current_ema)

            for i in range(window, len(series_prices)):
                current_ema = (series_prices[i] * multiplier) + (current_ema * (Decimal(1) - multiplier))
                ema_values.append(current_ema)
            return ema_values

        ema_short_series = _calculate_ema_series(prices, short_window)
        ema_long_series = _calculate_ema_series(prices, long_window)

        # MACD line series: ema_short - ema_long
        # Both series must have a value (not None) to calculate MACD
        macd_line_series = []
        # Start from long_window - 1 index because that's where ema_long_series gets its first value
        # and ema_short_series will also have a value there if short_window < long_window.
        min_len_for_macd_calc = long_window -1 # index

        if len(prices) <= min_len_for_macd_calc: # Not enough data for even one MACD value
             # print("MACD: Not enough data for even one MACD line value.")
             return None

        for i in range(min_len_for_macd_calc, len(prices)):
            if ema_short_series[i] is not None and ema_long_series[i] is not None:
                macd_line_series.append(ema_short_series[i] - ema_long_series[i])
            else:
                # This implies not enough data from the start of prices for one of the EMAs at this point.
                # Should fill with None to maintain series length if needed, but MACD calculation stops here.
                # For simplicity, if we encounter this, it means earlier EMAs were not possible.
                # However, _calculate_ema_series should fill initial parts with None.
                # Let's assume if one is None, the other might be too, or calculation is invalid.
                # We need a continuous series of MACD values for its EMA (signal line).
                # If there's a gap, the signal line calculation would be problematic.
                # For now, we'll only proceed if we have a continuous recent set of MACD values.
                pass # Will result in shorter macd_line_series if Nones are present early

        if len(macd_line_series) < signal_window: # Not enough MACD line values for its EMA (signal line)
            # print(f"MACD: Not enough MACD line values for signal line. Have {len(macd_line_series)}, need {signal_window}")
            # Return only MACD line if available, others None
            latest_macd_line = macd_line_series[-1] if macd_line_series else None
            return {
                "macd": latest_macd_line,
                "signal": None,
                "histogram": None
            }

        # Calculate Signal Line: EMA of the MACD line series
        # We need the _calculate_ema_series to handle a series of Decimals directly.
        # The existing calculate_ema (non-series) can be used if we want just the *last* signal line value.
        # Let's use the main calculate_ema for the final signal line value from the macd_line_series.

        # Use the main calculate_ema for the signal line (EMA of MACD values)
        # Ensure `calculate_ema` can handle a list of Decimals
        signal_line = calculate_ema(macd_line_series, signal_window)


        latest_macd_line = macd_line_series[-1] if macd_line_series else None # Get the most recent MACD line value

        histogram_value = None
        if latest_macd_line is not None and signal_line is not None:
            histogram_value = latest_macd_line - signal_line

        return {
            "macd": latest_macd_line,
            "signal": signal_line,
            "histogram": histogram_value
        }
    except Exception as e:
        print(f"Error in MACD calculation: {e}")
        import traceback
        traceback.print_exc() # Print full traceback for debugging
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
