#!/usr/bin/env python3
"""
Script to restore the default "AI and Machine Learning" topic to the configuration.
This fixes the error: "Default topic 'AI and Machine Learning' not found in configuration"
"""

import os
import sys
import json
import logging
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def get_config_path():
    """Get the path to the config.json file."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, '..'))
    config_path = os.path.join(project_root, 'app', 'config', 'config.json')
    return config_path

def backup_config(config_path):
    """Create a backup of the current config file."""
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{config_path}.backup_{timestamp}"
    
    try:
        import shutil
        shutil.copy2(config_path, backup_path)
        logger.info(f"Config backed up to: {backup_path}")
        return backup_path
    except Exception as e:
        logger.error(f"Failed to backup config: {e}")
        return None

def get_default_ai_ml_topic():
    """Get the default AI and Machine Learning topic configuration."""
    return {
        "name": "AI and Machine Learning",
        "categories": [
            "AI Warbots",
            "AI Business",
            "Releases and Announcements",
            "Sovereign AI & AI Nationalism",
            "AI Copyright, Regulation, and Antitrust",
            "AI at Work and Employment",
            "AI and Society",
            "AI Trust, Risk, and Security Management",
            "AI in Finance",
            "AI in Journalism",
            "AI Healthcare",
            "AI in Education",
            "AI in Law and the Legal Profession",
            "AI in Science",
            "AI in Art and the Media",
            "AI in Software Development",
            "AI Ethics",
            "AI and Robotics",
            "AI in the Data Center",
            "AI Carbon Footprint",
            "The Path to AGI",
            "Interesting Papers & Articles on Applied AI",
            "Other"
        ],
        "future_signals": [
            "AI is hype",
            "AI has plateaued",
            "AI will evolve gradually",
            "AI will accelerate",
            "AI is a bubble"
        ],
        "sentiment": [
            "Hyperbolic",
            "Positive",
            "Neutral",
            "Negative",
            "Critical"
        ],
        "time_to_impact": [
            "Immediate",
            "Short-term",
            "Mid-term",
            "Long-term"
        ],
        "driver_types": [
            "Accelerator",
            "Delayer",
            "Blocker",
            "Initiator",
            "Terminator",
            "Unknown",
            "Catalyst"
        ]
    }

def restore_default_topic():
    """Restore the default AI and Machine Learning topic to the configuration."""
    config_path = get_config_path()
    
    if not os.path.exists(config_path):
        logger.error(f"Config file not found: {config_path}")
        return False
    
    try:
        # Load current config
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Check if topics exist
        if 'topics' not in config:
            config['topics'] = []
        
        # Check if AI and Machine Learning topic already exists
        topic_names = [topic['name'] for topic in config['topics']]
        if "AI and Machine Learning" in topic_names:
            logger.info("AI and Machine Learning topic already exists in configuration")
            return True
        
        # Backup the current config
        backup_path = backup_config(config_path)
        
        # Add the default topic at the beginning of the list
        default_topic = get_default_ai_ml_topic()
        config['topics'].insert(0, default_topic)
        
        # Save the updated config
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        logger.info("Successfully restored 'AI and Machine Learning' topic to configuration")
        logger.info(f"Config file updated: {config_path}")
        if backup_path:
            logger.info(f"Original config backed up to: {backup_path}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error restoring default topic: {e}")
        return False

def main():
    """Main function."""
    logger.info("Default Topic Restoration Tool")
    logger.info("=" * 50)
    
    config_path = get_config_path()
    logger.info(f"Config file: {config_path}")
    
    if restore_default_topic():
        logger.info("✅ Default topic restoration completed successfully")
        logger.info("The application should now start without the topic error")
        return 0
    else:
        logger.error("❌ Failed to restore default topic")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 