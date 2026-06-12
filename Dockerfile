FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
 && rm -rf /var/lib/apt/lists/*

# Set working directory inside container
WORKDIR /app

# Install standard Hermes agent packages using system packages override
RUN pip install --break-system-packages --no-cache-dir \
    redis \
    chromadb \
    pyzmq \
    flask \
    htmx \
    pydantic \
    pyyaml \
    requests \
    openai \
    websockets \
    numpy \
    pandas

# Copy codebase
COPY . .

# Default system command
CMD ["python"]
