# Auspex Plugin Tool System

A plugin architecture for creating custom analysis tools that integrate with Auspex's AI chat interface.

## Overview

The plugin system allows developers to create specialized analysis tools by defining:
1. **Metadata** - Tool name, description, triggers
2. **Actions** - Data sources to query (vector search, database, web)
3. **Prompt** - LLM instructions for generating the analysis

Plugins are automatically discovered and appear as clickable badges in the Auspex chat interface.

## Directory Structure

```
data/auspex/plugins/
├── README.md                    # This file
├── newsletter_generator/
│   ├── tool.md                  # Required: Tool definition
│   └── config.json              # Optional: Configuration overrides
├── sentiment_analysis/
│   ├── tool.md
│   └── handler.py               # Optional: Custom Python handler
└── my_custom_tool/
    └── tool.md
```

## Creating a Plugin

### Minimal Plugin (tool.md only)

Create a folder under `data/auspex/plugins/` with a `tool.md` file:

```yaml
---
name: "my_analysis_tool"
version: "1.0.0"
type: "tool"
category: "analysis"
description: "Short description shown in the UI badge tooltip"

parameters:
  - name: topic
    type: string
    required: true
    description: "Topic to analyze"
  - name: limit
    type: integer
    default: 50
    description: "Maximum articles to analyze"

triggers:
  - patterns: ["keyword1", "keyword2", "regex.*pattern"]
    priority: high
  - patterns: ["secondary", "triggers"]
    priority: medium

actions:
  - vector_search
  - db_search

prompt: |
  You are an expert analyst. Analyze {article_count} articles about "{topic}".

  ARTICLES:
  {articles}

  Provide your analysis with:
  ## Section 1
  - Point 1
  - Point 2

  ## Section 2
  Content here...

  IMPORTANT: Cite sources using markdown links: [Article Title](URL)
---

# Tool Documentation

This section (after the closing ---) is markdown documentation.
It's not used by the system but helps developers understand the tool.
```

### Configuration Options

#### Parameters

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Unique tool identifier (lowercase, underscores) |
| `version` | string | Yes | Semantic version (e.g., "1.0.0") |
| `type` | string | Yes | Always "tool" |
| `category` | string | Yes | Category for grouping: "analysis", "content", "research", "search" |
| `description` | string | Yes | Short description for UI tooltip |
| `parameters` | array | No | Input parameters the tool accepts |
| `triggers` | array | Yes | Patterns that activate this tool |
| `actions` | array | Yes | Data sources to query |
| `prompt` | string | Yes* | LLM prompt template (*unless using custom handler) |
| `requires_api_key` | string | No | Environment variable required (tool hidden if missing) |

#### Parameter Definition

```yaml
parameters:
  - name: topic           # Parameter name
    type: string          # Type: string, integer, float, boolean, array
    required: true        # Is this required?
    default: "AI"         # Default value if not provided
    description: "..."    # Help text
    enum: ["opt1", "opt2"] # Optional: restrict to specific values
```

#### Trigger Patterns

Triggers determine when your tool activates based on user messages:

```yaml
triggers:
  - patterns: ["newsletter", "weekly newsletter", "generate newsletter"]
    priority: high      # 0.9 score - takes precedence
  - patterns: ["news roundup", "digest"]
    priority: medium    # 0.6 score
  - patterns: ["summarize.*week"]  # Supports regex
    priority: low       # 0.3 score
```

**Priority levels:**
- `high` (0.9) - Primary triggers, tool's main purpose
- `medium` (0.6) - Secondary triggers
- `low` (0.3) - Fallback triggers

When multiple tools match, the highest score wins.

#### Available Actions

| Action | Description | Data Provided |
|--------|-------------|---------------|
| `vector_search` | Semantic search using embeddings | Articles with similarity scores |
| `db_search` | SQL database search | Articles from PostgreSQL |
| `sentiment_analysis` | Sentiment distribution | `{sentiment}` variable |
| `bias_analysis` | Political bias distribution | `{bias}` variable |
| `web_search` | Google Custom Search API | `{web_search}` variable |

### Prompt Template Variables

The following variables are available in your prompt:

| Variable | Description |
|----------|-------------|
| `{topic}` | The current topic being analyzed |
| `{query}` | User's original query |
| `{article_count}` | Number of articles found |
| `{articles}` | Formatted article data with URLs |
| `{sentiment}` | Sentiment distribution (if action enabled) |
| `{bias}` | Bias distribution (if action enabled) |
| `{web_search}` | Web search results (if action enabled) |

