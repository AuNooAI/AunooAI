# Getting Started with Explore View

## Overview

**Explore View** is your central hub for threat intelligence research and analysis. This unified workspace brings together three powerful tools—**Article Investigator**, **Narrative Explorer**, and **Six Articles**—each designed for a specific stage of your intelligence workflow.

Whether you're conducting daily briefings, investigating specific threats, or identifying long-term patterns, Explore View provides the right tool for the job.

## The Three Pillars of Explore View

### 1. Article Investigator
**Best for**: Hands-on research and detailed article review

Your primary workspace for exploring, filtering, and managing individual threat intelligence articles. Perfect for:
- Daily threat intelligence monitoring
- Incident response research
- Finding specific articles or sources
- Exporting raw intelligence data

[→ Read the full Article Investigator guide](getting-started-article-investigator.md)

### 2. Narrative Explorer
**Best for**: Understanding themes, patterns, and connections

AI-powered analysis that reveals the story behind the news. Identifies emerging narratives, thematic clusters, and strategic insights across multiple articles. Perfect for:
- Trend analysis and pattern recognition
- Threat hunting across APT campaigns
- Strategic planning and forecasting
- Identifying research gaps

[→ Read the full Narrative Explorer guide](getting-started-narrative-view.md)

### 3. Six Articles
**Best for**: Executive briefings and strategic communication

Curated executive briefing tool that selects and analyzes the most strategically relevant articles. Delivers actionable intelligence in 8-12 minutes. Perfect for:
- Daily executive briefings
- C-suite and board presentations
- Crisis monitoring and rapid assessment
- Weekly strategic digests

[→ Read the full Six Articles guide](getting-started-six-articles.md)

## Quick Start: Which Tool Should I Use?

### Choose by Your Goal

| Your Goal | Use This Tool | Why |
|-----------|---------------|-----|
| "What happened today?" | **Article Investigator** | Browse all articles, hide irrelevant ones, bookmark important findings |
| "What are the important stories?" | **Six Articles** | AI selects and analyzes the top 6 most relevant articles for your role |
| "What's the bigger picture?" | **Narrative Explorer** | Reveals themes, patterns, and connections across many articles |
| "I need to find something specific" | **Article Investigator** | Advanced filtering by topic, source, entity, date |
| "I need to brief executives" | **Six Articles** | Persona-specific insights with executive actions and strategic relevance |
| "I'm threat hunting" | **Narrative Explorer** | Cross-article pattern recognition and thematic clustering |

### Choose by Your Audience

| Your Audience | Recommended Tool | Output Format |
|---------------|------------------|---------------|
| **Yourself** (research) | Article Investigator | Multiple view modes, filtering |
| **Your team** (collaboration) | Narrative Explorer | Thematic insights with research suggestions |
| **Your manager** (weekly update) | Six Articles | Strategic analysis with executive takeaways |
| **C-suite/Board** (strategic briefing) | Six Articles | CEO/CISO persona analysis, PDF export |
| **Security operations** (tactical) | Article Investigator | CSV export, detailed article data |
| **Threat intelligence analysts** (strategic) | Narrative Explorer | Pattern analysis, emerging threats |

### Choose by Time Available

| Time Available | Recommended Workflow |
|----------------|----------------------|
| **5 minutes** | Six Articles → Scan Executive Takeaways only |
| **15 minutes** | Six Articles → Read full analysis of 6 curated articles |
| **30 minutes** | Article Investigator → Filter and review in Card View, export findings |
| **1 hour** | Narrative Explorer → Generate insights, explore themes, click through to articles |
| **Deep dive** | Article Investigator + Narrative Explorer + Six Articles Deep Dive tools |

## Common Workflows

### Morning Intelligence Briefing (15 minutes)

1. **Article Investigator** (5 min)
   - Set date range: "Last 24 hours"
   - Quick scan in Table View
   - Hide obvious noise

2. **Six Articles** (10 min)
   - Generate briefing for your persona
   - Read Executive Takeaways and Strategic Relevance
   - Export as PDF for team

**Result**: You're current on overnight developments with actionable insights.

---

### Weekly Strategic Analysis (1 hour)

