# Backtesting Strategy & Design for the AI Trading Signal Bot

This document outlines the strategy, goals, components, and challenges for developing a backtesting framework for the AI Trading Signal Bot. This is a planning document for a future implementation.

## 1. Goals of the Backtesting Framework

*   **Strategy Validation**: Test the profitability and effectiveness of the AI-driven signal generation logic (using `AISignalGenerator` with various configurations) on historical market data.
*   **Parameter Optimization**: Experiment with different indicator parameters (SMA window, RSI window, MACD settings, Bollinger Bands settings, etc.) to find optimal configurations.
*   **AI Model Evaluation**: Compare the performance of different AI models (from OpenRouter or other sources) and different prompting strategies.
*   **Risk Assessment**: Analyze risk metrics such as drawdown, Sharpe ratio, Sortino ratio, win/loss rate, average win/loss size.
*   **Confidence Building**: Provide a data-driven way to assess the potential real-world performance of the bot before deploying significant capital (even for paper trading).
*   **Regression Testing**: Ensure that new code changes or AI prompt adjustments do not negatively impact historically profitable strategies.

## 2. Key Components of the Backtesting System

1.  **Historical Data Loader/Manager**:
    *   **Source**: Binance API (for klines/candlestick data: OHLCV - Open, High, Low, Close, Volume). Other sources could be CSV files or a dedicated market data database.
    *   **Functionality**: Fetch, store, and retrieve historical kline data for specified symbols and timeframes (e.g., 1m, 5m, 15m, 1h, 1d).
    *   **Considerations**: Handling missing data, rate limits from API, data storage format (e.g., Parquet, HDF5, SQL database).

2.  **Event Simulator / Market Replay Engine**:
    *   **Functionality**: Iterates through historical kline data, bar by bar (or tick by tick, if using tick data, though klines are more common for strategy backtesting).
    *   On each new bar, it should:
        *   Update the `price_history_deque` (similar to the live bot).
        *   Calculate all technical indicators based on the historical data up to that bar.

3.  **Strategy Execution Engine**:
    *   **Core Logic**: This module will encapsulate the bot's decision-making process. On each new bar from the Event Simulator:
        *   It takes the latest price and calculated indicators.
        *   It calls the `AISignalGenerator` (or a backtest-compatible version of it) to get a trading signal (BUY, SELL, HOLD).
        *   **Challenge**: Handling AI calls in a backtest. Making live API calls to OpenRouter for each bar in a long backtest would be slow and potentially costly. Solutions:
            *   **Snapshotting AI Logic**: If the AI logic is simple enough (e.g., a fixed ruleset derived from AI insights), implement that directly.
            *   **Caching AI Responses**: For a given set of inputs, if the AI was queried once, cache its response. (Limited utility if inputs are very dynamic).
            *   **Simulating AI**: Develop a simplified model or ruleset that *approximates* the AI's behavior based on previous observations of the live AI. This is complex.
            *   **Batch AI Queries (Less Ideal for True Backtest)**: Collect many data points and send them to AI in batches (not truly sequential).
            *   **Using AI for Strategy Definition, Not Per-Bar Execution**: Use the live AI to define a strategy (e.g., "When RSI < 30 and MACD crossover happens, consider BUY"), then backtest *that defined strategy*. This is often more practical.

4.  **Portfolio / Trade Simulator**:
    *   **Functionality**:
        *   Manages a simulated trading account (initial capital, positions, equity).
        *   When the Strategy Execution Engine generates a BUY or SELL signal:
            *   Simulates placing an order (market order at next bar's open, or current bar's close).
            *   Accounts for (optional) simulated transaction costs (slippage, commissions).
            *   Tracks open positions, entry/exit prices, P&L.
            *   Handles simulated stop-loss and take-profit orders based on the AI's suggestions or fixed rules.
    *   **State**: Needs to maintain current portfolio value, open positions, trade history.

5.  **Performance Metrics Calculator & Reporter**:
    *   **Functionality**: After a backtest run (or periodically), calculates key performance indicators (KPIs).
    *   **Metrics**:
        *   Total P&L, % Gain
        *   Win Rate, Loss Rate
        *   Average Win, Average Loss, Profit Factor
        *   Max Drawdown (absolute and percentage)
        *   Sharpe Ratio, Sortino Ratio
        *   Number of Trades
        *   Average Holding Period
    *   **Reporting**: Output reports in formats like console printout, CSV, HTML, or charts (e.g., equity curve).

## 3. Data Sources for Historical Data

*   **Primary**: Binance API (`GET /api/v3/klines`). Provides OHLCV data for various intervals.
*   **Secondary**:
    *   Downloaded CSV files from exchanges or data vendors.
    *   Dedicated historical data providers (e.g., Tiingo, Polygon.io - often paid).
*   **Storage**: Store downloaded data locally (CSV, Parquet, database) to avoid re-fetching and to ensure consistency.

## 4. Key Challenges

*   **Lookahead Bias**: Ensuring that decisions at any point in the backtest *only* use data that would have been available at that historical moment. This is a very common and subtle pitfall.
*   **Survivorship Bias**: If using historical data for a list of symbols, ensure the list reflects symbols that were actually tradable throughout the backtest period, not just current top symbols.
*   **Transaction Costs**: Accurately simulating slippage and commissions is crucial for realistic P&L.
*   **AI Call Simulation (as discussed above)**: Deciding how to handle the AI's role in a non-live, historical context. This is perhaps the biggest challenge for *this specific bot*.
*   **Overfitting**: Optimizing parameters too closely to the historical data might lead to good backtest results but poor live performance. Need for out-of-sample testing and robustness checks (e.g., walk-forward optimization).
*   **Computational Resources**: Backtesting over long periods or many symbols can be computationally intensive.
*   **Software Complexity**: Building a robust and flexible backtesting framework is a significant software engineering task. Popular Python libraries like `backtrader`, `zipline-reloaded`, `vectorbt` can help but have their own learning curves and might need adaptation for AI integration.

## 5. Phased Implementation Approach (Proposal)

1.  **Phase B1 (Core Engine)**:
    *   Historical data loader for Binance (1 symbol, 1 timeframe).
    *   Simple event simulator (bar-by-bar).
    *   Integrate current `AISignalGenerator` by either:
        *   Allowing it to run (very slow for long backtests due to API calls).
        *   Or, by first running the AI live to generate a set of "rules/conditions" and then coding those rules into the backtester strategy.
    *   Basic portfolio simulator (P&L, number of trades).
    *   Basic console reporting.
2.  **Phase B2 (Metrics & Refinement)**:
    *   Implement comprehensive performance metrics (drawdown, Sharpe, etc.).
    *   Add basic charting (equity curve).
    *   Improve data handling (more symbols, timeframes).
3.  **Phase B3 (Advanced Features)**:
    *   Parameter optimization tools.
    *   Walk-forward analysis.
    *   More realistic simulation of costs and order execution.

This document provides a starting point for discussion and planning the development of a valuable backtesting tool for the AI Trading Signal Bot.
