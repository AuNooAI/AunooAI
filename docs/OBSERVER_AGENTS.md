# Observer Agents: Automated Intelligence Monitoring

## What They Are

Observer Agents are custom, analyst-defined monitoring rules that continuously scan incoming articles for specific threats, opportunities, or developments. Where traditional keyword monitoring answers "collect articles about X", Observer Agents answer "tell me when something *specific* is happening within X" — turning analyst intuition into automated, repeatable detection.

## How They Work

An analyst writes a natural-language instruction describing what to watch for. The system then:

1. **Searches** the article corpus using semantic similarity, keyword matching, or date-range filtering
2. **Evaluates** each article against the instruction using a language model
3. **Flags** matching articles with a confidence score, threat level, and detailed reasoning
4. **Alerts** the analyst via email, Bluesky DM, or in-platform notifications
5. **Reports** (optionally) by generating a structured intelligence briefing from all matches

## Key Features

### Natural-Language Instructions

No query syntax to learn. Analysts describe what they're looking for in plain language:

- *"Flag any indication that Country X is preparing economic sanctions against Country Y, including diplomatic rhetoric, trade data anomalies, or leaked policy documents"*
- *"Monitor for paper mill activity targeting journals in our portfolio, including coordinated submission patterns, citation rings, or guest editor collusion"*
- *"Watch for biosimilar approvals or patent challenges that could affect top-20 revenue-generating compounds"*

### Entity Monitoring

Named entities (companies, people, organisations, products) can be attached to any instruction. Articles mentioning monitored entities are evaluated with higher priority and flagged with greater confidence.

### Per-Article Reasoning

Every flagged article includes:

| Field | Description |
|-------|-------------|
| **Confidence score** (0–1.0) | How certain the match is |
| **Threat level** (low / medium / high) | Severity assessment |
| **Reasoning** | Detailed explanation of *why* this article matched, citing specific content |
| **Recommended action** | What the analyst should do next |

This is not a keyword hit list. The language model reads each article and makes a judgment call, explaining its reasoning in terms the analyst can verify or challenge.

### Flexible Scheduling

Agents run on configurable schedules:

- **Interval-based**: every 30 minutes, every 4 hours, every 2 days
- **Daily at a fixed time**: 9:00 AM briefing, 6:00 PM end-of-day scan
- **On-demand**: manual trigger for ad-hoc investigations

### Search Strategies

Three approaches for finding relevant articles:

- **Recent**: Date-range scan of the last N days (fast, broad coverage)
- **Semantic**: Vector similarity search using the instruction text and entities (finds conceptually related articles even without keyword overlap)
- **Chunked**: Batch processing for large-scale analysis (50 articles per LLM evaluation)

### Automated Reporting

When matches are found, agents can auto-generate a markdown intelligence report synthesising all flagged articles into key findings, common themes, urgency assessment, and recommended actions. Reports are stored, versioned, and exportable.

### Multi-Channel Notifications

Configurable alert thresholds (e.g., "only notify if 3+ matches") with delivery via:

- **Email** — full alert details with optional report attachment
- **Bluesky direct message** — brief summary with match count and threat levels

### Article Tagging

Matched articles are automatically tagged with `SIGNAL_{AgentName}`, making them filterable across the platform. Optionally, matched articles can be starred for quick analyst access.

---

## Benefits

### From Reactive to Proactive Monitoring

Traditional intelligence workflows rely on analysts periodically reviewing article feeds and spotting relevant developments. Observer Agents invert this: the analyst defines what matters once, and the system watches continuously. Nothing falls through the cracks because the analyst was on leave, focused on a different topic, or overwhelmed by volume.

### Captures What Keyword Monitoring Misses

A keyword search for "patent cliff" will find articles that use those exact words. An Observer Agent instructed to *"watch for any pharmaceutical company losing market exclusivity on a blockbuster drug"* will also catch articles about generic entry, biosimilar approvals, Paragraph IV certifications, and court rulings — even if they never use the phrase "patent cliff". The language model understands intent, not just terminology.

### Scales Analyst Expertise Across the Organisation

A senior geopolitical analyst's ability to recognise early escalation signals can be encoded as an Observer Agent instruction and run 24/7 against every incoming article. This doesn't replace the analyst — it gives them a first pass at scale, letting them focus on the articles the agent flagged rather than reviewing hundreds manually.

### Explainable, Auditable Detection

Every alert includes the model's reasoning and the specific article content that triggered it. Analysts can assess whether the reasoning is sound, adjust the instruction if it's too broad or narrow, and track false positive rates over time. The confidence score provides a natural triage mechanism — high-confidence alerts get immediate attention, lower-confidence ones queue for batch review.

### Composable Monitoring Architecture

Multiple agents can monitor the same article corpus from different angles. A single "AI and Machine Learning" topic might have separate agents watching for regulatory developments, competitive product launches, safety incidents, and workforce displacement signals — each with its own instruction, threshold, and notification channel. Agents can be enabled, disabled, cloned, and modified independently.

### Continuous Learning Loop

As analysts review flagged articles and acknowledge or dismiss alerts, they develop intuition about what instructions work well and which need refinement. The instruction text can be updated at any time without losing execution history, creating an iterative improvement cycle between human judgment and automated detection.

---

## Example Use Cases

| Use Case | Instruction Summary | Schedule | Alert Channel |
|----------|-------------------|----------|---------------|
| **Sanctions early warning** | Monitor diplomatic rhetoric and trade policy shifts between specified countries | Every 4 hours | Email |
| **Research integrity** | Flag coordinated submission patterns, citation rings, or retraction activity across monitored publishers | Daily at 9 AM | Email + Bluesky |
| **Patent expiry tracking** | Watch for biosimilar approvals, generic entry, or court rulings affecting top-20 revenue compounds | Every 12 hours | Email with report |
| **Competitor intelligence** | Track product launches, M&A activity, leadership changes, and strategic partnerships for named competitors | Every 6 hours | Email |
| **Brand reputation** | Monitor for adverse media, PR crises, customer complaints, or regulatory actions mentioning the organisation | Every 2 hours | Email + Bluesky |
| **Emerging technology signals** | Identify breakthroughs, funding announcements, or policy shifts that could reshape a specific technology domain | Daily at 6 PM | Report only |

---

## Configuration Reference

### Instruction Fields

| Field | Description |
|-------|-------------|
| **Name** | Unique identifier for the agent |
| **Description** | What this agent watches for (displayed in UI) |
| **Instruction** | Natural-language detection criteria sent to the LLM |
| **Topic** | Optional — scopes the agent to a specific monitoring topic |
| **Entities to monitor** | Named entities (companies, people, brands) to prioritise |
| **Model** | LLM used for evaluation (e.g., gpt-4o-mini, claude-opus-4) |

### Search Parameters

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| **Search strategy** | recent | recent / semantic / chunked | How articles are found |
| **Days back** | 7 | 1–30 | Lookback window for article search |
| **Max articles** | 100 | 10–500 | Maximum articles evaluated per run |

### Schedule Options

| Type | Configuration | Example |
|------|--------------|---------|
| **Interval** | Every N minutes / hours / days | Every 4 hours |
| **Daily** | Fixed time (HH:MM) | Daily at 09:00 |
| **Manual** | On-demand trigger | Run now |

### Notification Options

| Channel | Configuration |
|---------|--------------|
| **Email** | Recipient address + alert threshold |
| **Bluesky DM** | Recipient handle + alert threshold |
| **Report** | Auto-generate markdown report from matches |
| **Article tagging** | Tag matched articles with `SIGNAL_{AgentName}` |
| **Star articles** | Mark matched articles for quick access |
