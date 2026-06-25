# Technical Problem: LLM Knowledge Cutoff in News Analysis

## The Problem

When Auspex analyzes current news articles, the LLM's training data creates factual conflicts:

| Article Says | LLM Training Says | LLM Output |
|--------------|-------------------|------------|
| "Trump threatened to invoke Insurrection Act" (Jan 2026) | Trump left office Jan 2021 | "**former** President Trump..." |
| "Governor Walz mobilized National Guard" | Walz is governor (correct) | Correct |
| "Pentagon preparing 1,500 soldiers" | Generic military knowledge | Lacks context of ongoing ICE protests |

**Core issue**: The LLM has no awareness of events between its training cutoff and the article date. It can read the article text but lacks the surrounding context that makes events meaningful.

**Symptoms**:
- Incorrect titles ("former president" when they're current)
- Missing connections to related events
- Failure to understand significance (why is this escalating?)
- Analysis treats each article as isolated rather than part of ongoing narrative

---

## Approach 1: Prompt Engineering

**What it is**: Instructions telling the LLM to override its training data and trust article content.

**Example**:
```
YOUR TRAINING DATA IS OUTDATED. If articles describe someone
taking presidential action, they ARE the current president.
NEVER say "former president" for anyone actively holding office.
```

### Pros

- **Fast to implement** - Just update prompt text
- **No infrastructure changes** - No new API calls, database queries, or services
- **Zero latency impact** - No additional processing
- **Works sometimes** - Strong models (GPT-4, Claude) can follow these instructions ~70-80% of the time

### Cons

- **Unreliable** - LLM training data is deeply embedded; instructions compete with learned patterns
- **Whack-a-mole** - Fix "former president" and "former Prime Minister" appears next
- **No actual knowledge** - LLM still doesn't know *why* Trump is president or what led to current events
- **Context blindness persists** - Can't connect article to broader events it doesn't know about
- **Model-dependent** - Smaller/cheaper models follow instructions less reliably
- **Fails silently** - No way to detect when the LLM ignores instructions

**Verdict**: Band-aid. Reduces visible errors but doesn't solve the knowledge gap.

---

## Approach 2: Context Engineering

**What it is**: Inject actual information into the LLM context so it has real knowledge, not just instructions to pretend.

### Option 2A: Related Article Injection

When analyzing an article, automatically retrieve 3-5 related recent articles to establish context.

```python
# When user asks about Minnesota deployment article
related = vector_search("ICE protests Minnesota Trump Insurrection Act", limit=5, days=30)
# Inject summaries of related articles before the target article
```

**Pros**:
- LLM sees actual coverage establishing current reality
- Connections to related events emerge naturally
- Uses existing infrastructure (vector search)
- Self-updating as new articles arrive

**Cons**:
- Increases token usage (5 articles x ~500 tokens = 2,500 extra tokens)
- May retrieve irrelevant articles
- Doesn't help for truly novel topics with no prior coverage
- Adds latency (vector search + retrieval)

---

### Option 2B: Dynamic "State of the World" Summary

Maintain a regularly-updated summary of current reality:
- Who holds major offices (President, key governors, world leaders)
- Ongoing major events (conflicts, protests, elections)
- Recent significant developments

```python
CURRENT_CONTEXT = """
As of January 2026:
- US President: Donald Trump (inaugurated January 2025, second term)
- Ongoing: ICE enforcement operations causing protests in multiple states
- Recent: Fatal shooting of ICE agent Renee Good has escalated tensions
- Minnesota Governor Tim Walz has activated National Guard
"""
```

**Pros**:
- Compact (500-1000 tokens covers essentials)
- Directly addresses the "who's in office" problem
- Consistent across all queries
- Can be curated for accuracy

**Cons**:
- Requires maintenance (manual or automated updates)
- May become stale between updates
- Doesn't scale to all topics (can't summarize everything)
- Risk of bias in what's included

---

### Option 2C: Automatic Context Extraction

Before analyzing any article, run a pre-processing step:
1. Extract key entities (people, organizations, events)
2. Query database for recent articles about those entities
3. Build a mini-briefing about each entity's current status

```python
entities = extract_entities(article)  # ["Trump", "Minnesota", "ICE", "National Guard"]
for entity in entities:
    recent = get_recent_coverage(entity, days=14)
    context += summarize_entity_status(entity, recent)
```

**Pros**:
- Targeted to the specific article being analyzed
- Automatically adapts to any topic
- Leverages existing article database
- No manual maintenance

**Cons**:
- Most complex to implement
- Multiple LLM calls (entity extraction + summarization)
- Highest latency
- Dependent on having relevant prior coverage

---

### Option 2D: Hybrid - Persistent Entity Registry

Maintain a database table of key entities with current status, updated whenever articles are ingested:

```sql
CREATE TABLE entity_status (
    entity_name TEXT PRIMARY KEY,
    entity_type TEXT,  -- 'person', 'organization', 'event'
    current_status TEXT,  -- 'President of USA', 'Governor of Minnesota'
    last_updated TIMESTAMP,
    source_articles JSONB
);
```

When analyzing articles, look up mentioned entities and inject their current status.

**Pros**:
- Fast lookup (database query vs LLM call)
- Accurate (derived from actual articles)
- Automatically maintained during ingestion
- Compact context injection

**Cons**:
- Requires entity extraction during ingestion
- New database table and maintenance logic
- May have gaps for rarely-mentioned entities
- Initial backfill needed

---

## Recommendation

**Short-term**: Option 2A (Related Article Injection)
- Leverages existing vector search
- Provides real context without new infrastructure
- Can implement in hours

**Medium-term**: Option 2D (Entity Registry)
- Solves the "who's in office" problem definitively
- Low latency once built
- Accurate and self-maintaining

**Avoid**: Pure prompt engineering as a solution. Use it only as a supplement to context engineering.

---

## Implementation Complexity

| Approach | Dev Time | Latency Impact | Token Cost | Reliability |
|----------|----------|----------------|------------|-------------|
| Prompt Engineering | 30 min | None | None | Low (70%) |
| 2A: Related Articles | 2-4 hrs | +500ms | +2500 tokens | Medium (85%) |
| 2B: Static Summary | 1-2 hrs | None | +500 tokens | Medium (80%) |
| 2C: Auto Extraction | 1-2 days | +2-3s | +4000 tokens | High (90%) |
| 2D: Entity Registry | 2-3 days | +50ms | +300 tokens | High (95%) |
