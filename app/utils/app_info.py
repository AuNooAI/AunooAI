import subprocess
from datetime import datetime
import os
from typing import Dict, Optional
import logging
import traceback

logger = logging.getLogger(__name__)

def get_git_branch() -> Optional[str]:
    """Get the current git branch name."""
    try:
        # Get absolute path to project root
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(current_dir, '..', '..'))
        
        logger.debug(f"Getting git branch from: {project_root}")
        
        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True,
            text=True,
            check=True,
            cwd=project_root  # Specify the working directory
        )
        branch = result.stdout.strip()
        logger.debug(f"Got git branch: {branch}")
        return branch
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.warning(f"Failed to get git branch: {str(e)}")
        return None

def get_last_commit_date() -> Optional[str]:
    """Get the date of the last git commit."""
    try:
        # Get absolute path to project root
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(current_dir, '..', '..'))
        
        logger.debug(f"Getting last commit date from: {project_root}")
        
        result = subprocess.run(
            ['git', 'log', '-1', '--format=%cd', '--date=iso'],
            capture_output=True,
            text=True,
            check=True,
            cwd=project_root  # Specify the working directory
        )
        commit_date = datetime.strptime(result.stdout.strip(), '%Y-%m-%d %H:%M:%S %z')
        formatted_date = commit_date.strftime('%Y-%m-%d %H:%M:%S')
        logger.debug(f"Got last commit date: {formatted_date}")
        return formatted_date
    except (subprocess.SubprocessError, FileNotFoundError, ValueError) as e:
        logger.warning(f"Failed to get last commit date: {str(e)}")
        return None

def get_version() -> Optional[str]:
    """Get the application version from version.txt if it exists."""
    try:
        # Get absolute path to project root
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(current_dir, '..', '..'))
        version_path = os.path.join(project_root, 'version.txt')
        
        logger.debug(f"Current directory: {current_dir}")
        logger.debug(f"Project root: {project_root}")
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
        logger.error(f"Error reading version file: {str(e)}")
        logger.error(f"Stack trace: {traceback.format_exc()}")
    return None

def get_app_info() -> Dict[str, str]:
    """Get all application information."""
    version = get_version()
    branch = get_git_branch()
    last_update = get_last_commit_date()
    
    logger.debug(f"App Info - Version: {version}, Branch: {branch}, Last Update: {last_update}")
    
    info = {
        'version': version or 'N/A',
        'branch': branch or 'N/A',
        'last_update': last_update or 'N/A'
    }
    
    logger.debug(f"Returning app info: {info}")
    return info 