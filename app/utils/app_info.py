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
        last_update = os.environ.get('APP_LAST_UPDATE')
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
            with open(version_path, 'r') as f:
                version = f.read().strip()
                logger.debug(f"Read version: {version}")
                return version
        else:
            logger.warning(f"Version file not found at: {version_path}")
            # Try alternate location
            alt_version_path = os.path.join(current_dir, '..', '..', 'app', 'version.txt')
            logger.debug(f"Trying alternate path: {alt_version_path}")
            if os.path.exists(alt_version_path):
                logger.debug(f"Version file found at alternate path: {alt_version_path}")
                with open(alt_version_path, 'r') as f:
                    version = f.read().strip()
                    logger.debug(f"Read version: {version}")
                    return version
            
    except Exception as e:
        logger.error(f"Error reading version: {str(e)}")
        logger.error(f"Stack trace: {traceback.format_exc()}")
    return None

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
    
    logger.debug(f"App Info - Version: {version}, Branch: {branch}, Last Update: {last_update}")
    
    info = {
        'version': version or 'N/A',
        'branch': branch or 'N/A',
        'last_update': last_update or 'N/A'
    }
    
    logger.debug(f"Returning app info: {info}")
    return info 