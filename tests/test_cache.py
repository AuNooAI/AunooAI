import pytest
import os
import json
from datetime import datetime, timedelta
from app.analyzers.cache import AnalysisCache, CacheError

@pytest.fixture
def cache_dir(tmp_path):
    return str(tmp_path / "test_cache")

@pytest.fixture
def cache(cache_dir):
    return AnalysisCache(cache_dir=cache_dir, ttl_hours=24)

@pytest.fixture
def sample_analysis():
    return {
        "title": "Test Title",
        "summary": "Test Summary",
        "category": "Test Category"
    }

def test_cache_initialization(cache_dir):
    # Test normal initialization
    cache = AnalysisCache(cache_dir)
    assert os.path.exists(cache_dir)

    # Test initialization with existing directory
    cache = AnalysisCache(cache_dir)
    assert os.path.exists(cache_dir)

def test_cache_set_get(cache, sample_analysis):
    uri = "http://test.com"
    content_hash = "test_hash"

    # Test setting cache
    cache.set(uri, content_hash, sample_analysis)
    
    # Test getting cache
    cached = cache.get(uri, content_hash)
    assert cached == sample_analysis

    # Test getting non-existent cache
    assert cache.get("nonexistent", "hash") is None

def test_cache_expiration(cache_dir, sample_analysis):
    # Create cache with short TTL
    cache = AnalysisCache(cache_dir, ttl_hours=0.001)  # ~3.6 seconds
    uri = "http://test.com"
    content_hash = "test_hash"

    # Set cache
    cache.set(uri, content_hash, sample_analysis)
    
    # Verify cache exists
    assert cache.get(uri, content_hash) == sample_analysis
    
    # Wait for cache to expire
    import time
    time.sleep(4)
    
    # Verify cache is expired
    assert cache.get(uri, content_hash) is None

def test_cache_delete(cache, sample_analysis):
    uri = "http://test.com"
    content_hash = "test_hash"

    # Set and verify cache
    cache.set(uri, content_hash, sample_analysis)
    assert cache.get(uri, content_hash) == sample_analysis

    # Delete cache
    cache.delete(uri, content_hash)
    assert cache.get(uri, content_hash) is None

    # Test deleting non-existent cache
    cache.delete("nonexistent", "hash")  # Should not raise error

def test_cache_clear(cache, sample_analysis):
    # Set multiple cache entries
    entries = [
        ("http://test1.com", "hash1"),
        ("http://test2.com", "hash2"),
        ("http://test3.com", "hash3")
    ]
    
    for uri, content_hash in entries:
        cache.set(uri, content_hash, sample_analysis)
        assert cache.get(uri, content_hash) == sample_analysis

    # Clear cache
    cache.clear()

    # Verify all entries are cleared
    for uri, content_hash in entries:
        assert cache.get(uri, content_hash) is None

def test_cache_stats(cache, sample_analysis):
    # Set multiple cache entries
    entries = [
        ("http://test1.com", "hash1"),
        ("http://test2.com", "hash2"),
        ("http://test3.com", "hash3")
    ]
    
    for uri, content_hash in entries:
        cache.set(uri, content_hash, sample_analysis)

    # Get stats
    stats = cache.get_stats()
    
    assert stats["total_files"] == 3
    assert stats["total_size_bytes"] > 0
    assert stats["oldest_cache"] is not None
    assert stats["newest_cache"] is not None

def test_cache_cleanup_expired(cache_dir, sample_analysis):
    # Create cache with short TTL
    cache = AnalysisCache(cache_dir, ttl_hours=0.001)  # ~3.6 seconds
    
    # Set multiple cache entries
    entries = [
        ("http://test1.com", "hash1"),
        ("http://test2.com", "hash2"),
        ("http://test3.com", "hash3")
    ]
    
    for uri, content_hash in entries:
        cache.set(uri, content_hash, sample_analysis)

    # Wait for cache to expire
    import time
    time.sleep(4)

    # Clean up expired entries
    cleaned = cache.cleanup_expired()
    assert cleaned == 3

    # Verify all entries are cleaned
    for uri, content_hash in entries:
        assert cache.get(uri, content_hash) is None

def test_cache_error_handling(cache_dir):
    # Test invalid cache directory
    with pytest.raises(CacheError):
        AnalysisCache("/nonexistent/path")

    cache = AnalysisCache(cache_dir)

    # Test invalid JSON in cache file
    uri = "http://test.com"
    content_hash = "test_hash"
    cache_path = os.path.join(cache_dir, f"{uri}_{content_hash}.json")
    
    os.makedirs(cache_dir, exist_ok=True)
    with open(cache_path, 'w') as f:
        f.write("invalid json")

    assert cache.get(uri, content_hash) is None

def test_cache_concurrent_access(cache_dir, sample_analysis):
    # Test multiple cache instances accessing same directory
    cache1 = AnalysisCache(cache_dir)
    cache2 = AnalysisCache(cache_dir)

    uri = "http://test.com"
    content_hash = "test_hash"

    # Set with first instance
    cache1.set(uri, content_hash, sample_analysis)
    
    # Get with second instance
    assert cache2.get(uri, content_hash) == sample_analysis
    
    # Delete with second instance
    cache2.delete(uri, content_hash)
    
    # Verify deleted in first instance
    assert cache1.get(uri, content_hash) is None 