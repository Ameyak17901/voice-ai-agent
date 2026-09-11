# Production Dockerfile for Vocode Web Voice Copilot Backend
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    HOST=0.0.0.0

# Install audio dependencies and build tools for miniaudio/sounddevice
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    libsndfile1 \
    portaudio19-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency specifications and embedded vocode-core
COPY requirements.txt .
COPY vocode-core ./vocode-core

# Install dependencies including embedded vocode
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY backend ./backend
COPY run.py .
COPY .env.example .

EXPOSE 8000

CMD ["python", "run.py"]
