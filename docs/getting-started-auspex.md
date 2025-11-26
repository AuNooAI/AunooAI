# Auspex AI Assistant

## Overview

**Auspex** is an AI-powered research assistant that helps you analyze news, identify trends, and generate insights from your curated article database. It combines semantic search, sentiment analysis, and specialized analysis tools to provide deep, evidence-based intelligence.

**Location**: Click the robot icon (floating button) on any page

---

## Why Use It?

- **Intelligent Research**: Ask natural language questions about your data
- **Multi-Source Analysis**: Combines vector search, database queries, and external sources
- **Specialized Tools**: One-click access to newsletters, sentiment analysis, partisan breakdowns
- **Citation-Rich Output**: Every insight links back to source articles
- **Organizational Context**: Tailor analysis to your organization's perspective

---

## How It Works

Auspex uses a sophisticated pipeline:

1. **Query Understanding**: Interprets your question and selects appropriate tools
2. **Data Retrieval**: Searches your article database using semantic similarity
3. **Analysis**: Applies AI models to synthesize findings
4. **Structured Output**: Returns well-organized analysis with citations

---

## Quick Start

### Step 1: Open Auspex

1. Click the **robot icon** (bottom-right floating button)
2. Chat modal opens with topic and model selectors

### Step 2: Configure Your Session

- **Topic**: Select which topic to analyze (e.g., "AI", "Cybersecurity")
- **Model**: Choose AI model (GPT-4.1, GPT-4o, etc.)
- **Sample Size**: Auto, Balanced, Comprehensive, or Custom article limit

### Step 3: Ask Questions

Type natural language questions:
- "What are the main AI trends this week?"
- "How is ransomware coverage changing?"
- "What's the sentiment around quantum computing?"

### Step 4: Use Analysis Tools

Click the colored badges for specialized analysis:
- **Newsletter Generator** - Weekly digest with curated sections
- **Sentiment Analysis** - Sentiment distribution breakdown
- **Partisan Analysis** - Political bias comparison
- **Future Impact** - Predictions and risk assessment

---

## Understanding the Interface

### Header Controls

| Control | Description |
|---------|-------------|
| **Topic Selector** | Choose which topic's articles to analyze |
| **Model Selector** | Select AI model (affects quality and speed) |
| **Sample Size** | Control how many articles to include |
| **Custom Limit** | Set exact article count (10-500) |
| **New Chat** | Start fresh conversation |
| **Export** | Download conversation |
| **Tools Config** | Enable/disable specific tools |
| **Fullscreen** | Expand to full window |

### Chat History

- **Sidebar Toggle**: Click chevron to show/hide past conversations
- **Session List**: Previous chats organized by date
- **Resume**: Click any session to continue where you left off

### Analysis Tools (Badges)

Colored badges appear below the chat input:

| Badge | Triggers | Output |
|-------|----------|--------|
| **Newsletter Generator** | "newsletter", "weekly roundup" | Formatted newsletter with sections |
| **Sentiment Analysis** | "sentiment", "positive/negative" | Sentiment distribution with charts |
| **Partisan Analysis** | "bias", "political", "left/right" | Political framing comparison |
| **Future Impact** | "future", "prediction", "forecast" | Predictions and risk assessment |
| **External Research** | "external research", "web search" | Combined web + database analysis |

---

## Plugin Tools

### Newsletter Generator

**Triggers**: "newsletter", "weekly newsletter", "news roundup"

**Output Sections**:
- **The News**: 6-15 headlines grouped by theme
- **The Deep Dive**: In-depth analysis of top story
- **Weird Sh*t of the Week**: Unusual or ironic developments
- **Must Reads**: 8-12 curated articles with links
- **Market Updates**: M&A, releases, partnerships

**Best For**: Weekly briefings, stakeholder updates, executive summaries

---

### Sentiment Analysis

**Triggers**: "sentiment", "how is X being perceived", "positive/negative coverage"

**Output Sections**:
- **Overall Distribution**: Percentage breakdown (Positive/Neutral/Negative)
- **Sentiment by Source**: Which outlets lean positive/negative
- **Key Themes**: What's driving each sentiment category
- **Sentiment Drivers**: Events and factors influencing tone
- **Notable Quotes**: Representative perspectives

**Best For**: Brand monitoring, crisis assessment, public perception tracking

---

### Partisan Analysis

**Triggers**: "bias", "partisan", "political framing", "left vs right"

