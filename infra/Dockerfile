# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# Multi-stage production Dockerfile for Real-Time Voice Agent Backend
# Non-root container with least privilege execution
# ---------------------------------------------------------------------------

FROM python:3.11-slim as builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------------------------------------------------------------------------
# Final runtime image
# ---------------------------------------------------------------------------
FROM python:3.11-slim as runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/install/bin:${PATH}" \
    PYTHONPATH="/app" \
    PORT=8000

# Install minimal OS runtime libraries for audio and media processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create dedicated non-root user
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/bash -m appuser

# Copy installed python dependencies from builder
COPY --from=builder /install /install

WORKDIR /app

# Copy application code
COPY backend /app/backend
COPY frontend /app/frontend
COPY infra/migrations /app/migrations

# Set permissions for non-root execution
RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/livez || exit 1

CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

