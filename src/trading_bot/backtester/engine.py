import asyncio
from collections import deque
from decimal import Decimal, InvalidOperation
import logging
from django.conf import settings
import math
import statistics

# Assuming AISignalGenerator is importable and utils are importable
from trading_bot.ai_signal_generator import AISignalGenerator
from trading_bot.utils import (
    calculate_sma, calculate_rsi, calculate_macd, calculate_bollinger_bands,
)

logger = logging.getLogger('trading_bot.backtester.engine')

class Backtester:
    def __init__(self,
                 historical_data: list[dict],
                 initial_capital: Decimal,
                 commission_pct: Decimal,
                 ai_generator: AISignalGenerator,
                 price_history_len: int = 60,
                 sma_window: int = 20, rsi_window: int = 14,
                 macd_short: int = 12, macd_long: int = 26, macd_signal_period: int = 9,
                 bb_window: int = 20, recent_trend_len: int = 5
                 ):

        self.historical_data = historical_data
        self.initial_capital = initial_capital
        self.commission_pct = commission_pct
        self.ai_generator = ai_generator

        self.price_history_len = price_history_len
        self.sma_window = sma_window; self.rsi_window = rsi_window
        self.macd_short = macd_short; self.macd_long = macd_long; self.macd_signal_period = macd_signal_period
        self.bb_window = bb_window; self.recent_trend_len = recent_trend_len

        self.cash = initial_capital
        self.current_position_qty = Decimal('0')
        self.entry_price = Decimal('0') # Price at which current position was entered
        self.current_stop_loss = None # Decimal, set on position entry
        self.current_take_profit = None # Decimal, set on position entry

        self.trades = [] # List of completed trade dicts
        self.portfolio_value_history = []
        self.price_history_deque = deque(maxlen=self.price_history_len)
        self.backtest_ai_call_delay = float(getattr(settings, 'BACKTEST_AI_CALL_DELAY', 2.0))

        logger.info(f"Backtester initialized. Capital: {self.initial_capital:.2f}. Data Bars: {len(self.historical_data)}")

    async def _update_price_history_and_get_latest(self, bar_data: dict, price_key: str = 'close') -> Decimal | None:
        try:
            price_val_str = bar_data.get(price_key)
            if price_val_str is None: return None
            price = Decimal(str(price_val_str))
            self.price_history_deque.append(price)
            return price
        except (InvalidOperation, TypeError): return None

    def _apply_commission(self, trade_value: Decimal) -> Decimal:
        return trade_value * self.commission_pct

    def _execute_buy(self, bar_data: dict, signal_data: dict):
        if self.current_position_qty > 0: # Already long
            logger.debug(f"Bar {bar_data['timestamp']}: BUY signal received but already in a long position. Holding.")
            return

        trade_price_str = bar_data.get('close')
        if trade_price_str is None: logger.error("BUY execute: 'close' price missing in bar_data."); return

        try:
            trade_price = Decimal(str(trade_price_str))
            trade_qty = Decimal('1') # Fixed quantity
            trade_value = trade_price * trade_qty
            commission = self._apply_commission(trade_value)

            if self.cash >= trade_value + commission:
                self.cash -= (trade_value + commission)
                self.current_position_qty = trade_qty
                self.entry_price = trade_price
                self.current_stop_loss = signal_data.get('suggested_stop_loss')
                self.current_take_profit = signal_data.get('suggested_take_profit')

                logger.info(f"TRADE EXECUTED (BUY): Time={bar_data['timestamp']}, Qty={trade_qty}, Price={trade_price:.4f}, "
                            f"SL={self.current_stop_loss}, TP={self.current_take_profit}, Commission={commission:.4f}, Cash={self.cash:.2f}")
                self.trades.append({
                    "timestamp_entry": bar_data['timestamp'], "type": "BUY", "qty": trade_qty,
                    "entry_price": trade_price, "commission_entry": commission,
                    "stop_loss_initial": self.current_stop_loss, "take_profit_initial": self.current_take_profit,
                    "status": "OPEN"
                })
            else:
                logger.warning(f"Bar {bar_data['timestamp']}: BUY signal - Insufficient cash for trade. Need {trade_value+commission:.2f}, have {self.cash:.2f}")
        except (InvalidOperation, TypeError) as e:
            logger.error(f"Error executing BUY for bar {bar_data['timestamp']}: {e}", exc_info=True)


    def _execute_sell(self, bar_data: dict, signal_data: dict):
        if self.current_position_qty <= 0:
            logger.debug(f"Bar {bar_data['timestamp']}: SELL signal received but not in a long position. No action.")
            return

        trade_price_str = bar_data.get('close')
        if trade_price_str is None: logger.error("SELL execute: 'close' price missing in bar_data."); return

        try:
            trade_price = Decimal(str(trade_price_str))
            trade_qty_to_sell = self.current_position_qty
            trade_value = trade_price * trade_qty_to_sell
            commission = self._apply_commission(trade_value)

            self.cash += (trade_value - commission)

            if self.trades and self.trades[-1]["status"] == "OPEN":
                last_trade = self.trades[-1]
                last_trade["status"] = "CLOSED"
                last_trade["exit_price"] = trade_price
                last_trade["timestamp_exit"] = bar_data['timestamp']
                last_trade["commission_exit"] = commission
                last_trade["reason_exit"] = "AI_Signal"
                pnl = (trade_price - last_trade["entry_price"]) * last_trade["qty"] - (last_trade["commission_entry"] + commission)
                last_trade["pnl"] = pnl
                logger.info(f"TRADE CLOSED (SELL Signal): Time={bar_data['timestamp']}, Qty={trade_qty_to_sell}, Price={trade_price:.4f}, "
                            f"Entry={last_trade['entry_price']:.4f}, PnL={pnl:.2f}, Commission={commission:.4f}, Cash={self.cash:.2f}")
            else:
                 logger.error(f"Bar {bar_data['timestamp']}: Attempted to close position via SELL signal, but no open trade found in log.")

            self.current_position_qty = Decimal('0')
            self.entry_price = Decimal('0')
            self.current_stop_loss = None
            self.current_take_profit = None
        except (InvalidOperation, TypeError) as e:
            logger.error(f"Error executing SELL for bar {bar_data['timestamp']}: {e}", exc_info=True)


    def _close_position_due_to_sl_tp(self, bar_data: dict, exit_price: Decimal, reason: str):
        if self.current_position_qty <= 0:
            logger.error(f"Bar {bar_data['timestamp']}: _close_position_due_to_sl_tp called but no open position.")
            return

        trade_qty_to_close = self.current_position_qty
        trade_value = exit_price * trade_qty_to_close
        commission = self._apply_commission(trade_value)
        self.cash += (trade_value - commission)

        if self.trades and self.trades[-1]["status"] == "OPEN":
            last_trade = self.trades[-1]
            last_trade["status"] = "CLOSED"
            last_trade["exit_price"] = exit_price
            last_trade["timestamp_exit"] = bar_data['timestamp']
            last_trade["commission_exit"] = commission
            last_trade["reason_exit"] = reason
            pnl = (exit_price - last_trade["entry_price"]) * last_trade["qty"] - (last_trade["commission_entry"] + commission)
            last_trade["pnl"] = pnl
            logger.info(f"TRADE CLOSED ({reason}): Time={bar_data['timestamp']}, Qty={trade_qty_to_close}, Price={exit_price:.4f}, "
                        f"Entry={last_trade['entry_price']:.4f}, PnL={pnl:.2f}, Commission={commission:.4f}, Cash={self.cash:.2f}")
        else:
             logger.error(f"Bar {bar_data['timestamp']}: Attempted to close position due to SL/TP, but no open trade found in log.")

        self.current_position_qty = Decimal('0')
        self.entry_price = Decimal('0')
        self.current_stop_loss = None
        self.current_take_profit = None


    def _handle_stop_loss_take_profit(self, bar_data: dict):
        if self.current_position_qty <= 0: return

        bar_low_str = bar_data.get('low')
        bar_high_str = bar_data.get('high')
        if bar_low_str is None or bar_high_str is None:
            logger.warning(f"Bar {bar_data['timestamp']}: Missing low/high price for SL/TP check.")
            return

        try:
            bar_low = Decimal(str(bar_low_str))
            bar_high = Decimal(str(bar_high_str))

            if self.current_stop_loss is not None and bar_low <= self.current_stop_loss:
                logger.info(f"Bar {bar_data['timestamp']}: Stop Loss triggered for long position at {self.current_stop_loss:.4f} (bar low: {bar_low:.4f})")
                self._close_position_due_to_sl_tp(bar_data, self.current_stop_loss, "StopLoss")
                return

            if self.current_take_profit is not None and bar_high >= self.current_take_profit:
                logger.info(f"Bar {bar_data['timestamp']}: Take Profit triggered for long position at {self.current_take_profit:.4f} (bar high: {bar_high:.4f})")
                self._close_position_due_to_sl_tp(bar_data, self.current_take_profit, "TakeProfit")
                return
        except (InvalidOperation, TypeError) as e:
            logger.error(f"Error in SL/TP check for bar {bar_data['timestamp']}: {e}", exc_info=True)


    async def run_backtest(self):
        logger.info("Starting backtest run...")
        if not self.historical_data: logger.warning("No historical data. Exiting."); return
        data_symbol = self.historical_data[0].get('symbol', 'TESTSYMBOL') if self.historical_data else 'TESTSYMBOL'
        self.portfolio_value_history.append({'timestamp': self.historical_data[0]['timestamp'] -1, 'value': self.initial_capital})

        for i, bar in enumerate(self.historical_data):
            current_bar_timestamp_ms = bar['timestamp']
            current_close_price = await self._update_price_history_and_get_latest(bar, 'close')

            if current_close_price is None:
                logger.warning(f"Skipping bar {i} due to invalid price data. TS: {current_bar_timestamp_ms}")
                last_known_price = self.price_history_deque[-1] if self.price_history_deque else self.entry_price if self.current_position_qty > 0 else Decimal(0)
                self.portfolio_value_history.append({'timestamp': current_bar_timestamp_ms, 'value': self.cash + (self.current_position_qty * last_known_price)})
                continue

            if self.current_position_qty > 0:
                self._handle_stop_loss_take_profit(bar)
                if self.current_position_qty == 0:
                    current_position_value = self.current_position_qty * current_close_price
                    current_portfolio_value = self.cash + current_position_value
                    self.portfolio_value_history.append({'timestamp': current_bar_timestamp_ms, 'value': current_portfolio_value})
                    # Continue to AI signal generation for this bar

            processed_data_for_ai = {'symbol': data_symbol, 'last_price': f"{current_close_price:.8f}",
                                     'volume': str(bar.get('volume', '0')), 'high_price': str(bar.get('high', '0')),
                                     'low_price': str(bar.get('low', '0')), 'timestamp': current_bar_timestamp_ms}

            min_len_for_indicators = 1
            if self.sma_window > 0 : min_len_for_indicators = max(min_len_for_indicators, self.sma_window)
            if self.rsi_window > 0 : min_len_for_indicators = max(min_len_for_indicators, self.rsi_window +1)
            if self.macd_long > 0 : min_len_for_indicators = max(min_len_for_indicators, self.macd_long)
            if self.bb_window > 0 : min_len_for_indicators = max(min_len_for_indicators, self.bb_window)

            if len(self.price_history_deque) >= min_len_for_indicators:
                if self.sma_window > 0: sma = calculate_sma(self.price_history_deque, self.sma_window); processed_data_for_ai['sma'] = f"{sma:.8f}" if sma else 'N/A'
                if self.rsi_window > 0: rsi = calculate_rsi(self.price_history_deque, self.rsi_window); processed_data_for_ai['rsi'] = f"{rsi:.2f}" if rsi else 'N/A'
                if self.macd_long > 0:
                    macd_results = calculate_macd(self.price_history_deque, self.macd_short, self.macd_long, self.macd_signal_period)
                    if macd_results:
                        processed_data_for_ai['macd_line'] = f"{macd_results['macd']:.8f}" if macd_results.get('macd') else 'N/A'
                        processed_data_for_ai['macd_signal'] = f"{macd_results['signal']:.8f}" if macd_results.get('signal') else 'N/A'
                        processed_data_for_ai['macd_histogram'] = f"{macd_results['histogram']:.8f}" if macd_results.get('histogram') else 'N/A'
                if self.bb_window > 0:
                    bbands = calculate_bollinger_bands(self.price_history_deque, self.bb_window)
                    if bbands:
                        processed_data_for_ai['bb_middle'] = f"{bbands['middle']:.8f}" if bbands.get('middle') else 'N/A'
                        processed_data_for_ai['bb_upper'] = f"{bbands['upper']:.8f}" if bbands.get('upper') else 'N/A'
                        processed_data_for_ai['bb_lower'] = f"{bbands['lower']:.8f}" if bbands.get('lower') else 'N/A'
                if self.recent_trend_len > 0 and len(self.price_history_deque) >= self.recent_trend_len:
                    trend_prices = list(self.price_history_deque)[-self.recent_trend_len:]
                    processed_data_for_ai['recent_price_trend'] = [f"{p:.8f}" for p in trend_prices]

                signal_dict_from_ai = await self.ai_generator.generate_signal(processed_data_for_ai)
                if self.backtest_ai_call_delay > 0: await asyncio.sleep(self.backtest_ai_call_delay)

                if signal_dict_from_ai:
                    signal_decision = signal_dict_from_ai.get('signal_type')
                    logger.info(f"Bar {i} TS {current_bar_timestamp_ms}: AI Signal={signal_decision}, Px={current_close_price:.4f}, Reason: {signal_dict_from_ai.get('reason', 'N/A')[:50]}...")

                    if signal_decision == 'BUY' and self.current_position_qty == 0: # Only buy if flat
                        self._execute_buy(bar, signal_dict_from_ai)
                    elif signal_decision == 'SELL' and self.current_position_qty > 0: # Only sell if long
                        self._execute_sell(bar, signal_dict_from_ai)
                else:
                    logger.debug(f"Bar {i} TS {current_bar_timestamp_ms}: AI returned no actionable signal.")
            else:
                logger.debug(f"Bar {i} TS {current_bar_timestamp_ms}: Not enough history for indicators.")

            current_position_value = self.current_position_qty * current_close_price
            current_portfolio_value = self.cash + current_position_value
            self.portfolio_value_history.append({'timestamp': current_bar_timestamp_ms, 'value': current_portfolio_value})

        logger.info("Backtest run completed.")
        self.display_results()

    def display_results(self):
        logger.info("--- Backtest Performance Results ---")
        logger.info(f"Data Range: {self.historical_data[0]['timestamp'] if self.historical_data else 'N/A'} to {self.historical_data[-1]['timestamp'] if self.historical_data else 'N/A'}")
        logger.info(f"Initial Capital: {self.initial_capital:.2f}")

        final_portfolio_value = self.portfolio_value_history[-1]['value'] if self.portfolio_value_history else self.initial_capital
        logger.info(f"Final Portfolio Value: {final_portfolio_value:.2f}")

        total_pnl = final_portfolio_value - self.initial_capital
        total_pnl_pct = (total_pnl / self.initial_capital) * 100 if self.initial_capital > 0 else Decimal('0')
        logger.info(f"Total Net PnL: {total_pnl:.2f} ({total_pnl_pct:.2f}%)")

        total_trades = len(self.trades)
        logger.info(f"Total Trades Executed: {total_trades}")

        if total_trades == 0:
            logger.info("No trades were executed during the backtest.")
            return

        profitable_trades = [t for t in self.trades if t.get('pnl', Decimal('0')) > 0]
        losing_trades = [t for t in self.trades if t.get('pnl', Decimal('0')) < 0]
        neutral_trades = [t for t in self.trades if t.get('pnl', Decimal('0')) == 0] # PnL might be exactly 0 after commissions

        num_wins = len(profitable_trades)
        num_losses = len(losing_trades)

        win_rate = (Decimal(num_wins) / Decimal(total_trades)) * 100 if total_trades > 0 else Decimal('0')
        loss_rate = (Decimal(num_losses) / Decimal(total_trades)) * 100 if total_trades > 0 else Decimal('0')
        logger.info(f"Win Rate: {win_rate:.2f}% ({num_wins} wins)")
        logger.info(f"Loss Rate: {loss_rate:.2f}% ({num_losses} losses)")
        if len(neutral_trades) > 0:
            logger.info(f"Neutral Trades (PnL=0): {len(neutral_trades)}")

        total_gross_profit = sum(t.get('pnl', Decimal('0')) for t in profitable_trades)
        total_gross_loss = abs(sum(t.get('pnl', Decimal('0')) for t in losing_trades)) # Sum of absolute losses

        avg_win = (total_gross_profit / Decimal(num_wins)) if num_wins > 0 else Decimal('0')
        avg_loss = (total_gross_loss / Decimal(num_losses)) if num_losses > 0 else Decimal('0')
        logger.info(f"Average Win Amount: {avg_win:.2f}")
        logger.info(f"Average Loss Amount: {avg_loss:.2f}")

        profit_factor = (total_gross_profit / total_gross_loss) if total_gross_loss > 0 else Decimal('inf') # 'inf' if no losses
        logger.info(f"Profit Factor (Gross Profit / Gross Loss): {profit_factor:.2f}")

        # Max Drawdown Calculation (Peak-to-Trough)
        peak = self.initial_capital
        max_drawdown_abs = Decimal('0')
        max_drawdown_pct = Decimal('0')
        for entry in self.portfolio_value_history:
            portfolio_val = entry['value']
            if portfolio_val > peak:
                peak = portfolio_val

            drawdown = peak - portfolio_val # Absolute drawdown from current peak
            if drawdown > max_drawdown_abs:
                max_drawdown_abs = drawdown

            if peak > 0: # Avoid division by zero if peak is 0 (e.g. if initial capital was 0)
                current_drawdown_pct = (drawdown / peak) * 100
                if current_drawdown_pct > max_drawdown_pct:
                    max_drawdown_pct = current_drawdown_pct

        logger.info(f"Max Drawdown: {max_drawdown_abs:.2f} ({max_drawdown_pct:.2f}%)")

        # Simplified Sharpe Ratio (assuming risk-free rate = 0, using std dev of PnL per trade)
        pnl_per_trade = [t.get('pnl', Decimal('0')) for t in self.trades]
        if total_trades > 1: # Need at least 2 trades for standard deviation
            avg_pnl_per_trade = sum(pnl_per_trade) / Decimal(total_trades) # This is total_pnl / total_trades
            # Calculate standard deviation of PnLs
            sum_sq_diff_pnl = sum([(pnl - avg_pnl_per_trade) ** 2 for pnl in pnl_per_trade])
            variance_pnl = sum_sq_diff_pnl / Decimal(total_trades -1) # Sample standard deviation
            std_dev_pnl = variance_pnl.sqrt() if variance_pnl >=0 else Decimal('0')

            sharpe_ratio = (avg_pnl_per_trade / std_dev_pnl) if std_dev_pnl > 0 else Decimal('inf') # 'inf' if no variance in PnL
            logger.info(f"Sharpe Ratio (simplified, per trade PnL, Rf=0): {sharpe_ratio:.3f} (Avg PnL: {avg_pnl_per_trade:.2f}, StdDev PnL: {std_dev_pnl:.2f})")
        else:
            logger.info("Sharpe Ratio: N/A (requires > 1 trade)")

        logger.info("--- End of Results ---")