### Article Data Format

Articles passed to `{articles}` are formatted as:

```
1. **Article Title**
   Source: Reuters | Date: 2024-01-15
   URL: https://example.com/article
   Summary: Brief summary text...
   Sentiment: Positive

2. **Another Article**
   Source: BBC | Date: 2024-01-14
   URL: https://example.com/article2
   Summary: Another summary...
```

**Important:** Always instruct the LLM to use the URL field for citations!

## Best Practices

### 1. URL Citations

Always include explicit instructions for URL citations:

```yaml
prompt: |
  CRITICAL: All citations must include clickable markdown links: [Article Title](URL)
  Every article in the data has a URL field - USE IT!

  WRONG: "(Reuters, Jan 15)" - No URL!
  CORRECT: "([Article Title](https://example.com), Reuters, Jan 15)"
```

### 2. Structured Output

Use markdown tables for comparative data:

```yaml
prompt: |
  ### Distribution Table

  | Category | Count | Percentage |
  |----------|-------|------------|
  | Category1 | X | X% |
  | Category2 | X | X% |
```

### 3. Source References Section

Include a dedicated sources section:

```yaml
prompt: |
  ### Source References

  List key articles with clickable links:
  | Source | Article |
  |--------|---------|
  | [Source] | [Title](URL) |
```

### 4. Clear Section Headers

Use consistent markdown headers for scannable output:

```yaml
prompt: |
  ## Main Analysis: {topic}

  ### Section 1
  Content...

  ### Section 2
  Content...

  ### Key Takeaways
  - Point 1
  - Point 2
```

## Optional: config.json

Override default settings:

```json
{
  "model": "gpt-4o",
  "max_tokens": 4000,
  "temperature": 0.7,
  "custom_setting": "value"
}
```

## Optional: Custom Handler (handler.py)

For complex logic beyond prompt-based tools:

```python
from app.services.tool_plugin_base import ToolHandler, ToolResult

class MyCustomHandler(ToolHandler):
    async def execute(self, params: dict, context: dict) -> ToolResult:
        # Access context
        topic = params.get('topic') or context.get('topic')
        db = context.get('db')
        vector_search = context.get('vector_store')
        ai_model_getter = context.get('ai_model')

        # Your custom logic here
        results = await self.custom_analysis(topic)

        return ToolResult(
            success=True,
            data={
                'analysis': results,
                'article_count': len(results)
            },
            message="Analysis complete"
        )

    async def custom_analysis(self, topic):
        # Implementation
        pass
```

## API Key Requirements

For tools requiring external APIs:

```yaml
---
name: "web_search"
# ... other config ...

requires_api_key: GOOGLE_API_KEY
---
```

The tool will only load if `GOOGLE_API_KEY` environment variable is set.

## Testing Your Plugin

1. Create your `tool.md` in `data/auspex/plugins/your_tool/`
2. Restart the service: `sudo systemctl restart [service-name]`
3. Check logs for loading: `journalctl -u [service-name] | grep plugin`
4. Open Auspex chat - your tool should appear as a badge
5. Click the badge or type a trigger phrase to test

## Example Plugins

### Newsletter Generator
- **Triggers:** "newsletter", "weekly roundup"
- **Actions:** vector_search, db_search, sentiment_analysis
- **Output:** Formatted newsletter with sections

### Sentiment Analysis
- **Triggers:** "sentiment", "positive", "negative"
- **Actions:** vector_search, sentiment_analysis
- **Output:** Sentiment distribution and analysis

### Partisan Analysis
- **Triggers:** "bias", "partisan", "political"
- **Actions:** vector_search, bias_analysis
- **Output:** Political bias breakdown with comparison tables

### Future Impact
- **Triggers:** "future", "prediction", "forecast"
- **Actions:** vector_search, db_search
- **Output:** Predictions and risk assessment

## Troubleshooting

### Plugin Not Loading
- Check file permissions: `chmod 644 tool.md`
- Verify YAML syntax (use a YAML validator)
- Check logs: `journalctl -u [service] | grep -i plugin`

### URLs Not Appearing in Output
- Add explicit URL instructions at the START of your prompt
- Include "WRONG vs CORRECT" examples
- Remind at end: "Cite with markdown links: [Title](URL)"

### Prompt Truncated
- Don't use `---` inside your prompt (YAML document separator)
- Use `##` instead for section dividers

### Tool Not Triggering
- Check trigger patterns match user input
- Verify priority is appropriate
- Test with exact trigger phrases first
