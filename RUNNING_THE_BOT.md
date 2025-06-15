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
    AI_FOLLOW_UP_CONFIDENCE_THRESHOLD='0.65' # (0.0 to 1.0) Threshold for AI follow-up query
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

## Running with Docker (Recommended for Consistency)

Using Docker is recommended for running the bot as it provides a consistent environment and simplifies dependency management.

**Prerequisites for Docker:**
*   Docker Desktop (for Windows/macOS) or Docker Engine (for Linux) installed.
*   Docker Compose (usually included with Docker Desktop, or install separately for Linux).

**Steps to Run with Docker:**

1.  **Ensure `.env` File is Present**:
    Make sure you have a complete `.env` file in the project root directory as described in the "Configure Environment Variables" section above. `docker-compose.yml` is configured to use this file.
    *   **Important for Docker Compose**: Inside your `.env` file, when running services via `docker-compose`, the `DB_HOST` should typically be the service name of your database container (e.g., `DB_HOST=db` as configured in our `docker-compose.yml`). The `docker-compose.yml` provided already sets `DB_HOST: db` in the app service's environment, which will override the value from the `.env` file for that specific variable when running `docker-compose up`.

2.  **Build and Run with Docker Compose**:
    Navigate to the project root directory (where `docker-compose.yml` and `Dockerfile` are located) in your terminal.
    Run the following command:
    \`\`\`bash
    docker-compose up --build
    \`\`\`
    *   `--build`: Forces Docker Compose to rebuild the application image if the `Dockerfile` or application code has changed.
    *   This command will:
        *   Pull the PostgreSQL image if not already present.
        *   Build your trading bot application image based on the `Dockerfile`.
        *   Start both the database container and the application container.
        *   Run Django database migrations automatically (as configured in the `app` service's command in `docker-compose.yml`).
        *   Then, it will start the `run_trading_bot` command with the parameters specified in `docker-compose.yml`.

3.  **Monitoring Dockerized Bot**:
    *   Logs from both the application and the database services will be streamed to your terminal.
    *   You can also view logs for a specific service: `docker-compose logs app` or `docker-compose logs db`.
    *   The application logs (including structured logs from Python's `logging` module) will also be written to the `logs/` directory within the container, which is mounted to `./logs` on your host machine (as per `docker-compose.yml` volumes).

4.  **Stopping Dockerized Bot**:
    *   Press `Ctrl+C` in the terminal where `docker-compose up` is running.
    *   To stop and remove the containers, you can run: `docker-compose down`

5.  **Customizing Bot Parameters with Docker Compose**:
    If you need to change the bot's parameters (like `--symbol` or indicator windows) when using Docker Compose:
    *   **Option 1 (Modify `docker-compose.yml`):** Directly edit the `command` section of the `app` service in your `docker-compose.yml` file. This is good for persistent changes.
    *   **Option 2 (Override Command):** Run `docker-compose run` for ad-hoc commands. This starts a new container.
        \`\`\`bash
        # First, ensure the database is running if not already:
        # docker-compose up -d db
        # Then run the app with a custom command (migrations might need to be run separately or first):
        # docker-compose run --rm app sh -c "python src/manage.py migrate --settings=core.settings && python src/manage.py run_trading_bot --symbol=ETHUSDT --sma_window=15 --settings=core.settings"
        \`\`\`
        The `--rm` flag automatically removes the container when it exits.

## Monitoring Bot Health (Production Considerations)

While this bot primarily runs as a script (Django management command), ensuring its health and continuous operation in a production-like environment requires monitoring. Here are some approaches:

1.  **Process Monitoring**:
    *   **Systemd/Supervisor**: If running on a Linux server directly (not in Docker initially), use a process manager like `systemd` or `Supervisor`. These tools can automatically restart the bot script if it crashes and log its stdout/stderr.
    *   **Docker Restart Policies**: When running with Docker (e.g., via `docker-compose.yml`), you can set restart policies (e.g., `restart: unless-stopped` or `restart: always`) on the `app` service to ensure Docker attempts to restart the container if it exits unexpectedly.

2.  **Log Analysis**:
    *   **Structured Logs**: The bot is configured for structured logging (JSON or detailed text) to files (e.g., `logs/trading_bot.log`). Regularly monitor these logs for:
        *   `ERROR` or `CRITICAL` level messages.
        *   High frequency of `WARNING` messages.
        *   Absence of expected `INFO` messages (e.g., "Successfully connected to WebSocket," "Signal Generated," periodic stats if implemented).
    *   **Log Management Systems**: For production, feed these logs into a centralized log management system (ELK Stack, Grafana Loki, Splunk, etc.) for easier searching, alerting, and dashboarding based on log content.

3.  **Output Monitoring**:
    *   **Telegram Notifications**: If you stop receiving signals on Telegram (and expect them based on market activity), it might indicate an issue.
    *   **Database/CSV Logs**: Check if new signals are being written to the `trading_signals.csv` file and the `trading_bot_signal` table in the database.
    *   **Operational Statistics**: The bot logs operational statistics on shutdown. If run for fixed periods and restarted by a scheduler, these stats can be collected. For continuous operation, periodic logging of stats (a future enhancement) would be more useful.

4.  **Resource Usage**:
    *   Monitor the CPU, memory, and network usage of the bot's process or container. Unusual spikes or sustained high usage might indicate problems or performance bottlenecks. Tools like `htop`, `docker stats`, or system-level monitoring agents can be used.

5.  **Application-Specific "Heartbeat" (Future Enhancement)**:
    *   For more direct health indication from a script:
        *   **Heartbeat File**: The bot could write a timestamp to a known file (e.g., `logs/heartbeat.txt`) every few minutes. An external script or monitoring tool can then check if this timestamp is recent.
        *   **Simple Status Endpoint**: If the Django HTTP server component were ever run alongside the bot (e.g., for an admin interface), a simple `/healthz` HTTP endpoint could be added to check database connectivity or the status of internal components. This is less relevant if only the management command is run.

6.  **External API Status**:
    *   Be aware of the status of external services like Binance and OpenRouter. Downtime or issues on their end will directly impact the bot. Some services provide status pages or APIs.

Effective monitoring is crucial for any system intended to run continuously and reliably. The methods above provide a starting point for ensuring the AI Trading Signal Bot is operating as expected.

## Logging System

The bot now uses Python's built-in `logging` module for more structured and configurable logging, replacing most `print()` statements.

*   **Configuration**: Logging behavior (level, file output, format) is controlled by environment variables set in your `.env` file (see `LOG_LEVEL`, `LOG_TO_FILE`, `LOG_FILE_PATH`, `LOG_FORMATTER_TYPE`) and applied via `src/core/settings.py`.
*   **Log Formats**: Supports plain text and JSON formats. JSON is highly recommended for production as it integrates well with log management systems.
*   **Log Output**:
    *   **Console**: Logs will always appear in your console (or Docker logs).
    *   **File**: If `LOG_TO_FILE=True` (default), logs are also written to the path specified by `LOG_FILE_PATH` (default: `logs/trading_bot.log` in the project root). This is a rotating log file.
*   **Log Content**: Logs include timestamps, log levels, module names, and detailed messages, including error tracebacks for exceptions.

## Troubleshooting Tips

*   **Dependencies**: Ensure all packages in `requirements.txt` are installed in your active virtual environment.
*   **`.env` File**: Double-check that the `.env` file is in the project **root** directory and all API keys, database credentials, and other settings are correct.
*   **Database Connection**: Verify your PostgreSQL server is running and accessible. Check database logs if connection errors occur.
*   **API Keys**: Ensure your OpenRouter and Telegram API keys are valid and have the necessary permissions.
*   **Python Path/Django Settings**: If `manage.py` commands fail, ensure `DJANGO_SETTINGS_MODULE` is implicitly or explicitly set correctly (our command uses `--settings=core.settings`). Ensure you are in the `src` directory.

---
This document should provide a comprehensive guide to getting the bot up and running.
