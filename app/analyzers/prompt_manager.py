from typing import Dict, List, Optional
import json
import os
import logging
from datetime import datetime
import hashlib
from pathlib import Path

logger = logging.getLogger(__name__)

class PromptManagerError(Exception):
    pass

class PromptManager:
    def __init__(self, storage_dir: str = None):
        if storage_dir is None:
            # Get the app root directory (parent of app package)
            app_root = Path(__file__).parent.parent.parent
            storage_dir = os.path.join(app_root, "data", "prompts")
        
        self.storage_dir = storage_dir
        self._ensure_storage_dir()
        logger.info(f"Initialized PromptManager with storage directory: {self.storage_dir}")

    def _ensure_storage_dir(self) -> None:
        try:
            # Create main prompts directory
            os.makedirs(self.storage_dir, exist_ok=True)
            
            # Create subdirectories for each prompt type
            for prompt_type in ["title_extraction", "content_analysis", "date_extraction"]:
                prompt_dir = os.path.join(self.storage_dir, prompt_type)
                os.makedirs(prompt_dir, exist_ok=True)
                logger.debug(f"Created prompt directory: {prompt_dir}")
                
                # Ensure current.json exists
                current_path = os.path.join(prompt_dir, "current.json")
                if not os.path.exists(current_path):
                    with open(current_path, 'w') as f:
                        json.dump({
                            "system_prompt": "",
                            "user_prompt": "",
                            "version": "1.0.0",
                            "created_at": datetime.now().isoformat()
                        }, f, indent=2)
                    logger.debug(f"Created empty current.json in {prompt_dir}")
                    
        except Exception as e:
            logger.error(f"Failed to create storage directory: {str(e)}")
            raise PromptManagerError(f"Failed to create storage directory: {str(e)}")

    def _compute_hash(self, content: Dict) -> str:
        content_str = json.dumps(content, sort_keys=True)
        return hashlib.sha256(content_str.encode()).hexdigest()[:16]

    def _get_version_path(self, prompt_type: str, version_hash: str) -> str:
        return os.path.join(self.storage_dir, prompt_type, f"{version_hash}.json")

    def _get_current_path(self, prompt_type: str) -> str:
        return os.path.join(self.storage_dir, prompt_type, "current.json")

    def save_version(self, prompt_type: str, system_prompt: str, user_prompt: str) -> Dict:
        try:
            if prompt_type not in ["title_extraction", "content_analysis", "date_extraction"]:
                raise PromptManagerError(f"Invalid prompt type: {prompt_type}")

            prompt_data = {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "version": "1.0.0",  # You can implement version numbering logic
                "created_at": datetime.now().isoformat()
            }

            # Compute hash and save version
            version_hash = self._compute_hash(prompt_data)
            version_path = self._get_version_path(prompt_type, version_hash)
            
            # Save as a version
            with open(version_path, 'w') as f:
                json.dump(prompt_data, f, indent=2)

            # Update current version
            current_path = self._get_current_path(prompt_type)
            with open(current_path, 'w') as f:
                json.dump(prompt_data, f, indent=2)

            logger.info(f"Saved new version of {prompt_type} prompt: {version_hash}")
            return {"hash": version_hash, **prompt_data}
        except Exception as e:
            logger.error(f"Failed to save prompt version: {str(e)}")
            raise PromptManagerError(f"Failed to save prompt version: {str(e)}")

    def get_versions(self, prompt_type: str) -> List[Dict]:
        try:
            if prompt_type not in ["title_extraction", "content_analysis", "date_extraction"]:
                raise PromptManagerError(f"Invalid prompt type: {prompt_type}")

            versions = []
            prompt_dir = os.path.join(self.storage_dir, prompt_type)
            
            for filename in os.listdir(prompt_dir):
                if filename != "current.json" and filename.endswith('.json'):
                    version_hash = filename[:-5]  # Remove .json
                    with open(os.path.join(prompt_dir, filename), 'r') as f:
                        version_data = json.load(f)
                        versions.append({"hash": version_hash, **version_data})

            # Sort by creation date, newest first
            versions.sort(key=lambda x: x["created_at"], reverse=True)
            return versions
        except Exception as e:
            logger.error(f"Failed to get prompt versions: {str(e)}")
            raise PromptManagerError(f"Failed to get prompt versions: {str(e)}")

    def get_version(self, prompt_type: str, version_hash: str) -> Dict:
        try:
            if prompt_type not in ["title_extraction", "content_analysis", "date_extraction"]:
                raise PromptManagerError(f"Invalid prompt type: {prompt_type}")

            if version_hash == "current":
                path = self._get_current_path(prompt_type)
            else:
                path = self._get_version_path(prompt_type, version_hash)

            if not os.path.exists(path):
                raise PromptManagerError(f"Version {version_hash} not found")

            with open(path, 'r') as f:
                version_data = json.load(f)
                return {"hash": version_hash, **version_data}
        except Exception as e:
            logger.error(f"Failed to get prompt version: {str(e)}")
            raise PromptManagerError(f"Failed to get prompt version: {str(e)}")

    def restore_version(self, prompt_type: str, version_hash: str) -> Dict:
        try:
            if prompt_type not in ["title_extraction", "content_analysis"]:
                raise PromptManagerError(f"Invalid prompt type: {prompt_type}")

            # Get the version data
            version_data = self.get_version(prompt_type, version_hash)
            
            # Update current version
            current_path = self._get_current_path(prompt_type)
            with open(current_path, 'w') as f:
                json.dump(version_data, f, indent=2)

            logger.info(f"Restored version {version_hash} of {prompt_type} prompt")
            return version_data
        except Exception as e:
            logger.error(f"Failed to restore prompt version: {str(e)}")
            raise PromptManagerError(f"Failed to restore prompt version: {str(e)}")

    def get_prompt_types(self) -> List[Dict]:
        return [
            {"name": "title_extraction", "display_name": "Title Extraction"},
            {"name": "content_analysis", "display_name": "Content Analysis"},
            {"name": "date_extraction", "display_name": "Date Extraction"}
        ]

    def get_current_version(self, prompt_type: str) -> Dict:
        return self.get_version(prompt_type, "current")

    def compare_versions(self, prompt_type: str, version_a: str, version_b: str) -> Dict:
        try:
            if prompt_type not in ["title_extraction", "content_analysis"]:
                raise PromptManagerError(f"Invalid prompt type: {prompt_type}")

            version_a_data = self.get_version(prompt_type, version_a)
            version_b_data = self.get_version(prompt_type, version_b)
            
            return {
                "version_a": version_a_data,
                "version_b": version_b_data
            }
        except Exception as e:
            logger.error(f"Failed to compare prompt versions: {str(e)}")
            raise PromptManagerError(f"Failed to compare prompt versions: {str(e)}")

    def initialize_defaults(self, default_templates: Dict) -> None:
        """Initialize storage with default templates if no versions exist."""
        try:
            for prompt_type, template in default_templates.items():
                if prompt_type not in ["title_extraction", "content_analysis", "date_extraction"]:
                    logger.warning(f"Skipping unknown prompt type: {prompt_type}")
                    continue

                current_path = self._get_current_path(prompt_type)
                if not os.path.exists(current_path):
                    self.save_version(
                        prompt_type,
                        template["system_prompt"],
                        template["user_prompt"]
                    )
                    logger.info(f"Initialized default template for {prompt_type}")
        except Exception as e:
            logger.error(f"Failed to initialize default templates: {str(e)}")
            raise PromptManagerError(f"Failed to initialize default templates: {str(e)}") 