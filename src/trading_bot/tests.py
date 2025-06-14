from django.test import TestCase
from .models import Signal
from decimal import Decimal
import datetime

class SignalModelTests(TestCase):

    def test_create_signal(self):
        """Test that a Signal object can be created successfully."""
        signal_time = datetime.datetime.now(datetime.timezone.utc)
        signal = Signal.objects.create(
            symbol="BTCUSDT",
            # timestamp will be auto_now_add
            signal_type="BUY",
            price=Decimal("50000.00")
        )
        self.assertEqual(signal.symbol, "BTCUSDT")
        self.assertEqual(signal.signal_type, "BUY")
        self.assertEqual(signal.price, Decimal("50000.00"))
        # Check if timestamp is recent (within a small delta, e.g., 5 seconds)
        self.assertTrue((datetime.datetime.now(datetime.timezone.utc) - signal.timestamp).total_seconds() < 5)
        self.assertTrue(str(signal).startswith(str(signal.timestamp.date()))) # Basic __str__ check
        self.assertTrue("BTCUSDT" in str(signal))
        self.assertTrue("BUY" in str(signal))
        self.assertTrue("50000.00" in str(signal))

# Placeholder for Trade model tests - to be implemented later
# class TradeModelTests(TestCase):
#     pass

# Placeholder for View tests - to be implemented later
# class SignalListViewTests(TestCase):
#     pass


# --- Technical Indicator Utility Tests ---
from .utils import calculate_sma, calculate_ema, calculate_rsi, calculate_macd, calculate_bollinger_bands
from collections import deque
from decimal import Decimal

class TechnicalIndicatorTests(TestCase):
    def setUp(self):
        self.prices_short_deque = deque([Decimal(str(i)) for i in range(1, 6)], maxlen=10) # 1,2,3,4,5
        self.prices_medium_deque = deque([Decimal(str(i)) for i in range(1, 21)], maxlen=30) # 1 to 20
        self.prices_long_deque = deque([Decimal(str(i)) for i in range(1, 51)], maxlen=60) # 1 to 50

    def test_calculate_sma_simple(self):
        sma = calculate_sma(self.prices_short_deque, 5)
        self.assertEqual(sma, Decimal('3')) # (1+2+3+4+5)/5 = 3
        sma_short_window = calculate_sma(self.prices_short_deque, 3) # uses last 3: 3,4,5
        self.assertEqual(sma_short_window, Decimal('4')) # (3+4+5)/3 = 4
        self.assertIsNone(calculate_sma(self.prices_short_deque, 6)) # Window > data length

    def test_calculate_ema_simple(self):
        # EMA needs careful validation, this is a very basic check
        # For stable prices, EMA should be close to the price
        stable_prices = [Decimal('10')] * 20
        ema = calculate_ema(stable_prices, 10)
        self.assertIsNotNone(ema)
        self.assertAlmostEqual(ema, Decimal('10'), places=4)

        # Test with our long deque
        ema_long = calculate_ema(list(self.prices_long_deque), 20) # Use full list for EMA
        self.assertIsNotNone(ema_long)
        # For a linearly increasing series, EMA will lag behind the latest prices
        # For prices 1..50, EMA(20) will be > (50-20+1)/2 + (20-1)/2 = 15+9.5 = 24.5 and < 50
        # print(f"Test EMA (1..50, win=20): {ema_long}") # For manual check: around 40.7
        self.assertTrue(Decimal('35') < ema_long < Decimal('45'))


    def test_calculate_rsi_simple(self):
        # Prices: 10, 11, 12, 13, 14, 15, 14, 13, 12, 11, 10, 9, 8, 7, 6 (15 points for RSI 14)
        rsi_prices = deque([Decimal(str(p)) for p in [10,11,12,13,14,15,14,13,12,11,10,9,8,7,6]], maxlen=20)
        rsi = calculate_rsi(rsi_prices, window=14) # Uses all 15 data points
        self.assertIsNotNone(rsi)
        # print(f"Test RSI: {rsi}") # For manual check, should be < 50
        self.assertTrue(Decimal('25') < rsi < Decimal('40')) # Based on typical online calc for this series

        # All gains (RSI=100)
        all_gains = deque([Decimal(str(i)) for i in range(1, 20)], maxlen=30)
        rsi_100 = calculate_rsi(all_gains, window=14)
        self.assertEqual(rsi_100, Decimal(100))

        # All losses (RSI=0) - Note: our avg_loss check returns 100 if avg_loss is 0.
        # To get RSI near 0, losses must dominate.
        all_losses = deque([Decimal(str(20-i)) for i in range(1, 20)], maxlen=30) # 19,18,...
        rsi_0_ish = calculate_rsi(all_losses, window=14)
        self.assertIsNotNone(rsi_0_ish)
        # print(f"Test RSI all losses: {rsi_0_ish}")
        self.assertTrue(rsi_0_ish < Decimal('1') or rsi_0_ish == Decimal('0'))


    def test_calculate_macd_simple(self):
        # MACD requires longer series for meaningful values
        macd_data = calculate_macd(self.prices_long_deque, 12, 26, 9)
        self.assertIsNotNone(macd_data)
        self.assertIsNotNone(macd_data['macd'])
        # print(f"Test MACD (1..50): {macd_data['macd']}") # For linearly increasing, short EMA > long EMA, so MACD > 0
        self.assertTrue(macd_data['macd'] > Decimal('0'))
        # Signal and histogram are None for now in this basic version
        self.assertIsNone(macd_data['signal'])
        self.assertIsNone(macd_data['histogram'])


    def test_calculate_bollinger_bands_simple(self):
        bands = calculate_bollinger_bands(self.prices_medium_deque, 20, 2) # Use last 20 prices (1..20)
        self.assertIsNotNone(bands)
        # Middle band is SMA(20) of (1..20) = (1+20)/2 = 10.5
        self.assertAlmostEqual(bands['middle'], Decimal('10.5'), places=4)
        self.assertTrue(bands['upper'] > bands['middle'])
        self.assertTrue(bands['lower'] < bands['middle'])
        # print(f"Test Bollinger (1..20): M={bands['middle']}, U={bands['upper']}, L={bands['lower']}")
        # Std Dev for 1..20 is approx 5.766. Upper = 10.5 + 2*5.766 = 21.032. Lower = 10.5 - 2*5.766 = -0.032
        self.assertAlmostEqual(bands['upper'], Decimal('10.5') + Decimal('2') * Decimal('5.766281297'), places=2)
        self.assertAlmostEqual(bands['lower'], Decimal('10.5') - Decimal('2') * Decimal('5.766281297'), places=2)
