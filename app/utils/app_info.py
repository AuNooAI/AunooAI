import os
from datetime import datetime
import logging
import traceback
from typing import Dict, Optional

logger = logging.getLogger(__name__)

def get_git_branch() -> Optional[str]:
    """Get the current git branch name from environment variable or fallback to git."""
    try:
        # First try to get from environment variable (set during Docker build)
        branch = os.environ.get('APP_GIT_BRANCH')
        if branch:
            logger.debug(f"Got git branch from environment: {branch}")
            return branch
            
        # Fallback to git command if not in Docker
        import subprocess
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(current_dir, '..', '..'))
        
        logger.debug(f"Getting git branch from: {project_root}")
        
        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True,
            text=True,
            check=True,
            cwd=project_root
        )
        branch = result.stdout.strip()
        logger.debug(f"Got git branch from git: {branch}")
        return branch
    except Exception as e:
        logger.warning(f"Failed to get git branch: {str(e)}")
        return None

def get_last_commit_date() -> Optional[str]:
    """Get the date of the last git commit from environment variable or fallback to git."""
    try:
        # First try to get from environment variable (set during Docker build)
        last_update = os.environ.get('APP_BUILD_DATE')
        if last_update:
            logger.debug(f"Got last update from environment: {last_update}")
            return last_update
            
        # Fallback to git command if not in Docker
        import subprocess
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(current_dir, '..', '..'))
        
        logger.debug(f"Getting last commit date from: {project_root}")
        
        result = subprocess.run(
            ['git', 'log', '-1', '--format=%cd', '--date=iso'],
            capture_output=True,
            text=True,
            check=True,
            cwd=project_root
        )
        commit_date = datetime.strptime(result.stdout.strip(), '%Y-%m-%d %H:%M:%S %z')
        formatted_date = commit_date.strftime('%Y-%m-%d %H:%M:%S')
        logger.debug(f"Got last commit date from git: {formatted_date}")
        return formatted_date
    except Exception as e:
        logger.warning(f"Failed to get last commit date: {str(e)}")
        # Fallback to build date if available
        build_date = os.environ.get('APP_BUILD_DATE')
        if build_date:
            logger.debug(f"Using build date instead: {build_date}")
            return build_date
        return None

def get_version() -> Optional[str]:
    """Get the application version from environment variable or version.txt."""
    try:
        # First try to get from environment variable (set during Docker build)
        version = os.environ.get('APP_VERSION')
        if version:
            logger.debug(f"Got version from environment: {version}")
            return version
            
        # Fallback to version.txt
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(current_dir, '..', '..'))
        version_path = os.path.join(project_root, 'version.txt')
        
        logger.debug(f"Looking for version file at: {version_path}")
        
        if os.path.exists(version_path):
            logger.debug(f"Version file found at: {version_path}")
            version = _read_version_file(version_path)
            if version:
                return version
        else:
            logger.debug(f"Version file not found at: {version_path}")
            # Try alternate location
            alt_version_path = os.path.join(current_dir, '..', '..', 'app', 'version.txt')
            logger.debug(f"Trying alternate path: {alt_version_path}")
            if os.path.exists(alt_version_path):
                logger.debug(f"Version file found at alternate path: {alt_version_path}")
                version = _read_version_file(alt_version_path)
                if version:
                    return version
            
    except Exception as e:
        logger.error(f"Error reading version: {str(e)}")
        logger.error(f"Stack trace: {traceback.format_exc()}")
    return None

def _read_version_file(file_path: str) -> Optional[str]:
    """Read version file with robust encoding detection."""
    import codecs
    
    # First try to detect BOM to determine encoding
    try:
        with open(file_path, 'rb') as f:
            raw_data = f.read()
            
        # Check for BOM markers
        if raw_data.startswith(codecs.BOM_UTF16_LE):
            encoding = 'utf-16-le'
            logger.debug(f"Detected UTF-16 LE with BOM")
        elif raw_data.startswith(codecs.BOM_UTF16_BE):
            encoding = 'utf-16-be'
            logger.debug(f"Detected UTF-16 BE with BOM")
        elif raw_data.startswith(codecs.BOM_UTF8):
            encoding = 'utf-8-sig'
            logger.debug(f"Detected UTF-8 with BOM")
        else:
            # No BOM detected, try common encodings in order of likelihood
            encodings_to_try = ['utf-8', 'ascii', 'latin1', 'cp1252']
            for enc in encodings_to_try:
                try:
                    version = raw_data.decode(enc).strip()
                    if version:
                        logger.debug(f"Successfully read version using {enc} encoding: {version}")
                        return _clean_version(version)
                except UnicodeDecodeError:
                    continue
            
            # If all else fails, try UTF-16 without BOM (might work on some systems)
            try:
                version = raw_data.decode('utf-16').strip()
                if version:
                    logger.debug(f"Successfully read version using utf-16 without BOM: {version}")
                    return _clean_version(version)
            except UnicodeDecodeError:
                pass
                
            logger.warning(f"Could not decode version file with any encoding")
            return None
        
        # If we detected a specific encoding from BOM, use it
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                version = f.read().strip()
                logger.debug(f"Read version using detected {encoding} encoding: {version}")
                return _clean_version(version)
        except Exception as e:
            logger.warning(f"Failed to read with detected encoding {encoding}: {e}")
            return None
            
    except Exception as e:
        logger.warning(f"Failed to read version file {file_path}: {e}")
        return None

def _clean_version(version: str) -> str:
    """Clean up version string by removing BOM and non-printable characters."""
    if version and isinstance(version, str):
        # Remove BOM characters if present
        version = version.replace('\ufeff', '').replace('\ufffe', '')
        # Remove any non-printable characters except newlines and spaces
        version = ''.join(c for c in version if c.isprintable() or c.isspace())
        # Trim whitespace
        version = version.strip()
    return version or 'N/A'

def get_app_info() -> Dict[str, str]:
    """Get all application information."""
    version = get_version()
    branch = get_git_branch()
    last_update = get_last_commit_date()
    
    # If all else fails, use container start time
    if not last_update:
        import time
        start_time = os.environ.get('APP_START_TIME')
        if not start_time:
            # Set and store start time on first request
            start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            os.environ['APP_START_TIME'] = start_time
        last_update = start_time
    
    # Ensure we have values for all fields
    if not version:
        version = os.environ.get('APP_VERSION', 'N/A')
    
    if not branch:
        branch = os.environ.get('APP_GIT_BRANCH', 'N/A')
    
    if not last_update:
        last_update = os.environ.get('APP_BUILD_DATE', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    
    # Clean up version if it contains BOM or other encoding artifacts
    if version and isinstance(version, str):
        version = _clean_version(version)
    
    logger.debug(f"App Info - Version: {version}, Branch: {branch}, Last Update: {last_update}")
    
    info = {
        'version': version or 'N/A',
        'branch': branch or 'N/A',
        'last_update': last_update or 'N/A'
    }
    
    logger.debug(f"Returning app info: {info}")
    return info 