# Multi-stage build for optimized image size
# Stage 1: Builder - Install dependencies and compile
FROM python:3.12-slim AS builder

WORKDIR /build

# Install only necessary build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .

# Create virtual environment and install dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install dependencies with optimizations
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime - Minimal image with only runtime dependencies
FROM python:3.12-slim

# Build arguments for app info
ARG APP_VERSION=unknown
ARG APP_GIT_BRANCH=unknown
ARG APP_BUILD_DATE=unknown

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_VERSION=${APP_VERSION} \
    APP_GIT_BRANCH=${APP_GIT_BRANCH} \
    APP_BUILD_DATE=${APP_BUILD_DATE} \
    PATH="/opt/venv/bin:$PATH"

# Install only runtime dependencies (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    postgresql-client \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Set working directory
WORKDIR /app

# Create necessary directories with appropriate permissions
RUN mkdir -p \
    app/data \
    app/config \
    templates \
    static \
    static/audio \
    tmp/aunoo_audio \
    reports \
    && chmod -R 755 /app

# Copy application code and necessary files
COPY app/ app/
COPY templates/ templates/
COPY static/ static/
COPY alembic/ alembic/
COPY alembic.ini .
COPY setup.py .
COPY docker-entrypoint.sh /entrypoint.sh

# Make entrypoint executable
RUN chmod +x /entrypoint.sh

# Create named volumes for persistent data
VOLUME ["/app/app/data", "/app/reports"]

# Set permissions for persistent directories
RUN chmod -R 777 /app/app/data /app/reports /app/static/audio /app/tmp

# Expose the port the app runs on (default 8080)
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8080}/health || exit 1

# Run as non-root user for security (optional but recommended)
# RUN useradd -m -u 1000 aunoo && chown -R aunoo:aunoo /app
# USER aunoo

# Command to run the application
ENTRYPOINT ["/entrypoint.sh"]
