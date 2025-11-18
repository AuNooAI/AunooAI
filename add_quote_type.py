#!/usr/bin/env python3
"""Add quote_type field to market signals prompt."""

import json

# Read the current prompt
with open('data/prompts/market_signals/current.json', 'r') as f:
    prompt_data = json.load(f)

# Update the user_prompt to include quote_type in examples
user_prompt = prompt_data['user_prompt']

# Find and replace the example quotes section
old_example = '''"quotes": [
    {
      "text": "The AI bubble may burst soon, followed by a period of reckoning, and then the emergence of productive AI-based business practices.",
      "source": "TechCrunch (2025-01-03)",
      "url": "https://techcrunch.com/article-url",
      "context": "Analysis of market trends",
      "relevance": "Indicates timing and sequence of market correction"
    },
    {
      "text": "Investments in [AI superintelligence] are expected to require patience, as transformative outcomes are projected to emerge over a protracted period.",
      "source": "Financial Times (2025-01-02)",
      "url": "https://ft.com/article-url",
      "context": "Investment outlook report",
      "relevance": "Warns against short-term AGI expectations"
    }
  ]'''

new_example = '''"quotes": [
    {
      "text": "The AI bubble may burst soon, followed by a period of reckoning, and then the emergence of productive AI-based business practices.",
      "source": "TechCrunch (2025-01-03)",
      "url": "https://techcrunch.com/article-url",
      "context": "Analysis of market trends",
      "relevance": "Indicates timing and sequence of market correction",
      "quote_type": "direct_quote"
    },
    {
      "text": "Investments in [AI superintelligence] are expected to require patience, as transformative outcomes are projected to emerge over a protracted period.",
      "source": "Financial Times (2025-01-02)",
      "url": "https://ft.com/article-url",
      "context": "Investment outlook report",
      "relevance": "Warns against short-term AGI expectations",
      "quote_type": "direct_quote"
    }
  ]'''

# Replace in user_prompt
if old_example in user_prompt:
    user_prompt = user_prompt.replace(old_example, new_example)
    print("✅ Updated example quotes in user_prompt")
else:
    print("❌ Could not find example quotes in user_prompt")
    exit(1)

# Update the prompt data
prompt_data['user_prompt'] = user_prompt
prompt_data['version'] = "1.0.2"

# Write back
with open('data/prompts/market_signals/current.json', 'w') as f:
    json.dump(prompt_data, f, indent=2)

print(f"✅ Updated prompt to version {prompt_data['version']}")
print("✅ Added quote_type='direct_quote' to example quotes")
print("\nThe LLM will now include quote_type field in responses!")
