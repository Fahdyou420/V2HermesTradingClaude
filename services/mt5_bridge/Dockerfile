FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
 && rm -rf /var/lib/apt/lists/*

# Set working directory inside container
WORKDIR /app

# Install dependencies using system packages override
RUN pip install --break-system-packages --no-cache-dir \
    pyzmq \
    fastapi \
    uvicorn \
    redis \
    python-dotenv \
    aiofiles \
    pydantic

# Copy service and shared code
COPY ./services/shared /app/services/shared
COPY ./services/mt5_bridge /app/services/mt5_bridge

# Expose port
EXPOSE 5558

# Run main module
CMD ["python", "-m", "services.mt5_bridge.main"]
