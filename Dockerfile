# Stage 1: Build frontend
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./

# Vite injects import.meta.env.VITE_* at build time — pass them as ARGs
ARG VITE_TURNSTILE_SITE_KEY
ENV VITE_TURNSTILE_SITE_KEY=$VITE_TURNSTILE_SITE_KEY
ARG VITE_YANDEX_METRIKA_ID
ENV VITE_YANDEX_METRIKA_ID=$VITE_YANDEX_METRIKA_ID

RUN npm run build

# Stage 2: Python backend + built frontend
FROM python:3.13-slim-bookworm

# Install system dependencies (ffmpeg for video processing, opencv deps)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Ensure stripe is installed (separate layer to bypass Docker cache)
RUN pip install --no-cache-dir "stripe>=11.0,<15.0"

# Copy backend code
COPY backend/ ./

# Copy built frontend
COPY --from=frontend-build /app/frontend/dist ./frontend-dist

# Create data directory (will be overridden by persistent volume)
RUN mkdir -p /data/storage

# Default port (Railway overrides via $PORT)
ENV PORT=8000
ENV PYTHONPATH=/app

# Default: web server. Override with "python run_worker.py" for worker mode.
CMD ["bash", "start.sh"]
