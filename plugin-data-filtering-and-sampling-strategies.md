---
description: >-
  This document explains how Auspex plugin tools filter and sample articles for
  analysis, and how to extend the system with new filtering strategies.
---

# Plugin Data Filtering & Sampling Strategies

### Overview

When a user requests analysis (e.g., "Partisan Analysis", "Future Impact"), the system needs to fetch relevant articles. Rather than using generic vector search (which clusters around semantic similarity), specialized plugins use **targeted SQL queries** to fetch articles with the specific data fields needed for that analysis type.

### Architecture

```
User Request ("Partisan Analysis for __all__")
    │
    ▼
┌─────────────────────────────────────┐
│  _should_use_tools()                │  ← Keyword detection
│  (auspex_service.py)                │
│  Checks for: "bias", "partisan",    │
│  "future", "impact", etc.           │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  _check_plugin_tools()              │  ← Topic conversion
│  (auspex_service.py)                │
│  Converts __all__ → None for        │
│  cross-topic mode                   │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  tool_registry.find_matching_tools()│  ← Plugin matching
│  (tool_plugin_base.py)              │
│  Matches triggers in tool.md files  │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  tool_registry.execute_tool()       │  ← Handler dispatch
│  Gets PromptOnlyToolHandler for     │
│  the matched tool                   │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  PromptOnlyToolHandler.execute()    │  ← Action execution
│  (tool_plugin_base.py)              │
│  Runs actions defined in tool.md    │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  DatabaseQueryFacade methods        │  ← Data filtering
│  get_articles_with_bias_data()      │
│  get_articles_with_future_signals() │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  Distribution calculation           │  ← Statistics
│  _get_bias_distribution_from_field()│
│  _get_future_signal_distribution()  │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  LLM Prompt with {placeholders}     │  ← Analysis
│  {articles}, {bias}, {future_signals}│
└─────────────────────────────────────┘
```

### Current Filtering Strategies

#### 1. Bias Analysis (`bias_analysis` action)

**Purpose:** Fetch articles that have political bias data for partisan/media bias analysis.

**Database Fields Used:**

* `bias` - Political leaning (e.g., "right-center", "left", "least biased")
* `bias_source` - Source of the bias rating
* `news_source` - For grouping by source

**Facade Method:** `get_articles_with_bias_data(topic_name, limit, days_back)`

```python
# Filters for articles WHERE:
# - bias IS NOT NULL
# - bias != ''
# - publication_date >= start_date
# - topic = topic_name (if specified)
```

**Normalization:** Raw bias values are normalized to standard categories:

* "right-center" → "Center-Right"
* "left-center" → "Center-Left"
* "least biased" → "Center"
* "far right", "extreme right" → "Far-Right"
* etc.

**Distribution Method:** `_get_bias_distribution_from_field(articles)`

Returns:

```python
{
    'distribution': {'Center-Right': 150, 'Center-Left': 120, ...},
    'percentages': {'Center-Right': 30.5, 'Center-Left': 24.4, ...},
    'total_articles': 492,
    'dominant': 'Center-Right',
    'sources_by_bias': {'Center-Right': ['foxnews.com', ...], ...}
}
```

#### 2. Future Impact Analysis (`future_impact_analysis` action)

**Purpose:** Fetch articles with forward-looking predictions and impact timelines.

**Database Fields Used:**

* `future_signal` - Prediction type (e.g., "AI will accelerate", "Escalation into armed conflict")
* `time_to_impact` - Timeline (e.g., "Immediate (0-6 months)", "Mid-term (18-60 months)")
* `sentiment` - Article sentiment (stronger sentiments often correlate with stronger predictions)

**Facade Method:** `get_articles_with_future_signals(topic_name, limit, days_back)`

```python
# Filters for articles WHERE:
# - future_signal IS NOT NULL
# - future_signal != ''
# - future_signal != 'None'
# - publication_date >= start_date
# - topic = topic_name (if specified)
```

**Distribution Method:** `_get_future_signal_distribution(articles)`

Returns:

```python
{
    'future_signals': {
        'distribution': {'AI will accelerate': 234, ...},
        'top_signals': [('AI will accelerate', 234), ...],
        'total': 500
    },
    'time_to_impact': {
        'distribution': {'Short-term': 180, 'Immediate (0-6 months)': 150, ...},
        'percentages': {'Short-term': 36.0, ...}
    },
    'sentiment': {
        'distribution': {'Neutral': 300, 'Negative': 120, ...},
        'strong_sentiment_count': 185
    },
    'total_articles': 500
}
```

#### 3. Sentiment Analysis (`sentiment_analysis` action)

**Purpose:** Analyze sentiment distribution across articles.

**Database Fields Used:**

* `sentiment` - Article sentiment (Positive, Negative, Neutral, Critical, Hyperbolic)

**Distribution Method:** `_get_sentiment_distribution(db, topic, articles)`

#### 4. Vector Search (default)

**Purpose:** Semantic similarity search for general queries.

**When Used:** When no specialized action is defined, or for `vector_search` action.

**Limitation:** Clusters around semantically similar content, may not provide diverse samples.

### Cross-Topic Mode

When `topic` is `__all__` or `None`, the system operates in **cross-topic mode**:

```python
is_cross_topic = (topic == '__all__' or not topic)
effective_topic = None if is_cross_topic else topic
```

In cross-topic mode:

* No topic filter is applied to SQL queries
* Articles from all topics are included
* Distribution calculations span all topics

### Adding a New Filtering Strategy

#### Step 1: Add Database Facade Method

In `app/database_query_facade.py`:

