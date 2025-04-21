from typing import Dict, Optional, Any
import json
import os
import time
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class CacheError(Exception):
    pass

class AnalysisCache:
    def __init__(self, cache_dir: str = "cache", ttl_hours: int = 24):
        self.cache_dir = cache_dir
        self.ttl = timedelta(hours=ttl_hours)
        self._ensure_cache_dir()

    def _ensure_cache_dir(self) -> None:
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
        except Exception as e:
            raise CacheError(f"Failed to create cache directory: {str(e)}")

    def _get_cache_key(self, uri: str, content_hash: str) -> str:
        """Generate a cache key that includes model information."""
        # Remove the old model name extraction since we'll handle it differently
        return f"{uri}_{content_hash}"

    def _get_cache_path(self, uri: str, content_hash: str) -> str:
        """Create a cache path that includes model information."""
        # Create a safe filename from the URI
        safe_uri = uri.replace('://', '_').replace('/', '_')
        filename = f"{safe_uri}_{content_hash}.json"
        
        # Create subdirectories based on the first few characters of the hash
        subdir = content_hash[:2]
        subdir_path = os.path.join(self.cache_dir, subdir)
        os.makedirs(subdir_path, exist_ok=True)
        
        return os.path.join(subdir_path, filename)

    def get(self, uri: str, content_hash: str, model_info: Dict[str, str] = None, template_hash: str = None) -> Optional[Dict[str, Any]]:
        """Get cached analysis with model version checking."""
        try:
            cache_key = self._get_cache_key(uri, content_hash)
            cache_path = self._get_cache_path(uri, content_hash)

            logger.debug(f"Checking cache with key: {cache_key}")
            if not os.path.exists(cache_path):
                logger.debug(f"No cache file found at: {cache_path}")
                return None

            with open(cache_path, 'r') as f:
                cached_data = json.load(f)

            # Check if cache has expired
            cached_time = datetime.fromisoformat(cached_data['cached_at'])
            if datetime.now() - cached_time > self.ttl:
                logger.debug(f"Cache expired for {cache_key}")
                self.delete(uri, content_hash)
                return None

            # Check model version if provided
            if model_info:
                cached_model = cached_data.get('model_info', {})
                if cached_model.get('name') != model_info.get('name') or \
                   cached_model.get('provider') != model_info.get('provider'):
                    logger.debug(f"Model mismatch for {cache_key}")
                    self.delete(uri, content_hash)
                    return None

            # Check template version if provided
            if template_hash and cached_data.get('template_hash') != template_hash:
                logger.debug(f"Template version mismatch for {cache_key}")
                self.delete(uri, content_hash)
                return None

            logger.debug(f"Cache hit for {cache_key}")
            return cached_data['analysis']
        except Exception as e:
            logger.error(f"Error reading from cache: {str(e)}")
            return None

    def set(self, uri: str, content_hash: str, analysis: Dict[str, Any], model_info: Dict[str, str] = None, template_hash: str = None) -> None:
        """Store analysis with model version information."""
        try:
            cache_key = self._get_cache_key(uri, content_hash)
            cache_path = self._get_cache_path(uri, content_hash)

            cache_data = {
                'uri': uri,
                'content_hash': content_hash,
                'analysis': analysis,
                'cached_at': datetime.now().isoformat(),
                'template_hash': template_hash,
                'model_info': model_info
            }

            with open(cache_path, 'w') as f:
                json.dump(cache_data, f, indent=2)

            logger.debug(f"Cached analysis for {uri} with model info: {model_info}")
        except Exception as e:
            logger.error(f"Error writing to cache: {str(e)}")
            raise CacheError(f"Failed to cache analysis: {str(e)}")

    def delete(self, uri: str, content_hash: str) -> None:
        try:
            cache_key = self._get_cache_key(uri, content_hash)
            cache_path = self._get_cache_path(uri, content_hash)

            if os.path.exists(cache_path):
                os.remove(cache_path)
                logger.debug(f"Deleted cache for {uri}")
        except Exception as e:
            logger.error(f"Error deleting cache: {str(e)}")
            raise CacheError(f"Failed to delete cache: {str(e)}")

    def clear(self) -> None:
        try:
            for filename in os.listdir(self.cache_dir):
                if filename.endswith('.json'):
                    os.remove(os.path.join(self.cache_dir, filename))
            logger.info("Cache cleared")
        except Exception as e:
            logger.error(f"Error clearing cache: {str(e)}")
            raise CacheError(f"Failed to clear cache: {str(e)}")

    def get_stats(self) -> Dict[str, Any]:
        try:
            total_files = 0
            total_size = 0
            oldest_cache = None
            newest_cache = None

            for filename in os.listdir(self.cache_dir):
                if filename.endswith('.json'):
                    file_path = os.path.join(self.cache_dir, filename)
                    total_files += 1
                    total_size += os.path.getsize(file_path)

                    with open(file_path, 'r') as f:
                        cache_data = json.load(f)
                        cached_at = datetime.fromisoformat(cache_data['cached_at'])
                        
                        if oldest_cache is None or cached_at < oldest_cache:
                            oldest_cache = cached_at
                        if newest_cache is None or cached_at > newest_cache:
                            newest_cache = cached_at

            return {
                'total_files': total_files,
                'total_size_bytes': total_size,
                'oldest_cache': oldest_cache.isoformat() if oldest_cache else None,
                'newest_cache': newest_cache.isoformat() if newest_cache else None
            }
        except Exception as e:
            logger.error(f"Error getting cache stats: {str(e)}")
            raise CacheError(f"Failed to get cache stats: {str(e)}")

    def cleanup_expired(self) -> int:
        try:
            cleaned = 0
            for filename in os.listdir(self.cache_dir):
                if filename.endswith('.json'):
                    file_path = os.path.join(self.cache_dir, filename)
                    with open(file_path, 'r') as f:
                        cache_data = json.load(f)
                        cached_at = datetime.fromisoformat(cache_data['cached_at'])
                        
                        if datetime.now() - cached_at > self.ttl:
                            os.remove(file_path)
                            cleaned += 1

            logger.info(f"Cleaned up {cleaned} expired cache files")
            return cleaned
        except Exception as e:
            logger.error(f"Error cleaning up expired cache: {str(e)}")
            raise CacheError(f"Failed to clean up expired cache: {str(e)}") 