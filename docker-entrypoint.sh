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
fi

# Create symlink from /app/.env to volume
rm -f /app/.env
ln -sf /app/.env_volume/.env /app/.env
echo ".env file linked to persistent volume"

# Wait for PostgreSQL if using it
if [ "$DB_TYPE" = "postgresql" ]; then
    echo "Waiting for PostgreSQL at ${DB_HOST:-postgres}:${DB_PORT:-5432}..."

    until pg_isready -h "${DB_HOST:-postgres}" -p "${DB_PORT:-5432}" -U "${DB_USER:-postgres}"; do
        echo "PostgreSQL is unavailable - sleeping"
        sleep 2
    done

    echo "PostgreSQL is up - continuing..."

    # Run database migrations
    echo "Running database migrations..."
    alembic upgrade head || echo "Warning: Migration failed or not needed"

    # Update admin password from environment variable
    if [ -n "$ADMIN_PASSWORD" ]; then
        echo "Setting up admin user with password from ADMIN_PASSWORD..."
        python3 /app/app/utils/update_admin.py || echo "Warning: Admin password setup failed"
    fi

    # Initialize media bias data
    echo "Initializing media bias data..."
    python3 /app/scripts/init_media_bias.py || echo "Warning: Media bias initialization failed or already complete"
fi

# Create necessary directories if they don't exist
mkdir -p /app/app/data
mkdir -p /app/reports
mkdir -p /app/static/audio
mkdir -p /app/tmp/aunoo_audio

# Set permissions
chmod -R 777 /app/app/data /app/reports /app/static/audio /app/tmp 2>/dev/null || true

# Display startup information
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
echo "  ⚠️  IMPORTANT: Configure API keys via the onboarding wizard!"
echo "========================================================================"
echo ""

# Start the application
echo "Starting FastAPI application on port ${PORT}..."
cd /app

if [ -f "/app/app/run.py" ]; then
    echo "Using run.py entry point..."
    exec python app/run.py
else
    echo "Using uvicorn with app.main:app..."
    exec python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --reload
fi
