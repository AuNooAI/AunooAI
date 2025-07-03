"""
server_run.py
Launch the FastAPI app on localhost only, ready to be reverse-proxied by NGINX.
"""

import os
import sys
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware

# --------------------------------------------------------------------------- #
# 1.  Environment & paths
# --------------------------------------------------------------------------- #
ROOT_DIR = Path(__file__).resolve().parents[1]          # …/tenant1/AunooAI
sys.path.append(str(ROOT_DIR))                          # import main.py

load_dotenv()                                           # .env in project root

PORT = int(os.getenv("PORT", 10000))
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")    # dev | production

# --------------------------------------------------------------------------- #
# 2.  Build FastAPI application
# --------------------------------------------------------------------------- #
from main import app                                    # ⇐ adjust if app.main

# Open CORS wide during dev; tighten allow_origins in prod if needed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://staging.aunoo.ai"] if ENVIRONMENT == "development" else ["https://experimental.aunoo.ai"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------- #
# 3.  Run Uvicorn  (no SSL here – NGINX handles HTTPS)
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    print(f"Starting FastAPI on http://127.0.0.1:{PORT}  (env = {ENVIRONMENT})")

    uvicorn.run(
        "main:app",                  # ⇐ change to "app.main:app" if needed
        host="127.0.0.1",
        port=PORT,
        reload=ENVIRONMENT == "development",
        proxy_headers=True,          # honour X-Forwarded-* from NGINX
        forwarded_allow_ips="*",     # accept forwarded headers from localhost
    )
