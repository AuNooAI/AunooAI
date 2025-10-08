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

# Copy setup script
COPY setup.py .

# Create named volumes for persistent data
VOLUME /app/app/data
VOLUME /app/reports

# Set permissions for persistent directories
RUN chmod -R 777 /app/app/data /app/reports /app/static/audio /app/tmp

# Create entrypoint script
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
# Create instance directory\n\
mkdir -p /app/app/data/${INSTANCE}\n\
\n\
# Setup .env file\n\
if [ ! -f /app/app/data/${INSTANCE}/.env ]; then\n\
  echo "Creating new .env file for instance: ${INSTANCE}"\n\
  touch /app/app/data/${INSTANCE}/.env\n\
  chmod 666 /app/app/data/${INSTANCE}/.env\n\
  \n\
  # Set default environment variables\n\
  cat > /app/app/data/${INSTANCE}/.env <<EOF\n\
PORT=${PORT}\n\
ENVIRONMENT=${ENVIRONMENT:-development}\n\
DISABLE_SSL=true\n\
EOF\n\
fi\n\
\n\
# Link .env file\n\
ln -sf /app/app/data/${INSTANCE}/.env /app/.env\n\
\n\
# Add database configuration from environment if provided\n\
if [ -n "$DB_TYPE" ]; then\n\
  echo "Configuring database: $DB_TYPE"\n\
  \n\
  # Remove old DB config lines\n\
  sed -i "/^DB_TYPE=/d" /app/.env\n\
  sed -i "/^DB_HOST=/d" /app/.env\n\
  sed -i "/^DB_PORT=/d" /app/.env\n\
  sed -i "/^DB_NAME=/d" /app/.env\n\
  sed -i "/^DB_USER=/d" /app/.env\n\
  sed -i "/^DB_PASSWORD=/d" /app/.env\n\
  sed -i "/^DATABASE_URL=/d" /app/.env\n\
  sed -i "/^SYNC_DATABASE_URL=/d" /app/.env\n\
  \n\
  # Add new DB config\n\
  echo "DB_TYPE=$DB_TYPE" >> /app/.env\n\
  \n\
  if [ "$DB_TYPE" = "postgresql" ]; then\n\
    echo "DB_HOST=${DB_HOST:-postgres}" >> /app/.env\n\
    echo "DB_PORT=${DB_PORT:-5432}" >> /app/.env\n\
    echo "DB_NAME=${DB_NAME:-aunoo_db}" >> /app/.env\n\
    echo "DB_USER=${DB_USER:-aunoo_user}" >> /app/.env\n\
    echo "DB_PASSWORD=${DB_PASSWORD:-changeme}" >> /app/.env\n\
    echo "DATABASE_URL=postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}" >> /app/.env\n\
    echo "SYNC_DATABASE_URL=postgresql+psycopg2://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}" >> /app/.env\n\
    echo "DB_POOL_SIZE=${DB_POOL_SIZE:-20}" >> /app/.env\n\
    echo "DB_MAX_OVERFLOW=${DB_MAX_OVERFLOW:-10}" >> /app/.env\n\
    \n\
    # Wait for PostgreSQL to be ready\n\
    echo "Waiting for PostgreSQL..."\n\
    until PGPASSWORD=$DB_PASSWORD psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -c "\\q" 2>/dev/null; do\n\
      echo "PostgreSQL is unavailable - sleeping"\n\
      sleep 2\n\
    done\n\
    echo "PostgreSQL is ready!"\n\
    \n\
    # Run migrations\n\
    echo "Running database migrations..."\n\
    alembic upgrade head || echo "Migration warning (may be expected for first run)"\n\
  fi\n\
fi\n\
\n\
# Set initial admin password if ADMIN_PASSWORD is provided and using SQLite\n\
if [ -n "$ADMIN_PASSWORD" ] && [ "$DB_TYPE" != "postgresql" ]; then\n\
  echo "Setting initial admin password..."\n\
  python -c "from app.utils.update_admin import update_admin_password; update_admin_password(\"/app/app/data/${INSTANCE}/fnaapp.db\", \"$ADMIN_PASSWORD\")" || true\n\
fi\n\
\n\
# Display startup info\n\
echo "================================================"\n\
echo "AunooAI Server Starting"\n\
echo "================================================"\n\
echo "Instance:    ${INSTANCE}"\n\
echo "Port:        ${PORT}"\n\
echo "Database:    ${DB_TYPE:-sqlite}"\n\
echo "Environment: ${ENVIRONMENT:-development}"\n\
echo "Version:     ${APP_VERSION}"\n\
echo "Branch:      ${APP_GIT_BRANCH}"\n\
echo "Build Date:  ${APP_BUILD_DATE}"\n\
echo "================================================"\n\
\n\
# Start application\n\
exec python app/run.py' > /entrypoint.sh && \
    chmod +x /entrypoint.sh

# Expose the port the app runs on
EXPOSE ${PORT}

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Command to run the application
CMD ["/entrypoint.sh"]
