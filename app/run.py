import sys
import os

# Add the parent directory to the Python path FIRST
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging BEFORE any other imports
from app.core.logging_config import configure_logging
configure_logging()

# Now import everything else
import uvicorn
from dotenv import load_dotenv
import ssl
from fastapi.middleware.cors import CORSMiddleware
import logging

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# Get port from environment variable, default to 10000 if not set
# Handle empty string case (common in Docker environment variables)
port_value = os.getenv('PORT', '10000').strip()
PORT = int(port_value) if port_value else 10000
CERT_PATH = os.getenv('CERT_PATH', 'cert.pem')
KEY_PATH = os.getenv('KEY_PATH', 'key.pem')
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')
DISABLE_SSL = os.getenv('DISABLE_SSL', 'false').lower() == 'true'

def check_database_connection():
    """Check database connection and provide helpful diagnostics."""
    db_type = os.getenv('DB_TYPE', 'sqlite').lower()

    if db_type == 'postgresql':
        logger.info("PostgreSQL database configured")

        # Check required environment variables
        required_vars = ['DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD']
        missing_vars = [var for var in required_vars if not os.getenv(var)]

        if missing_vars:
            logger.error(f"❌ Missing required PostgreSQL environment variables: {', '.join(missing_vars)}")
            logger.error("Run 'python scripts/setup_postgresql.py' to configure PostgreSQL")
            return False

        # Try to import PostgreSQL dependencies
        try:
            import asyncpg
            import psycopg2
            logger.info("✅ PostgreSQL dependencies installed")
        except ImportError as e:
            logger.error(f"❌ Missing PostgreSQL dependencies: {e}")
            logger.error("Run 'pip install asyncpg psycopg2-binary' or 'python scripts/setup_postgresql.py'")
            return False

        # Test connection
        try:
            import psycopg2
            db_host = os.getenv('DB_HOST')
            db_port = os.getenv('DB_PORT')
            db_name = os.getenv('DB_NAME')
            db_user = os.getenv('DB_USER')
            db_password = os.getenv('DB_PASSWORD')

            conn = psycopg2.connect(
                host=db_host,
                port=db_port,
                database=db_name,
                user=db_user,
                password=db_password,
                connect_timeout=5
            )
            conn.close()
            logger.info(f"✅ Connected to PostgreSQL database: {db_name}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to connect to PostgreSQL: {e}")
            logger.error("Check your database configuration or run 'python scripts/setup_postgresql.py'")
            return False
    else:
        logger.info("SQLite database configured")
        db_path = os.path.join(os.path.dirname(__file__), 'data', 'fnaapp.db')
        if os.path.exists(db_path):
            logger.info(f"✅ SQLite database found: {db_path}")
        else:
            logger.warning(f"⚠️  SQLite database not found: {db_path}")
            logger.info("Database will be created on first run")
        return True

def configure_app():
    from main import app
    
    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:8010",
            "https://localhost:8010",
            "https://localhost:10000",
            "http://localhost:10000"
        ] if ENVIRONMENT == 'production' else ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    return app

if __name__ == "__main__":
    # Check database connection before starting server
    logger.info("=" * 60)
    logger.info("AunooAI Server Startup")
    logger.info("=" * 60)

    if not check_database_connection():
        logger.error("\n❌ Database connection check failed!")
        logger.error("Please fix the database configuration before starting the server.")
        logger.error("\nFor PostgreSQL setup, run: python scripts/setup_postgresql.py")
        sys.exit(1)

    logger.info("=" * 60)

    # For Cloud Run, we don't use SSL since it's managed by Cloud Run itself
    print(f"DISABLE_SSL = {DISABLE_SSL}")
    print(f"Starting server on port {PORT}")
    
    if DISABLE_SSL:
        # Cloud Run mode (no SSL)
        print("Running without SSL (for Cloud Run)")
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=PORT,
            reload=True if ENVIRONMENT == 'development' else False,
            log_level="warning"  # Add log level control
        )
    else:
        # Regular mode with SSL
        print(f"Running with SSL using {CERT_PATH} and {KEY_PATH}")
        try:
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.load_cert_chain(CERT_PATH, keyfile=KEY_PATH)
            
            uvicorn.run(
                "main:app",
                host="0.0.0.0",
                port=PORT,
                ssl_keyfile=KEY_PATH,
                ssl_certfile=CERT_PATH,
                reload=True if ENVIRONMENT == 'development' else False,
                log_level="warning"  # Add log level control
            )
        except FileNotFoundError:
            print(f"WARNING: SSL certificate files not found. Falling back to non-SSL mode.")
            uvicorn.run(
                "main:app",
                host="0.0.0.0",
                port=PORT,
                reload=True if ENVIRONMENT == 'development' else False,
                log_level="warning"  # Add log level control
            )
