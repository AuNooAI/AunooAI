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
    # Valid prompt types including dashboard features
    VALID_PROMPT_TYPES = [
        "title_extraction",
        "content_analysis",
        "date_extraction",
        "relevance_analysis",
        "consensus_analysis",
        "strategic_recommendations",
        "market_signals",
        "impact_timeline",
        "future_horizons"
    ]

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
            for prompt_type in self.VALID_PROMPT_TYPES:
                prompt_dir = os.path.join(self.storage_dir, prompt_type)
                os.makedirs(prompt_dir, exist_ok=True)
                logger.debug(f"Created prompt directory: {prompt_dir}")

                # Ensure current.json exists with empty template
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

    def _get_next_version(self, prompt_type: str) -> str:
        try:
            versions = self.get_versions(prompt_type)
            if not versions:
                return "1.0.0"
            
            latest = versions[0]  # Already sorted newest first
            major, minor, patch = map(int, latest["version"].split("."))
            return f"{major}.{minor}.{patch + 1}"
        except Exception:
            return "1.0.0"  # Fallback if anything goes wrong

    def save_version(self, prompt_type: str, system_prompt: str, user_prompt: str) -> Dict:
        try:
            if prompt_type not in self.VALID_PROMPT_TYPES:
                raise PromptManagerError(f"Invalid prompt type: {prompt_type}")

            # Get next version number
            next_version = self._get_next_version(prompt_type)

            prompt_data = {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "version": next_version,
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

            logger.info(f"Saved new version {next_version} of {prompt_type} prompt: {version_hash}")
            return {"hash": version_hash, **prompt_data}
        except Exception as e:
            logger.error(f"Failed to save prompt version: {str(e)}")
            raise PromptManagerError(f"Failed to save prompt version: {str(e)}")

    def get_versions(self, prompt_type: str) -> List[Dict]:
        try:
            if prompt_type not in self.VALID_PROMPT_TYPES:
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
            if prompt_type not in self.VALID_PROMPT_TYPES:
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
            if prompt_type not in self.VALID_PROMPT_TYPES:
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
            {"name": "date_extraction", "display_name": "Date Extraction"},
            {"name": "relevance_analysis", "display_name": "Relevance Analysis"},
            {"name": "consensus_analysis", "display_name": "Consensus Analysis (Dashboard)"},
            {"name": "strategic_recommendations", "display_name": "Strategic Recommendations (Dashboard)"},
            {"name": "market_signals", "display_name": "Market Signals (Dashboard)"},
            {"name": "impact_timeline", "display_name": "Impact Timeline (Dashboard)"},
            {"name": "future_horizons", "display_name": "Future Horizons (Dashboard)"}
        ]

    def get_current_version(self, prompt_type: str) -> Dict:
        return self.get_version(prompt_type, "current")

    def compare_versions(self, prompt_type: str, version_a: str, version_b: str) -> Dict:
        try:
            if prompt_type not in self.VALID_PROMPT_TYPES:
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
                if prompt_type not in self.VALID_PROMPT_TYPES:
                    logger.warning(f"Skipping unknown prompt type: {prompt_type}")
                    continue

                current_path = self._get_current_path(prompt_type)
                versions = self.get_versions(prompt_type)
                
                # Initialize if no current version exists or if there are no versions
                if not os.path.exists(current_path) or not versions:
                    self.save_version(
                        prompt_type,
                        template["system_prompt"],
                        template["user_prompt"]
                    )
                    logger.info(f"Initialized default template for {prompt_type}")
        except Exception as e:
            logger.error(f"Failed to initialize default templates: {str(e)}")
            raise PromptManagerError(f"Failed to initialize default templates: {str(e)}")

    def delete_version(self, prompt_type: str, version_hash: str) -> None:
        try:
            if prompt_type not in self.VALID_PROMPT_TYPES:
                raise PromptManagerError(f"Invalid prompt type: {prompt_type}")

            if version_hash == "current":
                raise PromptManagerError("Cannot delete current version")

            version_path = self._get_version_path(prompt_type, version_hash)
            if not os.path.exists(version_path):
                raise PromptManagerError(f"Version {version_hash} not found")

            os.remove(version_path)
            logger.info(f"Deleted version {version_hash} of {prompt_type} prompt")
        except Exception as e:
            logger.error(f"Failed to delete prompt version: {str(e)}")
            raise PromptManagerError(f"Failed to delete prompt version: {str(e)}")

    def restore_to_default(self, prompt_type: str) -> Dict:
        """Restore prompt to bundled default by reloading from PromptLoader.

        For dashboard features, this reloads from data/prompts/{feature}/current.json
        and preserves it as the current version.

        Args:
            prompt_type: The feature to restore (e.g., 'consensus_analysis')

        Returns:
            Dict with restored prompt data
        """
        try:
            if prompt_type not in self.VALID_PROMPT_TYPES:
                raise PromptManagerError(f"Invalid prompt type: {prompt_type}")

            # Dashboard prompts are stored directly under data/prompts/{feature}/
            # Load the bundled default (which is the checked-in current.json)
            from app.services.prompt_loader import PromptLoader

            try:
                default_prompt = PromptLoader.load_prompt(prompt_type, "current")
            except FileNotFoundError:
                raise PromptManagerError(f"No default prompt found for {prompt_type}")

            # Extract system and user prompts
            system_prompt = default_prompt.get("system_prompt", "")
            user_prompt = default_prompt.get("user_prompt", "")

            # Save as a new version with current timestamp
            # This preserves the restore action in version history
            version_data = {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "version": self._get_next_version(prompt_type),
                "created_at": datetime.now().isoformat(),
                "restored_from_default": True
            }

            # Compute hash and save as versioned file
            version_hash = self._compute_hash(version_data)
            version_path = self._get_version_path(prompt_type, version_hash)
            with open(version_path, 'w') as f:
                json.dump(version_data, f, indent=2)

            # Update current.json with the default
            current_path = self._get_current_path(prompt_type)
            with open(current_path, 'w') as f:
                json.dump(version_data, f, indent=2)

            logger.info(f"Restored {prompt_type} to default version")
            return {"hash": version_hash, **version_data}

        except Exception as e:
            logger.error(f"Failed to restore to default: {str(e)}")
            raise PromptManagerError(f"Failed to restore to default: {str(e)}") 