FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory inside container
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

# Copy dashboard codebase
COPY . .

# Expose server port
EXPOSE 8080

# Environment variables defaults
ENV PORT=8080
ENV HERMES_RPC_URL=http://host.docker.internal:7778
ENV REDIS_URL=redis://redis:6379
ENV CHROMADB_URL=http://chromadb:8000
ENV OBSIDIAN_VAULT_PATH=/data/obsidian
ENV PAPER_TRADER_URL=http://paper_trader:5561
ENV BACKTESTER_URL=http://backtester:5560

# Run Flask application
CMD ["python", "app.py"]
