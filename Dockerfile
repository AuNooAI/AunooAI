# Use Python 3.11 slim image as base
FROM python:3.11-slim

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

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Create necessary directories
RUN mkdir -p app/data \
    app/config \
    templates \
    static \
    reports

# Copy requirements first
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and other necessary files
COPY app/ app/
COPY templates/ templates/
COPY static/ static/

# Create named volumes for persistent data
VOLUME /app/app/data
VOLUME /app/reports

# Set permissions for persistent directories
RUN chmod -R 777 /app/app/data /app/reports

# Create entrypoint script
RUN echo '#!/bin/bash\n\
mkdir -p /app/app/data/${INSTANCE}\n\
touch /app/app/data/${INSTANCE}/.env\n\
chmod 666 /app/app/data/${INSTANCE}/.env\n\
ln -sf /app/app/data/${INSTANCE}/.env /app/.env\n\
\n\
# Set initial admin password if ADMIN_PASSWORD is provided\n\
if [ -n "$ADMIN_PASSWORD" ]; then\n\
  echo "Setting initial admin password..."\n\
  cd /app && python -c "from app.utils.update_admin import update_admin_password; update_admin_password(\"/app/app/data/${INSTANCE}/fnaapp.db\", \"$ADMIN_PASSWORD\")"\n\
fi\n\
\n\
exec python app/run.py' > /entrypoint.sh && \
    chmod +x /entrypoint.sh

# Expose the port the app runs on
EXPOSE ${PORT}

# Command to run the application
CMD ["/entrypoint.sh"]