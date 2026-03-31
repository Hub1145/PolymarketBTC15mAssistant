FROM python:3.11-slim

WORKDIR /app

# Install system dependencies if needed (e.g., for building some python packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Environment variables can be overridden at runtime
ENV SYMBOL=BTCUSDT
ENV POLL_INTERVAL_MS=1000

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
