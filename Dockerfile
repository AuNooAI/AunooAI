# ==============================================================================
# Stage 1: Node.js Builder - Build React UI Components
# ==============================================================================
FROM node:20-slim AS node-builder

WORKDIR /ui-build

# Copy UI source files
COPY ui/package.json ui/package-lock.json* ./

# Install Node.js dependencies
RUN npm ci --prefer-offline --no-audit

# Copy UI source code
COPY ui/ ./

# Build React UI (outputs to build/ directory)
RUN npm run build

# ==============================================================================
# Stage 2: Python Builder - Install Python dependencies
# ==============================================================================
FROM python:3.12-slim AS python-builder

WORKDIR /app

# Install build dependencies for Python packages
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt

# ==============================================================================
# Stage 3: Runtime - Final minimal image
# ==============================================================================
FROM python:3.12-slim

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

# Install only runtime dependencies (no build tools)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        postgresql-client \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from python-builder
COPY --from=python-builder /install /usr/local

# Create necessary directories
RUN mkdir -p \
    app/data \
    app/config \
    templates \
    static \
    static/audio \
    static/trend-convergence \
    static/news-feed-v2 \
    tmp/aunoo_audio \
    reports

# Copy application code (use .dockerignore to exclude unnecessary files)
COPY app/ app/
COPY templates/ templates/
COPY static/ static/
COPY scripts/ scripts/
COPY alembic/ alembic/
COPY alembic.ini .
COPY setup.py .
COPY docker-entrypoint.sh /entrypoint.sh

# Copy built React UI from node-builder
COPY --from=node-builder /ui-build/build/ /app/static/trend-convergence/

# Fix line endings if built on Windows and make executable
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

# Create named volumes for persistent data
VOLUME /app/app/data
VOLUME /app/reports
VOLUME /app/.env_volume
VOLUME /app/app/config

# Set permissions for persistent directories
RUN chmod -R 777 /app/app/data /app/reports /app/static/audio /app/tmp

# Expose the port the app runs on
EXPOSE ${PORT}

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Command to run the application
CMD ["/entrypoint.sh"]
