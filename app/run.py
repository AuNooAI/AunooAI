import uvicorn
import os
from dotenv import load_dotenv
import sys
import ssl
from fastapi.middleware.cors import CORSMiddleware

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
load_dotenv()

# Get port from environment variable, default to 8000 if not set
PORT = int(os.getenv('PORT', 8008))
CERT_PATH = os.getenv('CERT_PATH', 'cert.pem')
KEY_PATH = os.getenv('KEY_PATH', 'key.pem')
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')
DISABLE_SSL = os.getenv('DISABLE_SSL', 'false').lower() == 'true'

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
            reload=True if ENVIRONMENT == 'development' else False
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
                reload=True if ENVIRONMENT == 'development' else False
            )
        except FileNotFoundError:
            print(f"WARNING: SSL certificate files not found. Falling back to non-SSL mode.")
            uvicorn.run(
                "main:app",
                host="0.0.0.0",
                port=PORT,
                reload=True if ENVIRONMENT == 'development' else False
            )
