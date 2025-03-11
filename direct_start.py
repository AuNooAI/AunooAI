import uvicorn
import os
import sys
import traceback

# Debug information
print("==== AunooAI Debug Information ====")
print(f"Python version: {sys.version}")
print(f"Current directory: {os.getcwd()}")
print(f"PORT environment variable: {os.environ.get('PORT')}")

# Add current directory to path
sys.path.append(os.getcwd())

# Disable SSL certificates for Cloud Run
os.environ.setdefault("CERT_PATH", "/dev/null")
os.environ.setdefault("KEY_PATH", "/dev/null")
os.environ["DISABLE_SSL"] = "true"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    print(f"Starting server on port {port}")
    
    try:
        # Start with plain HTTP for Cloud Run (no SSL)
        uvicorn.run("app.main:app", host="0.0.0.0", port=port, ssl_keyfile=None, ssl_certfile=None)
    except Exception as e:
        print(f"Error starting application: {str(e)}")
        traceback.print_exc()
        
        # As a backup attempt, try to launch differently
        print("Trying alternate startup method...")
        try:
            # Import and configure the app ourselves
            from app.main import app
            uvicorn.run(app, host="0.0.0.0", port=port)
        except Exception as e2:
            print(f"Error with second attempt: {str(e2)}")
            traceback.print_exc() 