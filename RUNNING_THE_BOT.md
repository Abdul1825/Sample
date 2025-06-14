# How to Run the AI Trading Signal Bot

This guide provides step-by-step instructions to set up and run the AI Trading Signal Bot.

## Prerequisites

*   **Python**: Version 3.10 or higher installed.
*   **Git**: Installed for cloning the repository.
*   **Terminal/Command Line**: Basic familiarity.
*   **PostgreSQL Database**: A running PostgreSQL instance. You will need:
    *   Database name
    *   Database user
    *   Database password
    *   Host and port where the database is accessible.
*   **API Keys**:
    *   Telegram Bot Token and Chat ID.
    *   OpenRouter AI API Key.

## Setup Instructions

1.  **Clone the Repository**:
    Open your terminal and clone the project repository:
    \`\`\`bash
    git clone <your_repository_url>
    cd <repository_name>
    \`\`\`
    *(Replace \`<your_repository_url>\` and \`<repository_name>\` with actual values)*

2.  **Navigate to Source Directory**:
    Most commands will be run from the `src` directory where `manage.py` is located.
    \`\`\`bash
    cd src
    \`\`\`

3.  **Create and Activate Virtual Environment (Recommended)**:
    It's highly recommended to use a virtual environment to manage project dependencies.
    \`\`\`bash
    # Create the virtual environment (run from the 'src' directory or project root)
    python -m venv .venv
    # Note: If you create it in root, requirements path below changes slightly.
    # This guide assumes .venv is in the root for consistency with .gitignore.
    # If .venv is in root: cd .. (to root), then python -m venv .venv, then cd src (back to src)

    # Activate the virtual environment:
    # On Windows:
    # ..\.venv\Scripts\activate
    # (If .venv is in root, from src dir. If .venv is in src, then .venv\Scripts\activate)

    # On macOS/Linux:
    # source ../.venv/bin/activate
    # (If .venv is in root, from src dir. If .venv is in src, then source .venv/bin/activate)
    \`\`\`
    *(This guide will assume `.venv` is created in the **project root directory**, one level above `src`)*.
    To create it in root: `cd ..` (if in `src`), then `python -m venv .venv`, then `cd src`.
    To activate from `src` if `.venv` is in root: `source ../.venv/bin/activate` (macOS/Linux) or `..\.venv\Scripts\activate` (Windows).


4.  **Install Dependencies**:
    With your virtual environment activated, and from the `src` directory (assuming `requirements.txt` is in the parent/root directory):
    \`\`\`bash
    pip install -r ../requirements.txt
    \`\`\`

5.  **Configure Environment Variables (`.env` file)**:
    In the **root directory** of the project (alongside `.gitignore` and this `RUNNING_THE_BOT.md` file), create a file named `.env`.
    Copy the following content into it, replacing placeholder values with your actual credentials and settings:

    \`\`\`env
    # Django Settings
    SECRET_KEY='your_strong_random_django_secret_key_here' # Important: Keep this secret!
    DEBUG='True' # Set to 'False' for production

    # Database (PostgreSQL Example)
    DB_NAME='your_db_name'
    DB_USER='your_db_user'
    DB_PASSWORD='your_db_password'
    DB_HOST='localhost' # Or your database server IP/hostname
    DB_PORT='5432'      # Default PostgreSQL port

    # Binance API (Optional for public data streams, required for trading if implemented)
    BINANCE_API_KEY='your_binance_api_key_here'
    BINANCE_API_SECRET='your_binance_api_secret_here'

    # Telegram Bot Configuration
    TELEGRAM_BOT_TOKEN='your_actual_telegram_bot_token'
    TELEGRAM_CHAT_ID='your_actual_telegram_chat_id' # Numeric chat ID

    # OpenRouter AI Configuration
    OPENROUTER_API_KEY='your_actual_openrouter_ai_key'
    OPENROUTER_MODEL_NAME='mistralai/mistral-7b-instruct:free' # Primary AI model
    # Optional secondary/tertiary models for consensus (leave blank or comment out if not used)
    OPENROUTER_MODEL_NAME_2=''
    OPENROUTER_MODEL_NAME_3=''
    \`\`\`

6.  **Database Migrations**:
    From the `src` directory (with virtual environment activated), run Django migrations to set up your database schema:
    \`\`\`bash
    python manage.py migrate --settings=core.settings
    \`\`\`
    *(Ensure your PostgreSQL server is running and accessible with the credentials provided in `.env`)*.

## Running the Bot

1.  **Activate Virtual Environment**: If not already active, activate your virtual environment (see Step 3 in Setup).
2.  **Navigate to `src` Directory**: Ensure your terminal is in the `src` directory.
3.  **Execute the Bot Command**:
    Run the `run_trading_bot` management command:
    \`\`\`bash
    python manage.py run_trading_bot --symbol=BTCUSDT --settings=core.settings
    \`\`\`

    *   `--symbol=BTCUSDT`: Specifies the trading pair to monitor (e.g., `ETHUSDT`, `ADAUSDT`).
    *   `--settings=core.settings`: Explicitly tells Django which settings file to use.

    **Available Command-Line Arguments:**
    You can customize the bot's behavior using these optional arguments:

    *   `--log_file <path>`: Path for the CSV signal log file (default: `logs/trading_signals.csv`).
    *   `--price_history_len <int>`: Max length of the price history deque (default: 60).
    *   `--recent_trend_len <int>`: Number of recent prices for AI trend context (default: 5, 0 to disable).
    *   `--sma_window <int>`: SMA window (default: 20, 0 to disable).
    *   `--rsi_window <int>`: RSI window (default: 14, 0 to disable).
    *   `--macd_short <int>`: MACD short EMA window (default: 12).
    *   `--macd_long <int>`: MACD long EMA window (default: 26, 0 to disable MACD).
    *   `--macd_signal_period <int>`: MACD signal EMA window (default: 9).
    *   `--bb_window <int>`: Bollinger Bands window (default: 20, 0 to disable).

    **Example with custom parameters:**
    \`\`\`bash
    python manage.py run_trading_bot --symbol=ETHUSDT --sma_window=15 --rsi_window=10 --log_file=my_eth_signals.csv --settings=core.settings
    \`\`\`

4.  **Monitoring**:
    The bot will print information to the console, including:
    *   Initialization messages.
    *   Generated signals (if any).
    *   Errors or warnings.
    Signals will also be logged to the specified CSV file, saved to the database, and sent to your configured Telegram chat.

5.  **Stopping the Bot**:
    Press `Ctrl+C` in the terminal where the bot is running. It will attempt a graceful shutdown and print operational statistics.

## Troubleshooting Tips

*   **Dependencies**: Ensure all packages in `requirements.txt` are installed in your active virtual environment.
*   **`.env` File**: Double-check that the `.env` file is in the project **root** directory and all API keys, database credentials, and other settings are correct.
*   **Database Connection**: Verify your PostgreSQL server is running and accessible. Check database logs if connection errors occur.
*   **API Keys**: Ensure your OpenRouter and Telegram API keys are valid and have the necessary permissions.
*   **Python Path/Django Settings**: If `manage.py` commands fail, ensure `DJANGO_SETTINGS_MODULE` is implicitly or explicitly set correctly (our command uses `--settings=core.settings`). Ensure you are in the `src` directory.

---
This document should provide a comprehensive guide to getting the bot up and running.