**Output Sections**:
- **Source Bias Distribution Table**: Count and percentage by political leaning
- **Comparative Framing Table**: Side-by-side view of narratives
- **Sample Articles Table**: Right Wing | Center | Left Wing comparison
- **Key Divergence Points**: Where coverage differs most
- **Recommendations**: Most balanced sources

**Best For**: Media bias research, balanced coverage assessment, political analysis

---

### Future Impact Analysis

**Triggers**: "future", "prediction", "forecast", "what will happen"

**Output Sections**:
- **Key Predictions**: 3-5 specific predictions with confidence levels
- **Emerging Opportunities**: Potential benefits and beneficiaries
- **Potential Risks**: Challenges and mitigation strategies
- **Signals to Watch**: Early indicators to monitor
- **Confidence Assessment**: Data quality and consensus evaluation

**Best For**: Strategic planning, risk assessment, opportunity identification

---

### External Research

**Triggers**: "external research", "web search", "outside sources"

**Requires**: Google API key configured in Settings

**Output Sections**:
- **External Sources Summary**: Key findings from web search
- **Internal Database Context**: How internal data aligns/differs
- **Synthesis & Analysis**: Combined insights
- **Key Takeaways**: Actionable findings

**Best For**: Gap analysis, verification, comprehensive research

---

## Deep Research Mode

Deep Research is an advanced autonomous research system that conducts comprehensive, multi-stage investigations. Unlike standard chat or plugin tools, Deep Research runs a full research workflow with progress tracking.

### How to Activate

1. Look for the **Deep Research** selector in the Auspex header
2. Choose a research mode:
   - **Off**: Standard chat mode (default)
   - **Internal**: Research using only your internal database
   - **Hybrid**: Combine internal database + external web sources
   - **External**: Research using external web sources only

3. When Deep Research is active:
   - The send button changes to "Start Deep Research"
   - Your query triggers the full 4-stage workflow

### The 4-Stage Workflow

Deep Research executes these stages automatically:

#### Stage 1: Planning (10% of process)
- Analyzes your research question
- Creates research objectives
- Develops search strategy
- Outlines report structure

#### Stage 2: Searching (40% of process)
- Executes multiple search queries
- Applies diversity filtering (avoids duplicate sources)
- Filters for credibility
- Tracks internal vs. external sources

#### Stage 3: Synthesis (30% of process)
- Analyzes all findings
- Resolves contradictions between sources
- Assesses confidence levels
- Groups related insights

#### Stage 4: Writing (20% of process)
- Produces professional research report
- Includes citations for all claims
- Adds credibility assessment
- Formats with clear sections

### Progress Tracking

During Deep Research, you'll see:
- **Stage indicator**: Which stage is currently running
- **Progress bar**: Overall completion percentage
- **Live updates**: Real-time status messages
- **Source count**: Internal vs. external sources used

### Output Format

Deep Research produces a comprehensive report with:

- **Executive Summary**: Key findings at a glance
- **Research Objectives**: What was investigated
- **Detailed Findings**: Section-by-section analysis
- **Source Analysis**: Credibility and diversity assessment
- **Confidence Assessment**: How reliable the conclusions are
- **Full Citations**: Every claim linked to sources

### When to Use Deep Research

| Use Deep Research When | Use Standard Chat When |
|------------------------|------------------------|
| Complex, multi-faceted questions | Simple, direct questions |
| Need comprehensive coverage | Need quick answers |
| Preparing formal reports | Casual exploration |
| Require credibility assessment | Trust your sources |
| Time is not critical | Need immediate response |

### Deep Research Tips

- **Be specific**: "Analyze the impact of AI regulation on European startups in 2024" > "AI regulation"
- **Allow time**: Deep Research takes 2-5 minutes depending on complexity
- **Use Hybrid mode**: Combines the best of internal curation + external breadth
- **Check source balance**: Review internal vs. external source counts

---

## Use Cases

### Daily Intelligence Briefing

**Scenario**: You need a quick overview of overnight developments.

**Workflow**:
1. Open Auspex, select your topic
2. Ask: "What happened in [topic] in the last 24 hours?"
3. Review key developments with citations
4. Click relevant articles to investigate further

**Result**: 5-minute briefing with source links

---

### Weekly Newsletter Generation

**Scenario**: Creating a weekly digest for stakeholders.

**Workflow**:
1. Open Auspex, select topic
2. Click **Newsletter Generator** badge
3. Review generated newsletter sections
4. Export or copy for distribution

**Result**: Professional newsletter in under 2 minutes

---

### Media Bias Assessment

**Scenario**: Understanding how different outlets cover a topic.

