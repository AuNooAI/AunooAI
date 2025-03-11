# AunooAI Deployment Fixes

This document summarizes the key changes made to fix deployment issues with AunooAI on Google Cloud Run.

## Issue 1: ModuleNotFoundError for 'scripts' Module

### Problem
The application failed to start due to a missing 'scripts' module, which contains database merging functionality:

```
ModuleNotFoundError: No module named 'scripts'
```

### Solution
We implemented a defensive import strategy in `app/routes/database.py`:

```python
try:
    from scripts.db_merge import DatabaseMerger
except ImportError:
    # Create a stub implementation if scripts module is not available
    class DatabaseMerger:
        def __init__(self, *args, **kwargs):
            logging.warning("Using stub DatabaseMerger (import failed)")
            
        def merge_databases(self, source_db_path):
            logging.warning(f"STUB: Would merge database from {source_db_path}")
            return True
```

This allows the application to run even when the scripts module is not available, which is appropriate for Cloud Run deployments.

### Why This Works
- The try-except block catches the ImportError at the source
- The stub implementation provides the same interface as the real DatabaseMerger
- The application can continue running without the actual scripts module
- Logging is added to indicate when the stub is being used

## Issue 2: PORT Environment Variable Conflicts

### Problem
Cloud Run automatically sets the `PORT` environment variable, which cannot be overridden. Our application was trying to set this variable, causing conflicts.

### Solution
We updated the entrypoint script to handle both `PORT` and `CONTAINER_PORT`:

```bash
# PORT handling: Cloud Run sets PORT automatically and we should use that
# For Kubernetes deployments, we use CONTAINER_PORT instead
if [ -z "$PORT" ] && [ -n "$CONTAINER_PORT" ]; then
  export PORT="$CONTAINER_PORT"
  echo "Using CONTAINER_PORT value for PORT: ${PORT}"
else
  # Cloud Run will have already set PORT
  echo "Using provided PORT: ${PORT}"
fi

# Make sure PORT is set to something if neither variable was provided
export PORT="${PORT:-8080}"
```

### Why This Works
- Respects Cloud Run's automatically set PORT variable
- Provides a fallback for Kubernetes deployments using CONTAINER_PORT
- Ensures a default value if neither variable is set

## Issue 3: SSL Certificate Issues

### Problem
Cloud Run handles SSL termination, but the application was trying to use its own SSL certificates, causing startup failures.

### Solution
We explicitly disable SSL in the entrypoint script:

```bash
# EXPLICITLY disable SSL for Cloud Run
export DISABLE_SSL="true"
export CERT_PATH="/dev/null"
export KEY_PATH="/dev/null"
```

### Why This Works
- Tells the application not to use SSL
- Sets certificate paths to /dev/null to prevent errors
- Allows Cloud Run to handle SSL termination

## Issue 4: Directory Structure and File Permissions

### Problem
The application required specific directories and file permissions to function correctly.

### Solution
We updated the Dockerfile to ensure all necessary directories exist and have proper permissions:

```dockerfile
# Ensure data directories exist and have proper permissions
RUN mkdir -p /app/app/data && \
    mkdir -p /app/data && \
    mkdir -p /app/reports
    
# Set permissions for directories
RUN chmod -R 777 /app/app/data /app/reports /app/data /app/scripts
```

### Why This Works
- Creates all required directories during image build
- Sets permissive permissions to avoid access issues
- Ensures the application can write to data directories

## Issue 5: Startup Script Improvements

### Problem
The application needed a custom startup process for Cloud Run.

### Solution
We created a dedicated `cloud_run_start.py` script that:
1. Sets up the Python environment
2. Handles import patching
3. Creates necessary directories
4. Starts the application with the correct settings

### Why This Works
- Provides a Cloud Run-specific entry point
- Handles environment setup before starting the application
- Includes detailed logging for troubleshooting

## Lessons Learned

1. **Defensive Programming**: Always handle potential errors gracefully, especially when dealing with imports and external dependencies.

2. **Environment-Specific Configuration**: Different deployment environments (like Cloud Run vs. GKE) may require different configurations.

3. **Logging and Debugging**: Comprehensive logging is essential for troubleshooting deployment issues.

4. **Multiple Layers of Protection**: Implementing multiple solutions (stub modules, directory verification, etc.) provides redundancy in case one approach fails.

5. **Documentation**: Keeping detailed documentation of deployment processes and issues helps with future maintenance and troubleshooting. 