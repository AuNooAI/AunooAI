"""
Quick test script for PromptLoader service
"""

import sys
import json
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.prompt_loader import PromptLoader


def test_prompt_loader():
    """Test PromptLoader functionality."""

    print("🧪 Testing PromptLoader Service")
    print("="*60)

    # Test 1: List features
    print("\n1. Testing list_features()...")
    features = PromptLoader.list_features()
    print(f"   ✅ Found {len(features)} features: {features}")

    # Test 2: Load market_signals prompt
    print("\n2. Testing load_prompt('market_signals')...")
    try:
        prompt = PromptLoader.load_prompt("market_signals", "current")
        print(f"   ✅ Loaded prompt: {prompt.get('prompt_name')}")
        print(f"   📋 Version: {prompt.get('version')}")
        print(f"   📝 Description: {prompt.get('description')}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

    # Test 3: Get variables from prompt
    print("\n3. Testing get_prompt_variables()...")
    variables = PromptLoader.get_prompt_variables(prompt)
    print(f"   ✅ Found {len(variables)} variables: {variables}")

    # Test 4: Template substitution
    print("\n4. Testing get_prompt_template()...")
    test_vars = {
        "topic": "AI Adoption",
        "article_count": "50",
        "date_range": "Last 30 days",
        "articles": "[Test article content]"
    }

    system_prompt, user_prompt = PromptLoader.get_prompt_template(prompt, test_vars)

    # Check if variables were substituted
    if "{topic}" in user_prompt or "{article_count}" in user_prompt:
        print(f"   ❌ Variables not substituted properly")
        return False
    else:
        print(f"   ✅ Variables substituted successfully")
        print(f"   📊 System prompt length: {len(system_prompt)} chars")
        print(f"   📄 User prompt length: {len(user_prompt)} chars")

    # Test 5: Validate prompt schema
    print("\n5. Testing validate_prompt_schema()...")
    is_valid, error = PromptLoader.validate_prompt_schema(prompt)
    if is_valid:
        print(f"   ✅ Prompt schema is valid")
    else:
        print(f"   ❌ Prompt schema invalid: {error}")
        return False

    # Test 6: List prompts
    print("\n6. Testing list_prompts('market_signals')...")
    prompts = PromptLoader.list_prompts("market_signals")
    print(f"   ✅ Found {len(prompts)} prompt(s)")
    for p in prompts:
        print(f"      - {p['filename']} (v{p['version']}) - {p['description'][:50]}...")

    # Test 7: Check expected output schema
    print("\n7. Checking expected output schema...")
    schema = prompt.get("expected_output_schema", {})
    required = schema.get("required", [])
    print(f"   ✅ Required fields: {required}")

    print("\n" + "="*60)
    print("✅ All tests passed! PromptLoader is working correctly.")
    return True


if __name__ == "__main__":
    success = test_prompt_loader()
    sys.exit(0 if success else 1)
