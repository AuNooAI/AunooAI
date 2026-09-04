"""Pure-function checks for the MCP OAuth helpers. No database, no app."""

import base64
import hashlib
import time
from datetime import timedelta

import pytest

pytestmark = pytest.mark.usefixtures("mcp_env")


@pytest.fixture
def mcp_env(monkeypatch):
    monkeypatch.setenv("NORN_SECRET_KEY", "test-secret-not-for-prod")
    monkeypatch.setenv("APP_URL", "https://example.test")


def test_pkce_s256_vector():
    from app.mcp_access import oauth_service as svc
    # RFC 7636 appendix B
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    assert svc.verify_pkce(challenge, verifier)
    assert not svc.verify_pkce(challenge, verifier + "x")
    assert not svc.verify_pkce("", verifier)
    assert not svc.verify_pkce(challenge, None)


def test_pkce_matches_our_own_derivation():
    from app.mcp_access import oauth_service as svc
    verifier = "a" * 43
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert svc.verify_pkce(challenge, verifier)


def test_access_token_round_trip():
    from app.mcp_access import oauth_service as svc
    tok = svc.mint_access_token(username="Alice", client_id="c1")
    claims = svc.decode_access_token(tok)
    assert claims is not None
    assert claims["sub"] == "alice"
    assert claims["client_id"] == "c1"
    assert claims["aud"] == "https://example.test/mcp"
    assert claims["iss"] == "https://example.test"
    assert claims["scope"] == "mcp:workspace"


def test_access_token_wrong_audience_and_expiry(monkeypatch):
    from app.mcp_access import oauth_service as svc
    tok = svc.mint_access_token(username="alice", client_id="c1")
    monkeypatch.setenv("APP_URL", "https://other.test")
    assert svc.decode_access_token(tok) is None
    monkeypatch.setenv("APP_URL", "https://example.test")
    expired = svc.mint_access_token(username="alice", client_id="c1", ttl=timedelta(seconds=-5))
    assert svc.decode_access_token(expired) is None
    assert svc.decode_access_token("not-a-jwt") is None
    assert svc.decode_access_token(None) is None


def test_client_secret_check_is_hash_based():
    from app.mcp_access import oauth_service as svc
    raw, digest = svc.generate_client_secret()
    assert svc.verify_client_secret(digest, raw)
    assert not svc.verify_client_secret(digest, raw + "x")
    assert not svc.verify_client_secret(None, raw)
    assert not svc.verify_client_secret(digest, "")


@pytest.mark.parametrize("uri,ok", [
    ("https://claude.ai/api/mcp/auth_callback", True),
    ("http://localhost:3000/cb", True),
    ("http://127.0.0.1:41234/callback", True),
    ("http://localhost", True),
    ("http://evil.test/cb", False),
    ("http://localhost.evil.test/cb", False),
    ("ftp://x", False),
    (123, False),
])
def test_validate_redirect_uri(uri, ok):
    from app.mcp_access import oauth_service as svc
    assert svc.validate_redirect_uri(uri) is ok


def test_pending_store_consume_once_and_expiry(monkeypatch):
    from app.mcp_access import oauth_service as svc
    store = svc.PendingConsentStore(ttl_seconds=0.2)
    rid = store.put({"username": "alice"})
    assert store.peek(rid) == {"username": "alice"}
    assert store.pop(rid) == {"username": "alice"}
    assert store.pop(rid) is None
    rid2 = store.put({"username": "bob"})
    time.sleep(0.25)
    assert store.peek(rid2) is None


def test_rate_limiter_blocks_after_burst():
    from app.mcp_access import oauth_service as svc
    rl = svc.RateLimiter(rate_per_minute=3)
    assert all(rl.allow("ip") for _ in range(3))
    assert not rl.allow("ip")
    assert rl.allow("other-ip")


def test_bearer_key_helpers():
    from app.mcp_access import keys
    assert keys.strip_bearer("Bearer abc") == "abc"
    assert keys.strip_bearer("bearer   abc  ") == "abc"
    assert keys.strip_bearer("Basic abc") is None
    assert keys.strip_bearer("Bearer") is None
    assert keys.strip_bearer(None) is None
    plain = keys.new_plaintext()
    assert plain.startswith("aunoo_") and len(plain) > 40
    assert len(keys.hash_token(plain)) == 64
