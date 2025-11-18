#!/usr/bin/env python3
"""Add quote_type instruction to prompt."""

import json

# Read the current prompt
with open('data/prompts/market_signals/current.json', 'r') as f:
    prompt_data = json.load(f)

user_prompt = prompt_data['user_prompt']

# Add the quote_type instruction after relevance
old_text = '   - **Relevance**: Why this specific quote matters for the analysis\n   - If you cannot find suitable quotes'

new_text = '   - **Relevance**: Why this specific quote matters for the analysis\n   - **quote_type**: MUST be set to "direct_quote" for all extracted quotes (this controls UI styling - direct quotes display in blue, synthetic commentary in yellow)\n   - If you cannot find suitable quotes'

if old_text in user_prompt:
    user_prompt = user_prompt.replace(old_text, new_text)
    print("✅ Added quote_type instruction")
else:
    print("❌ Could not find text to replace")
    exit(1)

prompt_data['user_prompt'] = user_prompt

# Write back
with open('data/prompts/market_signals/current.json', 'w') as f:
    json.dump(prompt_data, f, indent=2)

print("✅ Updated prompt with quote_type instruction")