```python
def get_articles_with_custom_field(self, topic_name=None, limit=500, days_back=30):
    """Fetch articles that have custom_field data populated.

    Args:
        topic_name: Optional topic filter. None for cross-topic.
        limit: Maximum articles to return.
        days_back: How many days back to search.

    Returns:
        List of article dicts with custom_field data.
    """
    from sqlalchemy import cast, Date
    import logging
    logger = logging.getLogger(__name__)

    start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')

    # Build WHERE conditions
    conditions = [
        articles.c.custom_field.isnot(None),
        articles.c.custom_field != ''
    ]

    if topic_name:
        conditions.append(articles.c.topic == topic_name)

    # Date filter
    coalesce_date = func.coalesce(articles.c.submission_date, articles.c.publication_date)
    conditions.append(cast(coalesce_date, Date) >= start_date)

    # Build query
    query = select(articles).where(
        and_(*conditions)
    ).order_by(
        desc(coalesce_date)
    ).limit(limit)

    result = self._execute_with_rollback(query).mappings().fetchall()
    return [dict(row) for row in result]
```

#### Step 2: Add Action Handler

In `app/services/tool_plugin_base.py`, add to the `execute()` method:

```python
elif action == 'custom_analysis' and db:
    try:
        fetch_limit = max(limit, 500)

        # Use facade method
        custom_articles = db.facade.get_articles_with_custom_field(
            topic_name=effective_topic,
            limit=fetch_limit,
            days_back=30
        )

        self.logger.info(f"Custom analysis: fetched {len(custom_articles)} articles")

        if custom_articles:
            articles = custom_articles[:limit]

            # Calculate distribution
            custom_data = self._get_custom_distribution(custom_articles)
            action_results['custom'] = custom_data
        else:
            action_results['custom'] = {'error': 'No articles with custom data'}

    except Exception as e:
        self.logger.error(f"Custom analysis failed: {e}")
        action_results['custom'] = {'error': str(e)}
```

#### Step 3: Add Distribution Method

In `app/services/tool_plugin_base.py`:

```python
def _get_custom_distribution(self, articles: List[Dict]) -> Dict:
    """Calculate custom field distribution from articles."""
    from collections import Counter

    values = Counter()
    for article in articles:
        value = article.get('custom_field', '')
        if value:
            values[value] += 1

    total = len(articles)
    return {
        'distribution': dict(values),
        'percentages': {k: round(v/total*100, 1) for k, v in values.items()},
        'total_articles': total,
        'dominant': values.most_common(1)[0][0] if values else 'Unknown'
    }
```

#### Step 4: Create Plugin Definition

Create `data/auspex/plugins/custom_analysis/tool.md`:

```yaml
---
name: "custom_analysis"
version: "1.0.0"
type: "tool"
category: "analysis"
description: "Analyze articles based on custom field"

parameters:
  - name: topic
    type: string
    required: true
  - name: limit
    type: integer
    default: 100

triggers:
  - patterns: ["custom", "specific keywords"]
    priority: high

actions:
  - custom_analysis

prompt: |
  Analyze {article_count} articles about "{topic}".

  CUSTOM DATA:
  {custom}

  ARTICLES:
  {articles}

  Provide analysis...
---
```

#### Step 5: Add Trigger Keywords

In `app/services/auspex_service.py`, add to `_should_use_tools()`:

```python
tool_keywords = [
    # ... existing keywords ...
    "custom", "specific", "keywords"  # Add your trigger words
]
```

### Available Article Fields

The `articles` table contains these fields that can be used for filtering:

| Field              | Type | Description            | Example Values                                         |
| ------------------ | ---- | ---------------------- | ------------------------------------------------------ |
| `bias`             | text | Political bias rating  | "right-center", "left", "least biased"                 |
| `bias_source`      | text | Source of bias rating  | "mediabiasfactcheck.com"                               |
| `sentiment`        | text | Article sentiment      | "Positive", "Negative", "Neutral", "Critical"          |
| `future_signal`    | text | Future prediction type | "AI will accelerate", "Escalation into armed conflict" |
| `time_to_impact`   | text | Impact timeline        | "Immediate (0-6 months)", "Mid-term (18-60 months)"    |
| `category`         | text | Article category       | "Technology", "Politics"                               |
| `topic`            | text | Topic name             | "AI", "Geopolitics"                                    |
| `news_source`      | text | Source domain          | "reuters.com", "bbc.com"                               |
| `publication_date` | date | Publication date       | "2025-01-15"                                           |

Query current field distributions:

```sql
SELECT field_name, COUNT(*)
FROM articles
WHERE field_name IS NOT NULL AND field_name != ''
GROUP BY field_name
ORDER BY COUNT(*) DESC;
```

### Best Practices

1. **Always filter for non-null values** - Many articles don't have all fields populated
2. **Use the facade pattern** - Don't write raw SQL in handlers; add methods to `DatabaseQueryFacade`
3. **Provide fallbacks** - If specialized query returns no results, fall back gracefully
4. **Log fetched counts** - Helps debug when results seem wrong
5. **Normalize values** - Raw data often has inconsistent formatting
6. **Include distribution in prompt** - Give the LLM statistical context alongside articles
7. **Test with cross-topic mode** - Ensure `topic=None` works correctly

### Debugging

Check logs for:

```
Bias analysis: fetched 500 articles with bias data
Future impact analysis: fetched 500 articles with future signals
```

If you see low counts or errors, check:

1. Database has articles with the required fields populated
2. Date range isn't too restrictive
3. Topic filter isn't excluding all results
