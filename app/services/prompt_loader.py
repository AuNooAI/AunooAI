"""
Prompt Management Service

Loads and manages AI prompts from data/prompts/ directory.
Supports versioning, template variables, and CRUD operations.
"""

from pathlib import Path
import json
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
import hashlib
import logging

logger = logging.getLogger(__name__)


class PromptLoader:
    """Load and manage prompts from data/prompts/ directory."""

    PROMPTS_DIR = Path("data/prompts")

    @classmethod
    def load_prompt(
        cls,
        feature: str,
        prompt_name: str = "current",
        subfolder: Optional[str] = None
    ) -> Dict[str, Any]:
        """Load a prompt by feature and name.

        Args:
            feature: Feature name (e.g., 'market_signals', 'trend_convergence')
            prompt_name: Prompt file name without .json (default: 'current')
            subfolder: Optional subfolder within feature (e.g., 'consensus_analysis')

        Returns:
            Dict with system_prompt, user_prompt, and metadata

        Raises:
            FileNotFoundError: If prompt file doesn't exist
        """
        if subfolder:
            prompt_path = cls.PROMPTS_DIR / feature / subfolder / f"{prompt_name}.json"
        else:
            prompt_path = cls.PROMPTS_DIR / feature / f"{prompt_name}.json"

        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt not found: {prompt_path}")

        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                prompt_data = json.load(f)

            logger.info(f"Loaded prompt: {feature}/{subfolder or ''}/{prompt_name}")
            return prompt_data

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in prompt file {prompt_path}: {e}")
            raise ValueError(f"Invalid JSON in prompt file: {e}")
        except Exception as e:
            logger.error(f"Error loading prompt {prompt_path}: {e}")
            raise

    @classmethod
    def save_prompt(
        cls,
        feature: str,
        prompt_data: Dict[str, Any],
        set_as_current: bool = False,
        subfolder: Optional[str] = None
    ) -> str:
        """Save a new prompt version.

        Args:
            feature: Feature name
            prompt_data: Prompt dictionary
            set_as_current: If True, also save as current.json
            subfolder: Optional subfolder within feature

        Returns:
            Path to saved prompt file
        """
        # Ensure feature directory exists
        if subfolder:
            feature_dir = cls.PROMPTS_DIR / feature / subfolder
        else:
            feature_dir = cls.PROMPTS_DIR / feature

        feature_dir.mkdir(parents=True, exist_ok=True)

        # Add metadata
        if "created_at" not in prompt_data:
            prompt_data["created_at"] = datetime.utcnow().isoformat()
        prompt_data["updated_at"] = datetime.utcnow().isoformat()

        # Generate version hash
        content_hash = hashlib.md5(
            json.dumps(prompt_data, sort_keys=True).encode()
        ).hexdigest()[:16]

        # Save versioned file
        version = prompt_data.get("version", "1.0.0")
        filename_base = subfolder if subfolder else feature
        versioned_path = feature_dir / f"{filename_base}_v{version}_{content_hash}.json"

        with open(versioned_path, 'w', encoding='utf-8') as f:
            json.dump(prompt_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved prompt version: {versioned_path}")

        # Optionally set as current
        if set_as_current:
            current_path = feature_dir / "current.json"
            with open(current_path, 'w', encoding='utf-8') as f:
                json.dump(prompt_data, f, indent=2, ensure_ascii=False)

            logger.info(f"Set as current prompt: {current_path}")

        return str(versioned_path)

    @classmethod
    def list_prompts(cls, feature: str, subfolder: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all prompts for a feature.

        Args:
            feature: Feature name
            subfolder: Optional subfolder within feature

        Returns:
            List of prompt metadata dictionaries
        """
        if subfolder:
            feature_dir = cls.PROMPTS_DIR / feature / subfolder
        else:
            feature_dir = cls.PROMPTS_DIR / feature

        if not feature_dir.exists():
            return []

        prompts = []
        for p in feature_dir.glob("*.json"):
            try:
                # Load basic metadata
                with open(p, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                prompts.append({
                    "filename": p.name,
                    "path": str(p),
                    "modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
                    "version": data.get("version", "unknown"),
                    "description": data.get("description", "No description"),
                    "is_current": p.name == "current.json"
                })
            except Exception as e:
                logger.warning(f"Error reading prompt metadata from {p}: {e}")
                continue

        # Sort by modification time, newest first
        prompts.sort(key=lambda x: x["modified"], reverse=True)

        return prompts

    @classmethod
    def get_prompt_template(
        cls,
        prompt_data: Dict[str, Any],
        variables: Dict[str, Any]
    ) -> Tuple[str, str]:
        """Fill prompt template with variables.

        Args:
            prompt_data: Loaded prompt dictionary
            variables: Variables to substitute (e.g., {"topic": "AI", "article_count": 50})

        Returns:
            Tuple of (system_prompt, user_prompt) with variables filled
        """
        system_prompt = prompt_data.get("system_prompt", "")
        user_prompt = prompt_data.get("user_prompt", "")

        # Substitute variables
        for key, value in variables.items():
            placeholder = "{" + key + "}"
            system_prompt = system_prompt.replace(placeholder, str(value))
            user_prompt = user_prompt.replace(placeholder, str(value))

        return system_prompt, user_prompt

    @classmethod
    def list_features(cls) -> List[str]:
        """List all features with prompts.

        Returns:
            List of feature names
        """
        if not cls.PROMPTS_DIR.exists():
            return []

        features = [
            d.name for d in cls.PROMPTS_DIR.iterdir()
            if d.is_dir() and not d.name.startswith('.')
        ]

        return sorted(features)

    @classmethod
    def validate_prompt_schema(cls, prompt_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate prompt data structure.

        Args:
            prompt_data: Prompt dictionary to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        required_fields = ["prompt_name", "feature", "system_prompt", "user_prompt"]

        for field in required_fields:
            if field not in prompt_data:
                return False, f"Missing required field: {field}"

        # Validate system_prompt and user_prompt are non-empty strings
        if not isinstance(prompt_data["system_prompt"], str) or not prompt_data["system_prompt"].strip():
            return False, "system_prompt must be a non-empty string"

        if not isinstance(prompt_data["user_prompt"], str) or not prompt_data["user_prompt"].strip():
            return False, "user_prompt must be a non-empty string"

        return True, None

    @classmethod
    def get_prompt_variables(cls, prompt_data: Dict[str, Any]) -> List[str]:
        """Extract variable names from prompt template.

        Args:
            prompt_data: Prompt dictionary

        Returns:
            List of variable names (without braces)
        """
        import re

        system_prompt = prompt_data.get("system_prompt", "")
        user_prompt = prompt_data.get("user_prompt", "")

        combined = system_prompt + " " + user_prompt

        # Find all {variable} patterns
        variables = re.findall(r'\{(\w+)\}', combined)

        # Return unique variables
        return list(set(variables))
