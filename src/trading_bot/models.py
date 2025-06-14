from django.db import models

class Signal(models.Model):
    symbol = models.CharField(max_length=10)  # e.g., BTCUSDT
    timestamp = models.DateTimeField(auto_now_add=True)
    signal_type = models.CharField(max_length=4)  # e.g., BUY, SELL
    price = models.DecimalField(max_digits=20, decimal_places=8)
    # Add other relevant fields like stop_loss, take_profit, etc. later

    def __str__(self):
        return f"{self.timestamp} - {self.symbol} - {self.signal_type} @ {self.price}"

class Trade(models.Model):
    signal = models.ForeignKey(Signal, on_delete=models.CASCADE, related_name='trades', null=True, blank=True)
    symbol = models.CharField(max_length=10) # Should ideally match the signal's symbol
    timestamp = models.DateTimeField(auto_now_add=True)
    trade_type = models.CharField(max_length=4) # e.g., BUY, SELL
    price = models.DecimalField(max_digits=20, decimal_places=8)
    quantity = models.DecimalField(max_digits=20, decimal_places=8)
    # Add other relevant fields like status (OPEN, CLOSED), profit/loss, etc. later

    def __str__(self):
        return f"{self.timestamp} - {self.trade_type} {self.quantity} {self.symbol} @ {self.price}"
