# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV DJANGO_SETTINGS_MODULE core.settings # Set default Django settings

# Set work directory
WORKDIR /app

# Install system dependencies (if any, e.g., for psycopg2-binary if not using pre-built wheels)
# RUN apt-get update && apt-get install -y ... && rm -rf /var/lib/apt/lists/*
# For psycopg2-binary, usually no extra system deps are needed if using slim buster/bullseye.

# Install Python dependencies
# Copy only requirements.txt first to leverage Docker cache
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
# This includes src/, manage.py, and any other project files at root needed at runtime
COPY . /app/
# If .env is needed during build (IT SHOULD NOT BE), it would be copied here.
# But it's better to pass runtime env vars.

# The application runs from the src directory for manage.py
# We can adjust WORKDIR or CMD path. Let's keep WORKDIR /app and adjust CMD.
# Default command to run when container starts.
# This can be overridden when running `docker run` or in docker-compose.
# Note: For production, you might want a non-root user.
# RUN addgroup --system app && adduser --system --group app
# USER app

# Default command (example - user should override symbol)
# CMD ["python", "src/manage.py", "run_trading_bot", "--symbol=BTCUSDT", "--settings=core.settings"]
# A better CMD might be just ["python", "src/manage.py"] and then user specifies "run_trading_bot ..."
# Or an entrypoint script that handles migrations then runs the command.
# For now, a simple CMD that can be easily overridden.
CMD ["python", "src/manage.py", "run_trading_bot"]
