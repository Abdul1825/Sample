from django.db import models
from decimal import Decimal # Ensure Decimal is available

class Signal(models.Model):
    symbol = models.CharField(max_length=20)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    signal_type = models.CharField(max_length=10, db_index=True)
    price = models.DecimalField(max_digits=20, decimal_places=8)

    ai_model = models.CharField(max_length=100, null=True, blank=True) # Primary AI model
    ai_confidence_score = models.FloatField(null=True, blank=True)
    ai_reason = models.TextField(null=True, blank=True)
    suggested_stop_loss = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    suggested_take_profit = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)

    # Technical Indicator values
    sma_value = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    rsi_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    macd_value = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    macd_signal_value = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    macd_histogram_value = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    bollinger_upper = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    bollinger_middle = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    bollinger_lower = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)

    # Consensus fields
    consensus_models_queried = models.IntegerField(null=True, blank=True)
    consensus_models_agreed = models.IntegerField(null=True, blank=True)
    raw_ai_responses = models.JSONField(null=True, blank=True) # Stores list of dicts from each AI model
    ai_key_indicators_note = models.TextField(null=True, blank=True) # Note from AI on influential indicators

    # Post-signal price tracking fields
    price_at_plus_5m = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    price_at_plus_15m = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    price_at_plus_30m = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    price_at_plus_1hr = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)

    def __str__(self):
        return f"{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')} - {self.symbol} - {self.signal_type} @ {self.price:.4f} (AI: {self.ai_model or 'N/A'})"

    class Meta:
        ordering = ['-timestamp']

class Trade(models.Model): # Assuming this was the structure of Trade model from plan 1
    signal = models.ForeignKey(Signal, on_delete=models.CASCADE, related_name='trades', null=True, blank=True)
    symbol = models.CharField(max_length=20) # Match Signal's symbol length
    timestamp = models.DateTimeField(auto_now_add=True)
    trade_type = models.CharField(max_length=4) # e.g., BUY, SELL
    price = models.DecimalField(max_digits=20, decimal_places=8)
    quantity = models.DecimalField(max_digits=20, decimal_places=8)
    # Add other relevant fields like status (OPEN, CLOSED), profit/loss, etc. later

    def __str__(self):
        return f"{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')} - {self.trade_type} {self.quantity} {self.symbol} @ {self.price:.4f}"

    class Meta:
        ordering = ['-timestamp']