1. **Article Investigator** (15 min)
   - Set date range: "Last 7 days"
   - Filter to 3-5 key topics
   - Bookmark critical articles

2. **Narrative Explorer** (30 min)
   - Generate narrative insights for the week
   - Identify emerging patterns and themes
   - Note research suggestions

3. **Six Articles** (15 min)
   - Generate weekly digest (7-8 articles)
   - Use Deep Dive on 1-2 critical articles
   - Export Enhanced HTML for team distribution

**Result**: Comprehensive understanding of the week's threat landscape with strategic context.

---

### Incident Response Research (30-60 minutes)

1. **Article Investigator** (15 min)
   - Filter by specific entity (threat actor, malware, CVE)
   - Expand date range for historical context
   - Switch to HUD View for side-by-side reading
   - Export findings as CSV

2. **Narrative Explorer** (20 min)
   - Generate insights for related topics
   - Identify connected incidents or campaigns
   - Review thematic patterns

3. **Six Articles Deep Dive** (15 min)
   - Use Deep Dive tool on key articles
   - Generate Impact Timeline
   - Ask Auspex specific questions

**Result**: Comprehensive incident context with historical patterns and strategic implications.

---

### Executive Board Preparation (2 hours)

1. **Article Investigator** (30 min)
   - Set date range: "Last 30 days"
   - Select high-level strategic topics
   - Review in Reader View for full context
   - Mark critical developments

2. **Narrative Explorer** (45 min)
   - Generate insights for board-relevant topics
   - Identify long-term trends and shifts
   - Document emerging risks and opportunities

3. **Six Articles** (45 min)
   - Generate with CEO persona
   - Use Scenario Planning tools
   - Export as professional PDF
   - Generate Podcast version for board preview

**Result**: Board-ready intelligence brief with strategic insights and talking points.

---

### Threat Hunting Campaign (Ongoing)

1. **Narrative Explorer** (Initial: 1 hour)
   - Wide date range (30-90 days)
   - Multiple related topics
   - Identify suspicious patterns and anomalies
   - Note entities and themes for investigation

2. **Article Investigator** (Ongoing)
   - Filter by entities identified in Narrative Explorer
   - Track specific indicators over time
   - Export findings for documentation

3. **Six Articles** (Weekly check-in)
   - Generate with CISO persona
   - Review for any new related developments
   - Use Deep Dive on relevant articles

**Result**: Systematic threat hunting with pattern recognition and ongoing monitoring.

## Understanding the Workflow

### The Intelligence Cycle with Explore View

```
┌─────────────────────────────────────────────────────────────┐
│                     Collection & Loading                     │
│              (Automatic: Articles load in background)        │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Processing & Filtering                    │
│                  → Article Investigator ←                    │
│          Browse, filter, hide noise, bookmark critical       │
└───────────────────────────┬─────────────────────────────────┘
                            │
                ┌───────────┴───────────┐
                │                       │
                ▼                       ▼
┌───────────────────────┐   ┌───────────────────────┐
│   Analysis (Broad)    │   │ Analysis (Focused)    │
│ → Narrative Explorer ← │   │   → Six Articles ←    │
│  Patterns & Themes    │   │  Curated Insights     │
└───────────┬───────────┘   └───────────┬───────────┘
            │                           │
            └───────────┬───────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                 Dissemination & Action                       │
│         Export → Share → Brief → Investigate → Act          │
└─────────────────────────────────────────────────────────────┘
```

### Typical Daily Flow

**Morning (15 min)**
1. Article Investigator → Quick scan, hide noise
2. Six Articles → Generate daily brief
3. Export & share with team

**Midday (30 min)**
- Follow up on flagged items from morning
- Use Deep Dive tools for critical articles
- Update incident trackers

**Afternoon (Optional: 30 min)**
- Narrative Explorer → Weekly pattern check
- Article Investigator → Deep research on specific topics
- Prepare briefing materials for leadership

**Weekly (1 hour)**
- Narrative Explorer → Generate weekly insights
- Six Articles → Create weekly digest
- Archive and distribute findings

## Key Features Across All Tools

