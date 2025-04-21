#!/usr/bin/env python3
"""
Initialize default configuration files.
This script copies default configuration templates to their locations if they
don't exist yet. Used for initial setup and after updates.
"""

import os
import json
import shutil
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Configuration mapping: target_path -> default template path
DEFAULT_CONFIGS = {
    "app/config/config.json": "app/config/defaults/config.default.json",
    "app/config/litellm_config.yaml": "app/config/defaults/litellm_config.default.yaml",
    "app/config/provider_config.json": "app/config/defaults/provider_config.default.json",
    "app/config/templates": "app/config/defaults/templates.default",
}

# Default .env template (minimal version)
DEFAULT_ENV = """# AunooAI Environment Configuration
# Add your environment-specific values below

# Database
DB_PATH=app/data/fnapp.db

# API Keys
OPENAI_API_KEY=
ANTHROPIC_API_KEY=

# Server Configuration
HOST=0.0.0.0
PORT=8000
"""


def get_project_root():
    """Get the project root directory."""
    script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    return script_dir.parent


def copy_default_templates():
    """Copy default configuration templates if targets don't exist."""
    root_dir = get_project_root()
    
    # Process each config file
    for target_rel_path, default_rel_path in DEFAULT_CONFIGS.items():
        target_path = root_dir / target_rel_path
        default_path = root_dir / default_rel_path
        
        # Skip if target already exists
        if target_path.exists():
            logger.info(f"Config already exists: {target_rel_path}")
            continue
            
        # Skip if default template doesn't exist
        if not default_path.exists():
            logger.warning(
                f"Default template not found: {default_rel_path}, skipping"
            )
            continue
            
        # Create parent directories if they don't exist
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Copy the default template
        if default_path.is_dir():
            shutil.copytree(default_path, target_path)
            logger.info(f"Created default directory: {target_rel_path}")
        else:
            shutil.copy2(default_path, target_path)
            logger.info(f"Created default file: {target_rel_path}")
    
    # Create .env file if it doesn't exist
    env_path = root_dir / ".env"
    if not env_path.exists():
        with open(env_path, "w") as f:
            f.write(DEFAULT_ENV)
        logger.info("Created default .env file")


def create_default_templates():
    """Create default template files in the defaults directory."""
    root_dir = get_project_root()
    defaults_dir = root_dir / "app/config/defaults"
    
    # Create defaults directory if it doesn't exist
    defaults_dir.mkdir(parents=True, exist_ok=True)
    
    # Create default config.json
    config_path = defaults_dir / "config.default.json"
    if not config_path.exists():
        default_config = {
            "app_name": "AunooAI",
            "debug": False,
            "log_level": "INFO",
            "default_models": {
                "text": "gpt-4o",
                "embedding": "text-embedding-3-small"
            },
            "max_tokens": 4000,
            "temperature": 0.7
        }
        with open(config_path, "w") as f:
            json.dump(default_config, f, indent=2)
        logger.info(f"Created default template: {config_path}")
    
    # Create default litellm_config.yaml
    litellm_path = defaults_dir / "litellm_config.default.yaml"
    if not litellm_path.exists():
        default_litellm = """# Default LiteLLM Configuration
model_list:
  - model_name: gpt-4o
    litellm_params:
      model: gpt-4o
      api_key: os.environ/OPENAI_API_KEY
  
  - model_name: claude-3
    litellm_params:
      model: claude-3-opus-20240229
      api_key: os.environ/ANTHROPIC_API_KEY

general_settings:
  max_tokens: 4000
  temperature: 0.7
"""
        with open(litellm_path, "w") as f:
            f.write(default_litellm)
        logger.info(f"Created default template: {litellm_path}")
    
    # Create default provider_config.json
    provider_path = defaults_dir / "provider_config.default.json"
    if not provider_path.exists():
        default_provider = {
            "openai": {
                "api_base": "https://api.openai.com/v1",
                "models": ["gpt-4o", "gpt-3.5-turbo"]
            },
            "anthropic": {
                "api_base": "https://api.anthropic.com",
                "models": ["claude-3-opus", "claude-3-sonnet"]
            }
        }
        with open(provider_path, "w") as f:
            json.dump(default_provider, f, indent=2)
        logger.info(f"Created default template: {provider_path}")
    
    # Create default templates directory
    templates_dir = defaults_dir / "templates.default"
    if not templates_dir.exists():
        templates_dir.mkdir(parents=True, exist_ok=True)
        
        # Add a sample template file
        sample_template = templates_dir / "report.json"
        sample_content = {
            "report_sections": {
                "categories": "### {title}\\n\\n**Source:** {news_source} | [Link]({url})\\n\\n{summary}\\n\\n**Sentiment:** {sentiment} | **Time to Impact:** {time_to_impact} | **Future Signal:** {future_signal}\\n\\n"
            }
        }
        with open(sample_template, "w") as f:
            json.dump(sample_content, f, indent=2)
        logger.info(f"Created default template directory: {templates_dir}")


def main():
    """Main function to initialize default configurations."""
    # Create default templates first
    create_default_templates()
    
    # Copy them to target locations if needed
    copy_default_templates()
    
    logger.info("Default configuration setup complete")


if __name__ == "__main__":
    main() 