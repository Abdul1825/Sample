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
