"""Expired analysis cache files are removed from every subdirectory."""
import json
import os
import time
from datetime import datetime, timedelta

from app.analyzers.cache import AnalysisCache


def _write(path, cached_at, age_seconds):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"cached_at": cached_at.isoformat(), "analysis": {}}, f)
    t = time.time() - age_seconds
    os.utime(path, (t, t))


def test_cleanup_walks_subdirectories(tmp_path):
    cache = AnalysisCache(str(tmp_path), ttl_hours=24)
    old = tmp_path / "ab" / "old.json"
    fresh = tmp_path / "cd" / "fresh.json"
    _write(str(old), datetime.now() - timedelta(hours=30), 30 * 3600)
    _write(str(fresh), datetime.now() - timedelta(hours=1), 3600)
    assert cache.cleanup_expired() == 1
    assert not old.exists() and fresh.exists()


def test_unreadable_file_uses_its_age_and_does_not_stop_the_sweep(tmp_path):
    cache = AnalysisCache(str(tmp_path), ttl_hours=24)
    bad = tmp_path / "ab" / "bad.json"
    bad.parent.mkdir()
    bad.write_text("{not json")
    t = time.time() - 30 * 3600
    os.utime(bad, (t, t))
    old = tmp_path / "ab" / "old.json"
    _write(str(old), datetime.now() - timedelta(hours=30), 30 * 3600)
    assert cache.cleanup_expired() == 2


def test_recent_write_is_never_deleted(tmp_path):
    cache = AnalysisCache(str(tmp_path), ttl_hours=24)
    p = tmp_path / "ab" / "inflight.json"
    _write(str(p), datetime.now() - timedelta(hours=30), 10)  # stale content, just written
    assert cache.cleanup_expired() == 0
    assert p.exists()


def test_set_then_get_round_trip_leaves_no_temp_file(tmp_path):
    cache = AnalysisCache(str(tmp_path), ttl_hours=24)
    cache.set("https://x.test/a", "abcd", {"k": 1})
    assert cache.get("https://x.test/a", "abcd") == {"k": 1}
    assert not [f for _r, _d, fs in os.walk(tmp_path) for f in fs if f.endswith(".tmp")]
