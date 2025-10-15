# Use Python 3.12 slim image as base
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Build arguments for app info
ARG APP_VERSION=unknown
ARG APP_GIT_BRANCH=unknown
ARG APP_BUILD_DATE=unknown

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_VERSION=${APP_VERSION} \
    APP_GIT_BRANCH=${APP_GIT_BRANCH} \
    APP_BUILD_DATE=${APP_BUILD_DATE}

# Install system dependencies including PostgreSQL client
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        postgresql-client \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create necessary directories
RUN mkdir -p app/data \
    app/config \
    templates \
    static \
    static/audio \
    tmp \
    tmp/aunoo_audio \
    reports

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application code and other necessary files
COPY app/ app/
COPY templates/ templates/
COPY static/ static/
COPY alembic/ alembic/
COPY alembic.ini .

# Copy setup and entrypoint scripts
COPY setup.py .
COPY docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create named volumes for persistent data
VOLUME /app/app/data
VOLUME /app/reports

# Set permissions for persistent directories
RUN chmod -R 777 /app/app/data /app/reports /app/static/audio /app/tmp

# Expose the port the app runs on
EXPOSE ${PORT}

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Command to run the application
CMD ["/entrypoint.sh"]
