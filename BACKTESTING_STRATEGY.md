# Backtesting Strategy & Design for the AI Trading Signal Bot

This document outlines the strategy, goals, components, and challenges for developing a backtesting framework for the AI Trading Signal Bot.

## 1. Goals of the Backtesting Framework

*   **Strategy Validation**: Test the profitability and effectiveness of the AI-driven signal generation logic (using `AISignalGenerator` with various configurations) on historical market data.
*   **Parameter Optimization**: Experiment with different indicator parameters (SMA window, RSI window, MACD settings, Bollinger Bands settings, etc.) to find optimal configurations.
*   **AI Model Evaluation**: Compare the performance of different AI models (from OpenRouter or other sources) and different prompting strategies.
*   **Risk Assessment**: Analyze risk metrics such as drawdown, Sharpe ratio, Sortino ratio, win/loss rate, average win/loss size.
*   **Confidence Building**: Provide a data-driven way to assess the potential real-world performance of the bot before deploying significant capital (even for paper trading).
*   **Regression Testing**: Ensure that new code changes or AI prompt adjustments do not negatively impact historically profitable strategies.

## 2. Key Components of the Backtesting System

1.  **Historical Data Loader/Manager**:
    *   **Source**: Binance API (for klines/candlestick data: OHLCV). CSV files are used as an intermediate storage.
    *   **Functionality**: A Django management command (`download_historical_data`) fetches, and saves kline data. The backtester loads from these CSVs.
    *   **Status**: Implemented in Phase I.

2.  **Event Simulator / Market Replay Engine (within `Backtester` class)**:
    *   **Functionality**: Iterates through historical kline data (loaded from CSV) bar by bar.
    *   On each new bar, it updates a `price_history_deque` and calculates all technical indicators.
    *   **Status**: Implemented in Phase I.

3.  **Strategy Execution Engine (within `Backtester` class)**:
    *   **Core Logic**: On each bar, takes latest price and indicators, calls `AISignalGenerator` to get a signal.
    *   **AI Call Method**: Currently makes live API calls to OpenRouter, rate-limited by `BACKTEST_AI_CALL_DELAY` setting. This allows testing the *exact same AI logic* as the live bot but can be slow for extensive backtests and incurs API usage if not using free models or exceeding free tiers.
    *   **Status**: Implemented in Phase I.

4.  **Portfolio / Trade Simulator (within `Backtester` class)**:
    *   **Functionality**: Manages simulated account (capital, positions, equity). Simulates market order execution (currently long-only, fixed quantity), accounts for commissions, tracks trades, and handles simulated stop-loss/take-profit orders based on AI suggestions.
    *   **Status**: Implemented in Phase I.

5.  **Performance Metrics Calculator & Reporter (within `Backtester` class)**:
    *   **Functionality**: Calculates and logs key performance indicators (Total P&L, Win Rate, Avg Win/Loss, Profit Factor, Max Drawdown, simplified Sharpe Ratio).
    *   **Status**: Implemented in Phase I.

## 3. Data Sources for Historical Data

*   **Primary**: Binance API (`GET /api/v3/klines`).
*   **Intermediate Storage**: CSV files, managed by the `download_historical_data` command.
*   **Status**: Implemented in Phase I.

## 4. Key Challenges (Updated based on Phase I choices)

*   **Lookahead Bias**: Must be vigilant in indicator calculations and strategy logic to only use data available up to the current bar. (Current implementation aims to respect this).
*   **Survivorship Bias**: If testing multiple symbols, the list of symbols and their historical data needs careful management. (Currently focused on single-symbol backtests via specific data files).
*   **Transaction Costs**: Basic percentage commission is implemented. Slippage is not yet simulated.
*   **AI Call Simulation in Backtests**:
    *   **Current Approach (Phase I)**: Live calls to OpenRouter, rate-limited.
        *   *Pros*: Uses the exact same AI logic as the live bot. Tests current AI model's response to historical scenarios.
        *   *Cons*: Slow for long backtests. Incurs API costs if paid models/tiers are used. Dependent on OpenRouter availability during backtest.
    *   **Future Considerations for AI in Backtesting**:
        *   *Caching AI Responses*: For identical `processed_data_for_ai` inputs, cache and reuse AI responses to speed up re-runs (limited by input variability).
        *   *Snapshotting/Approximating AI Logic*: If AI's behavior can be distilled into a ruleset or a local model after observing its live performance, that ruleset/local model could be used for faster backtests. This is complex.
        *   *Using AI for Strategy Definition, then Backtesting Rules*: Use the live AI to help *define* a trading strategy (e.g., "When RSI < X and MACD crossover happens and AI confirms bullish sentiment, consider BUY"). Then, backtest *that human-defined, AI-assisted strategy* without per-bar AI calls. This is often a practical approach.
*   **Overfitting**: Parameter optimization (e.g., for indicator windows) against historical data can lead to overfitting. Requires out-of-sample testing, walk-forward optimization (future phases).
*   **Computational Resources**: Extensive backtests can be resource-intensive.
*   **Software Complexity**: While Phase I provides a core, further enhancements (e.g., sophisticated order types, portfolio-level risk management, advanced stats) add complexity.

## 5. Phased Implementation Approach (Updated Post-Phase I)

**Phase B-I (Core Engine - COMPLETED)**:
*   Historical data loader command (`download_historical_data`) for Binance (CSV output).
*   `Backtester` class:
    *   Loads data from CSV.
    *   Event simulator (bar-by-bar processing).
    *   Indicator calculations.
    *   Integration with `AISignalGenerator` (live, rate-limited calls).
    *   Basic trade simulation (long-only, fixed quantity, commission, SL/TP from AI).
    *   Portfolio value tracking.
    *   Calculation and console reporting of key performance metrics.
*   Management command (`run_backtest`) to orchestrate backtesting.

**Phase B-II (Enhancements & Usability - FUTURE)**:
*   **Improved Reporting**:
    *   Output results to CSV/JSON/HTML.
    *   Generate charts (equity curve, drawdown). (e.g., using Matplotlib or Plotly, if environment allows).
*   **Advanced Trade Simulation**:
    *   Variable position sizing (e.g., % of equity).
    *   Option for simulating short selling.
    *   More realistic order execution (e.g., different order types, basic slippage model).
*   **Data Handling**: Support for more symbols, timeframes more easily.
*   **Parameter Sweeping**: Basic tools for iterating through different indicator parameters to find optimal sets (caution: overfitting).

**Phase B-III (Advanced Backtesting Features - FUTURE)**:
*   **Walk-Forward Optimization**.
*   **Portfolio-Level Backtesting** (multiple symbols, correlations).
*   Integration with dedicated backtesting libraries if needed for speed/features (e.g., `vectorbt` for vectorized backtesting if strategy allows, or `Backtrader`/`Zipline` for event-driven).
*   More sophisticated statistical analysis of results (e.g., Monte Carlo simulation).

This document will be updated as the backtesting framework evolves.
