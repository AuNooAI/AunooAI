#!/usr/bin/env python3
"""Update the market signals prompt to require actual quote extraction."""

import json

# Read the current prompt
with open('data/prompts/market_signals/current.json', 'r') as f:
    prompt_data = json.load(f)

# Get the current user_prompt
user_prompt = prompt_data['user_prompt']

# Define the old quotes section
old_quotes_section = """4. **Quotes:**
   - Extract 2-3 impactful quotes from articles or create synthetic quotes based on consensus
   - **Source**: Format as "Publication Name (YYYY-MM-DD)" using the Publication and Publication Date from the articles
   - **URL**: Include the URL field from the article so users can click through to the source
   - **Context**: Brief context about where this quote appears (e.g., "Analysis of market trends", "CEO interview")
   - **Relevance**: Why this quote matters for the analysis"""

# Define the new quotes section
new_quotes_section = """4. **Quotes:**
   - **CRITICAL**: You MUST extract ACTUAL quotes directly from the "Full Content" field provided for each article
   - Do NOT create synthetic or paraphrased quotes - extract verbatim text from the article content
   - Look for impactful statements, key findings, expert opinions, or significant claims in the Full Content
   - Extract 2-3 direct quotes that best represent the key themes or findings
   - **Source**: Format as "Publication Name (YYYY-MM-DD)" using the Publication and Publication Date from the articles
   - **URL**: Include the exact URL field from the article so users can click through to verify the quote
   - **Context**: Brief context about where this quote appears in the article (e.g., "Opening paragraph", "Expert testimony", "Research findings")
   - **Relevance**: Why this specific quote matters for the analysis
   - If you cannot find suitable quotes in the Full Content, return an empty quotes array rather than creating synthetic quotes"""

# Replace the section
updated_prompt = user_prompt.replace(old_quotes_section, new_quotes_section)

# Verify the replacement worked
if updated_prompt == user_prompt:
    print("❌ ERROR: Replacement failed - section not found")
    exit(1)

# Update the prompt data
prompt_data['user_prompt'] = updated_prompt
prompt_data['updated_at'] = "2025-11-18T15:30:00Z"
prompt_data['version'] = "1.0.1"

# Write back to file
with open('data/prompts/market_signals/current.json', 'w') as f:
    json.dump(prompt_data, f, indent=2)

print("✅ SUCCESS: Prompt updated to require actual quote extraction")
print("\nChanges made:")
print("- Version: 1.0.0 → 1.0.1")
print("- Updated: 2025-11-18T15:30:00Z")
print("- Quotes section: Now REQUIRES extraction from Full Content")
print("- Quotes section: FORBIDS synthetic/paraphrased quotes")
print("\nThe LLM will now extract actual quotes from the raw_markdown content!")