### Shared Filters
All three tools use the same top-level filters:
- **Topics**: Select threat intelligence categories
- **Date Range**: Choose your time window
- **Sources**: Filter by publisher (optional)

Change these filters once, and they apply across all tools.

### Cross-Tool Navigation
- Click article titles to open full article view
- Bookmark articles in Article Investigator, reference in other tools
- Export from any tool maintains links back to source articles

### Export Options
Each tool offers appropriate export formats:
- **Article Investigator**: CSV, PDF, Markdown (raw data)
- **Narrative Explorer**: Markdown, HTML (insights and themes)
- **Six Articles**: Markdown, HTML, PDF, Podcast (executive briefing)

## Tips for Maximum Efficiency

### Start Broad, Then Focus
1. Begin in **Article Investigator** to see everything
2. Hide noise and identify areas of interest
3. Use **Narrative Explorer** to understand patterns
4. Use **Six Articles** to brief others on key findings

### Use Tools in Combination
- **Article Investigator + Six Articles**: Browse all → Export best 6
- **Narrative Explorer + Article Investigator**: Find patterns → Investigate specific articles
- **Six Articles + Deep Dive Tools**: Executive brief → Detailed analysis on demand

### Establish Daily Routines
- **Same time each day**: Consistency builds habit
- **Same tool sequence**: Article Investigator → Six Articles → Narrative Explorer (weekly)
- **Same export format**: Standardize for your team/leadership

### Leverage Personas
- Use **CISO** persona for security team briefings
- Use **CEO** persona for board presentations
- Use **CTO** persona for engineering leadership
- Compare personas to see different strategic angles

### Keyboard & Navigation
- Use **Table View** in Article Investigator for speed
- Use **Reader View** for focused reading
- Use **Podcast mode** in Six Articles for commutes
- Bookmark your browser page with preferred filters

## Troubleshooting

### "I don't see any articles"
- Check your date range (expand to last 7 days)
- Verify at least one topic is selected
- Click "Refresh" or "Load Articles"
- Check internet connection

### "Results aren't relevant"
- **Article Investigator**: Apply more specific topic filters
- **Narrative Explorer**: Narrow to 3-5 focused topics
- **Six Articles**: Switch to a more specific persona (CISO vs CEO)

### "It's taking too long"
- **Article Investigator**: Use pagination instead of "Show All"
- **Narrative Explorer**: Reduce date range (30 days → 7 days)
- **Six Articles**: Reduce article count (6 → 4)

### "I'm overwhelmed by information"
1. Start with **Six Articles** (6 curated articles only)
2. Read just the Executive Takeaways
3. Deep dive on 1-2 critical items
4. Come back to Article Investigator only if needed

## Best Practices

### For Threat Intelligence Teams
- **Daily**: Article Investigator + Six Articles
- **Weekly**: Narrative Explorer for pattern analysis
- **Archive**: Export all three formats for organizational memory
- **Collaborate**: Share findings across tools for team discussion

### For Security Leadership
- **Daily**: Six Articles with CISO persona (10 min)
- **Weekly**: Narrative Explorer review (30 min)
- **Monthly**: Article Investigator deep dive on key threats (1 hour)
- **Board prep**: Six Articles with CEO persona + exports

### For Solo Analysts
- **Morning**: Six Articles scan (5 min)
- **Research**: Article Investigator with filters (ongoing)
- **Pattern hunting**: Narrative Explorer weekly
- **Documentation**: Export findings from appropriate tool

### For Large Teams
- **Divide responsibilities**: Assign team members to specific topics
- **Share workflows**: One analyst runs Narrative Explorer, others investigate findings
- **Standardize exports**: Agree on format (PDF for exec, Markdown for Slack)
- **Review meetings**: Use Six Articles as agenda, Narrative Explorer for context

## Getting Help

### Learn More
- [Article Investigator Guide](getting-started-article-investigator.md) - Detailed research and filtering
- [Narrative Explorer Guide](getting-started-narrative-view.md) - Pattern analysis and themes
- [Six Articles Guide](getting-started-six-articles.md) - Executive briefings

### Support
For additional support or to report issues, contact your Aunoo AI administrator or visit the support documentation.

---

*Last updated: 2025-11-25*
