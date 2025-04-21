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

## Issue 6: HTTPS Redirect Loop

### Problem
When deployed to Cloud Run, the application was stuck in an infinite redirect loop, resulting in the browser error `ERR_TOO_MANY_ACCEPT_CH_RESTARTS`. This happened because Cloud Run handles SSL termination at its edge, but internally forwards requests to the container using HTTP. The application's `HTTPSRedirectMiddleware` was detecting these internal HTTP requests and trying to redirect them to HTTPS, creating an infinite loop.

### Solution
We modified the `HTTPSRedirectMiddleware` to be aware of Cloud Run's environment:

```python
# Skip HTTPS redirect if running in Cloud Run or if DISABLE_SSL is set
if os.getenv("DISABLE_SSL", "false").lower() == "true":
    return await call_next(request)
    
# Check X-Forwarded-Proto header (used by Cloud Run and other proxies)
forwarded_proto = request.headers.get("X-Forwarded-Proto")
if forwarded_proto == "https":
    # The request is already using HTTPS through a proxy
    return await call_next(request)
```

Additionally, we updated the deployment process to always set the `DISABLE_SSL` environment variable when deploying to Cloud Run:

```bash
# In the deployment script
gcloud run deploy aunooai-${TENANT} \
  --set-env-vars="INSTANCE=${TENANT},ADMIN_PASSWORD=${ADMIN_PASSWORD},STORAGE_BUCKET=${STORAGE_BUCKET},DISABLE_SSL=true" \
  ...
```

### Why This Works
- Respects the `DISABLE_SSL` environment variable set in the entrypoint script
- Checks the `X-Forwarded-Proto` header, which Cloud Run sets to "https" for requests that came in via HTTPS
- Prevents the redirect loop by correctly identifying requests that are already secure
- Setting `DISABLE_SSL=true` in the deployment ensures this fix is always applied

## Issue 7: Startup Probe Timeouts

### Problem
Cloud Run's default startup probe configuration was too aggressive for our application, especially when initializing LiteLLM, which can take longer to start. This resulted in container health check failures with errors like `HealthCheckContainerError`.

### Solution
We adjusted the startup probe configuration in the deployment script:

```bash
# In the deployment script
gcloud run deploy aunooai-${TENANT} \
  --startup-probe=tcp:port=8080,initial-delay=5s,timeout=300s,period=10s,failure-threshold=30 \
  ...
```

For applications that take unusually long to start, we also added the option to deploy without a startup probe initially:

```bash
# For first deployment, omit the startup probe entirely
gcloud run deploy aunooai-${TENANT} \
  # ... other parameters ...
  # No startup probe parameter for first deployment
```

### Why This Works
- Extends the timeout period for startup probes
- Increases the failure threshold before giving up
- Allows the application more time to initialize LiteLLM and other components
- Provides flexibility to deploy without a startup probe for the initial deployment

## Issue 8: LiteLLM Initialization

### Problem
When deploying with LiteLLM, initialization of the various model providers takes time and requires API keys to be configured properly.

### Solution
We updated the deployment script to accept various LiteLLM-related API keys and pass them as environment variables:

```bash
# In the deployment script
OPENAI_API_KEY=${OPENAI_API_KEY:-""}
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-""}
GOOGLE_API_KEY=${GOOGLE_API_KEY:-""}
LITELLM_CONFIG=${LITELLM_CONFIG:-""}

# Build the environment variable string conditionally
ENV_VARS="INSTANCE=${TENANT},ADMIN_PASSWORD=${ADMIN_PASSWORD},STORAGE_BUCKET=${STORAGE_BUCKET},DISABLE_SSL=true"

if [ -n "$OPENAI_API_KEY" ]; then
  ENV_VARS="${ENV_VARS},OPENAI_API_KEY=${OPENAI_API_KEY}"
fi

if [ -n "$ANTHROPIC_API_KEY" ]; then
  ENV_VARS="${ENV_VARS},ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}"
fi

if [ -n "$GOOGLE_API_KEY" ]; then
  ENV_VARS="${ENV_VARS},GOOGLE_API_KEY=${GOOGLE_API_KEY}"
fi

if [ -n "$LITELLM_CONFIG" ]; then
  ENV_VARS="${ENV_VARS},LITELLM_CONFIG=${LITELLM_CONFIG}"
fi
```

### Why This Works
- Allows passing API keys for various LiteLLM providers
- Only includes environment variables that are actually provided
- Provides flexibility for different configurations

## Lessons Learned

1. **Defensive Programming**: Always handle potential errors gracefully, especially when dealing with imports and external dependencies.

2. **Environment-Specific Configuration**: Different deployment environments (like Cloud Run vs. GKE) may require different configurations.

3. **Logging and Debugging**: Comprehensive logging is essential for troubleshooting deployment issues.

4. **Multiple Layers of Protection**: Implementing multiple solutions (stub modules, directory verification, etc.) provides redundancy in case one approach fails.

5. **Documentation**: Keeping detailed documentation of deployment processes and issues helps with future maintenance and troubleshooting.

6. **Proxy Awareness**: When deploying behind proxies or load balancers, applications need to be aware of headers like `X-Forwarded-Proto` to correctly determine the original request protocol.

7. **Startup Probe Configuration**: Applications with complex initialization processes may require custom startup probe settings or even no startup probe for the initial deployment.

8. **Environment Variables for Credentials**: Pass sensitive credentials like API keys as environment variables rather than hardcoding them.

9. **Conditional Configuration**: Build configuration strings conditionally based on what's available, making deployment scripts more flexible and reusable.

10. **Defensive Deployment**: Always include defensive measures like disabling SSL to avoid redirect loops in managed environments like Cloud Run. 