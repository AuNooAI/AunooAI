import uvicorn
import os
from dotenv import load_dotenv
import sys

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
load_dotenv()

# Get port from environment variable, default to 8000 if not set
PORT = int(os.getenv('PORT', 8000))

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=PORT,
        reload=True  # Enable auto-reload during development
    )
