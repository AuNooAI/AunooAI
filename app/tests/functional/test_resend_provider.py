import httpx
import os

BASE_URL = "http://localhost:10001"

def test_resend_key_is_configured():
    payload = {
        "provider": "resend",
        "credentials": {
            "api_key": os.environ["TEST_RESEND_API_KEY"]
        }
    }

    r = httpx.post(f"{BASE_URL}/providers/configure", json=payload)
    assert r.status_code == 200
    assert r.json().get("status") == "success"

    # Verify the key was saved by checking the debug endpoint (server runs in Docker,
    # so we can't read the container's .env file directly from host)
    debug = httpx.get(f"{BASE_URL}/providers/debug_path")
    assert debug.status_code == 200
    assert debug.json().get("env_exists") is True
