#!/bin/bash
set -e

# Create instance directory
mkdir -p /app/app/data/${INSTANCE}

# Setup .env file
if [ ! -f /app/app/data/${INSTANCE}/.env ]; then
  echo "Creating new .env file for instance: ${INSTANCE}"
  touch /app/app/data/${INSTANCE}/.env
  chmod 666 /app/app/data/${INSTANCE}/.env

  # Set default environment variables
  cat > /app/app/data/${INSTANCE}/.env <<EOF
PORT=${PORT:-10000}
ENVIRONMENT=${ENVIRONMENT:-development}
DISABLE_SSL=true
EOF
fi

# Link .env file
ln -sf /app/app/data/${INSTANCE}/.env /app/.env

# Community Edition: PostgreSQL Only
# SQLite is not supported in containerized deployments
if [ -z "$DB_TYPE" ]; then
  echo "ERROR: DB_TYPE environment variable is required"
  echo "Community Edition requires PostgreSQL (DB_TYPE=postgresql)"
  exit 1
fi

if [ "$DB_TYPE" != "postgresql" ]; then
  echo "ERROR: Only PostgreSQL is supported in Community Edition"
  echo "Please set DB_TYPE=postgresql and provide PostgreSQL connection details"
  exit 1
fi

echo "Configuring PostgreSQL database..."

# Remove old DB config lines
sed -i "/^DB_TYPE=/d" /app/.env
sed -i "/^DB_HOST=/d" /app/.env
sed -i "/^DB_PORT=/d" /app/.env
sed -i "/^DB_NAME=/d" /app/.env
sed -i "/^DB_USER=/d" /app/.env
sed -i "/^DB_PASSWORD=/d" /app/.env
sed -i "/^DATABASE_URL=/d" /app/.env
sed -i "/^SYNC_DATABASE_URL=/d" /app/.env
sed -i "/^DB_POOL_SIZE=/d" /app/.env
sed -i "/^DB_MAX_OVERFLOW=/d" /app/.env
sed -i "/^DB_POOL_TIMEOUT=/d" /app/.env
sed -i "/^DB_POOL_RECYCLE=/d" /app/.env

# Add PostgreSQL config
echo "DB_TYPE=postgresql" >> /app/.env
echo "DB_HOST=${DB_HOST:-postgres}" >> /app/.env
echo "DB_PORT=${DB_PORT:-5432}" >> /app/.env
echo "DB_NAME=${DB_NAME:-aunoo_db}" >> /app/.env
echo "DB_USER=${DB_USER:-aunoo_user}" >> /app/.env
echo "DB_PASSWORD=${DB_PASSWORD:-changeme}" >> /app/.env
echo "DATABASE_URL=postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}" >> /app/.env
echo "SYNC_DATABASE_URL=postgresql+psycopg2://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}" >> /app/.env
echo "DB_POOL_SIZE=${DB_POOL_SIZE:-20}" >> /app/.env
echo "DB_MAX_OVERFLOW=${DB_MAX_OVERFLOW:-10}" >> /app/.env
echo "DB_POOL_TIMEOUT=${DB_POOL_TIMEOUT:-30}" >> /app/.env
echo "DB_POOL_RECYCLE=${DB_POOL_RECYCLE:-3600}" >> /app/.env

# Wait for PostgreSQL to be ready with timeout
echo "Waiting for PostgreSQL..."
RETRIES=30
until PGPASSWORD=$DB_PASSWORD psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -c "\q" 2>/dev/null || [ $RETRIES -eq 0 ]; do
  echo "PostgreSQL is unavailable - waiting ($RETRIES retries left)"
  RETRIES=$((RETRIES-1))
  sleep 2
done

if [ $RETRIES -eq 0 ]; then
  echo "ERROR: PostgreSQL connection timeout!"
  echo "Please check:"
  echo "  - PostgreSQL service is running"
  echo "  - DB_HOST=$DB_HOST is correct"
  echo "  - DB_USER=$DB_USER has access"
  echo "  - DB_NAME=$DB_NAME exists"
  exit 1
fi

echo "PostgreSQL is ready!"

# Run migrations
echo "Running database migrations..."
if ! alembic upgrade head; then
  echo "❌ ERROR: Database migrations FAILED!"
  echo "This is a critical error - the database is not initialized."
  echo "Container will exit."
  exit 1
fi
echo "✅ Database migrations completed successfully"

# Initialize media bias data
echo "Initializing media bias data..."
if python scripts/init_media_bias.py; then
  echo "✅ Media bias data initialized"
else
  echo "⚠️  Media bias initialization failed (non-fatal)"
fi

# Display startup info
echo "================================================"
echo "AunooAI Server Starting"
echo "================================================"
echo "Instance:    ${INSTANCE}"
echo "Port:        ${PORT}"
echo "Database:    ${DB_TYPE:-sqlite}"
if [ "$DB_TYPE" = "postgresql" ]; then
  echo "DB Host:     ${DB_HOST}:${DB_PORT}"
  echo "DB Name:     ${DB_NAME}"
  echo "Pool Size:   ${DB_POOL_SIZE:-20}"
fi
echo "Environment: ${ENVIRONMENT:-development}"
echo "Version:     ${APP_VERSION}"
echo "Branch:      ${APP_GIT_BRANCH}"
echo "Build Date:  ${APP_BUILD_DATE}"
echo "================================================"

# Start application
exec python app/run.py
