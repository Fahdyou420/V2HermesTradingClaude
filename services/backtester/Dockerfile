FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
 && rm -rf /var/lib/apt/lists/*

# Set working directory inside container
WORKDIR /app

# Copy requirements and install
COPY ./services/backtester/requirements.txt /app/requirements.txt
RUN pip install --break-system-packages --no-cache-dir -r /app/requirements.txt

# Copy shared and service codebase
COPY ./services/shared /app/services/shared
COPY ./services/preprocessor /app/services/preprocessor
COPY ./services/backtester /app/services/backtester

# Expose port
EXPOSE 5560

# Start the backtester service process
CMD ["python", "-m", "services.backtester.main"]
