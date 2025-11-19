#!/bin/bash
set -e

echo "Starting Aunoo AI application..."
echo "Instance: ${INSTANCE:-unknown}"
echo "Environment: ${ENVIRONMENT:-unknown}"
echo "Port: ${PORT:-5000}"
echo "Database Type: ${DB_TYPE:-postgresql}"

# Set up persistent .env file using volume
if [ ! -f "/app/.env_volume/.env" ]; then
    echo "Initializing .env file in volume..."
    # Create initial .env from template if it exists, or create empty
    if [ -f "/app/.env.template" ]; then
        cp /app/.env.template /app/.env_volume/.env
        echo "Copied .env.template to persistent volume"
    else
        touch /app/.env_volume/.env
        echo "Created empty .env in persistent volume"
    fi
    chmod 666 /app/.env_volume/.env
fi

# Create symlink from /app/.env to volume
rm -f /app/.env
ln -sf /app/.env_volume/.env /app/.env
echo ".env file linked to persistent volume"

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

# Create config.json if it doesn't exist (required by database.py)
if [ ! -f "/app/app/data/config.json" ]; then
    echo "Creating default config.json..."
    mkdir -p /app/app/data
    echo '{"active_database": "postgresql"}' > /app/app/data/config.json
    chmod 666 /app/app/data/config.json
    echo "Created config.json with PostgreSQL as active database"
fi

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

# Update admin password from environment variable
if [ -n "$ADMIN_PASSWORD" ]; then
    echo "Setting up admin user with password from ADMIN_PASSWORD..."
    python3 /app/app/utils/update_admin.py || echo "Warning: Admin password setup failed"
fi

# Create necessary directories if they don't exist
mkdir -p /app/app/data
mkdir -p /app/reports
mkdir -p /app/static/audio
mkdir -p /app/tmp/aunoo_audio

# Set permissions
chmod -R 777 /app/app/data /app/reports /app/static/audio /app/tmp 2>/dev/null || true

# Display startup info
echo ""
echo "========================================================================"
echo "  🚀 AunooAI Container Ready"
echo "========================================================================"
echo "  Instance:     ${INSTANCE}"
echo "  Port:         ${PORT}"
echo "  Database:     ${DB_TYPE}"
if [ "$DB_TYPE" = "postgresql" ]; then
  echo "  DB Host:      ${DB_HOST}:${DB_PORT}"
  echo "  DB Name:      ${DB_NAME}"
fi
echo ""
echo "  🔐 DEFAULT LOGIN CREDENTIALS:"
echo "     Username: admin"
echo "     Password: ${ADMIN_PASSWORD:-admin123}"
echo ""
echo "  ⚠️  IMPORTANT: Change the admin password after first login!"
echo "========================================================================"
echo ""

# Start application
exec python app/run.py