**Workflow**:
1. Open Auspex, select topic
2. Click **Partisan Analysis** badge
3. Review bias distribution table
4. Compare sample articles across political spectrum
5. Identify most balanced sources

**Result**: Evidence-based media bias report with specific examples

---

### Trend Identification

**Scenario**: Spotting emerging patterns in coverage.

**Workflow**:
1. Open Auspex, select topic
2. Ask: "What trends are emerging in [topic]?"
3. Use **Future Impact** tool for predictions
4. Review sentiment changes over time

**Result**: Early warning on emerging trends with supporting evidence

---

### Competitive Intelligence

**Scenario**: Tracking coverage of specific companies or products.

**Workflow**:
1. Open Auspex, select relevant topic
2. Ask: "What's being said about [Company X]?"
3. Review sentiment and key themes
4. Compare with competitor coverage

**Result**: Competitive landscape analysis with citations

---

### Comprehensive Research Report

**Scenario**: Preparing a formal research brief on a complex topic requiring credibility assessment.

**Workflow**:
1. Open Auspex, select topic
2. Set Deep Research mode to **Hybrid** (internal + external)
3. Enter detailed research question: "Analyze the regulatory landscape for AI in healthcare, including recent legislation, compliance requirements, and industry response"
4. Watch progress through 4 stages (Planning → Searching → Synthesis → Writing)
5. Review comprehensive report with credibility assessment

**Result**: Professional research report with executive summary, detailed findings, and full citations (2-5 minutes)

---

## Tips & Best Practices

### Query Formulation

- **Be Specific**: "AI regulation in Europe last 7 days" > "AI news"
- **Include Timeframes**: "this week", "past month", "recent"
- **Name Entities**: Mention specific companies, people, countries
- **State Your Goal**: "for executive briefing" or "for risk assessment"

### Tool Selection

- **Newsletters**: For regular stakeholder updates
- **Sentiment**: When you need to gauge perception
- **Partisan**: When political framing matters
- **Future Impact**: For strategic planning
- **External Research**: When internal data may have gaps

### Maximizing Quality

- **Larger Sample Size**: More articles = more comprehensive analysis
- **Better Models**: GPT-4.1 > GPT-4o-mini for complex analysis
- **Organizational Profile**: Set up your profile for contextualized insights
- **Follow-Up Questions**: Drill down on interesting findings

### Citation Verification

- All analysis includes clickable source links
- Click through to verify claims
- Note source diversity (single source vs. multiple)
- Check publication dates for recency

---

## Configuration

### Tools Configuration

Click the wrench icon to enable/disable specific tools:

**Database Tools**:
- Get Topic Articles
- Semantic Search & Analysis
- Keyword Search
- Follow-up Query

**Analysis Tools**:
- Sentiment Trends Analysis
- Category Analysis
- Real-time News Search

### Sample Size Modes

| Mode | Description | Best For |
|------|-------------|----------|
| **Auto** | System chooses based on query | General use |
| **Balanced** | Moderate article count | Daily research |
| **Comprehensive** | Maximum coverage | Deep analysis |
| **Focused** | Fewer, most relevant | Quick answers |
| **Custom** | Set exact count (10-500) | Specific needs |

### Organizational Profile

For contextualized analysis:
1. Go to Settings → Organizational Profiles
2. Create profile with your organization's focus
3. Select profile when starting Auspex chat
4. Analysis will be tailored to your context

---

## Troubleshooting

### No results returned

- Check topic selection (does topic have articles?)
- Try broader search terms
- Verify date range includes recent articles
- Check if tools are enabled in configuration

### Tool not triggering

- Use explicit trigger words (see badge descriptions above)
- Click the badge directly instead of typing
- Check if required API keys are configured (for web search)

### Slow responses

- Reduce sample size / article limit
- Use faster model (GPT-4o-mini vs GPT-4.1)
- Check network connection
- Large analyses (300+ articles) take longer

### Missing citations/URLs

- This is an LLM behavior issue
- Tools are configured to require URLs
- Try regenerating the analysis
- Report persistent issues

### Chat history not loading

- Refresh the page
- Check if cookies are enabled
- Clear browser cache if persistent

---

## Related Documentation

- [Plugin Development Guide](../data/auspex/plugins/README.md) - Create custom tools
- [Settings](getting-started-settings.md) - Configure AI models and API keys
- [Exploratory Analytics](getting-started-exploratory-analytics.md) - Data visualization
- [Article Investigator](getting-started-article-investigator.md) - Detailed article review

---

*Last updated: 2025-11-26*
