# Exploratory Analytics

## Overview

**Exploratory Analytics** provides interactive data visualization and statistical analysis of your intelligence database. Discover patterns, trends, and anomalies that aren't obvious from reading individual articles.

**Location**: Settings → Analytics (or Analyze → Data Insights)

---

## What's Included

### Temporal Analysis
- **Articles Over Time**: Line charts showing collection volume
- **Trend Detection**: Identify spikes or declines in coverage
- **Seasonality**: Spot recurring patterns
- **Time-of-Day**: When articles are published

### Topic Distribution
- **Pie Charts**: Breakdown by topic category
- **Bar Charts**: Compare topic volumes
- **Topic Evolution**: How topics change over time
- **Topic Correlation**: Which topics appear together

### Source Analysis
- **Top Publishers**: Most prolific sources
- **Media Bias Distribution**: Left/center/right breakdown
- **Credibility Scores**: High vs. low credibility sources
- **Geographic Distribution**: Articles by country

### Sentiment Analysis
- **Overall Sentiment**: Positive/negative/neutral breakdown
- **Sentiment by Topic**: Do some topics skew negative?
- **Sentiment Over Time**: Is coverage becoming more alarming?
- **Sentiment vs. Source Bias**: Correlation analysis

### Entity Analysis
- **Top Entities**: Most-mentioned organizations, people, CVEs
- **Entity Co-occurrence**: Which entities appear together
- **Entity Timeline**: When entities are mentioned
- **Entity Sentiment**: How entities are portrayed

### Advanced Visualizations
- **Heatmaps**: Topic × Sentiment × Time
- **Scatter Plots**: Bias vs. Credibility
- **Radar Charts**: Multi-dimensional analysis
- **Network Graphs**: Entity relationships

---

## Quick Start

### Step 1: Select Data

Filter your analysis:
- **Date Range**: Last 7 days, 30 days, custom range
- **Topics**: Select one or more topics (or all)
- **Sources**: Include/exclude specific publishers
- **Sentiments**: Filter by positive/negative/neutral

### Step 2: Choose Visualization

Pick from available charts:
- **Quick Stats**: Overview cards (total articles, top topic, etc.)
- **Distribution Charts**: Pie/bar charts for categorical data
- **Temporal Charts**: Line charts for trends over time
- **Heatmaps**: Multi-dimensional data
- **Custom**: Build your own visualization

### Step 3: Explore & Drill Down

Interactive features:
- **Click charts**: Filter to specific data points
- **Hover**: See detailed tooltips
- **Zoom**: Temporal charts support zooming
- **Export**: Save charts as PNG/PDF

---

## Use Cases

### Weekly Intelligence Briefing

**Workflow**:
1. Set date range to "Last 7 days"
2. View "Articles Over Time" to spot spikes
3. Check "Topic Distribution" for hot topics
4. Review "Sentiment Over Time" for alarming trends
5. Export charts for slide deck

**Result**: Data-driven weekly briefing with visualizations.

---

### Media Bias Audit

**Workflow**:
1. Set date range to "Last 30 days"
2. View "Media Bias Distribution" pie chart
3. Check "Sentiment by Bias" to see if bias affects tone
4. Review "Top Publishers" by bias category
5. Identify sources to diversify coverage

**Result**: Understanding of source bias, action plan for balance.

---

### Threat Landscape Analysis

**Workflow**:
1. Set topics to all threat-related categories
2. View "Topic Distribution Over Time" heatmap
3. Identify emerging threats (growing topics)
4. Check "Entity Co-occurrence" for attack campaigns
5. Export data for strategic planning

**Result**: Visual representation of evolving threat landscape.

---

### Incident Surge Investigation

**Scenario**: Sudden spike in ransomware coverage

**Workflow**:
1. Filter to "Ransomware" topic
2. View "Articles Over Time" to pinpoint spike
3. Check "Top Entities" during spike (which group?)
4. Review "Source Analysis" (is one source driving spike?)
5. Drill into articles from spike dates

**Result**: Understanding of whether spike is real trend or media echo chamber.

---

## Available Visualizations

### Quick Stats Cards

Top-level metrics displayed as cards:
- **Total Articles**: Count in selected date range
- **Top Topic**: Most frequent category
- **Top Sentiment**: Most common sentiment
- **Average Articles/Day**: Collection rate
- **Top Source**: Most prolific publisher

### Distribution Charts

**Topic Distribution (Pie/Bar)**
- Shows breakdown by topic category
- Click slice/bar to filter to that topic
- Hover for exact counts and percentages

**Sentiment Distribution (Pie/Bar)**
- Positive/Negative/Neutral breakdown
- Color-coded (green/red/gray)
- Compare sentiment across topics

**Source Bias Distribution**
- Left/Left-Center/Center/Right-Center/Right
- Based on Media Bias Fact Check data
- Helps identify coverage balance

**Credibility Distribution**
- Very High/High/Mixed/Low/Very Low
- Based on source ratings
- Quality control metric

### Temporal Charts

**Articles Over Time (Line)**
- Daily article counts
- Zoom to specific date range
- Identify spikes and gaps
- Click point to see articles from that day

**Sentiment Over Time (Line)**
- Track sentiment trends
- Multiple lines (Positive/Negative/Neutral)
- See if coverage is becoming more negative

**Topic Trends (Multi-line)**
- Compare multiple topics over time
- Identify which topics are growing/declining
- Useful for strategic planning

### Heatmaps

**Sentiment × Topic Heatmap**
- Rows: Topics, Columns: Sentiments
- Color intensity shows article count
- Identify which topics are most negative/positive

**Topic × Time Heatmap**
- Rows: Topics, Columns: Days/Weeks
- See topic activity patterns over time
- Spot emerging threats early

### Advanced Charts

**Bias vs. Credibility Scatter**
- X-axis: Political bias (left to right)
- Y-axis: Credibility score
- Each point is an article
- Identify low-credibility biased sources

**Entity Network Graph**
- Nodes: Entities (orgs, people, CVEs)
- Edges: Co-occurrence in articles
- Size: Frequency of mention
- Reveals connections between entities

**Radar Chart**
- Multi-dimensional comparison
- Topics, sentiments, sources
- Good for presentations

---

## Tips & Best Practices

### Data Selection

- Start broad, then narrow down
- Use representative date ranges (30 days minimum for trends)
- Include enough data for statistical significance (50+ articles)

### Visualization Choice

- **Categorical data** (topics, sources): Pie/bar charts
- **Temporal data** (trends): Line charts
- **Multi-dimensional**: Heatmaps or scatter plots
- **Relationships**: Network graphs

### Interpretation

- Correlation ≠ causation
- Watch for sampling bias (limited sources = skewed data)
- Consider external events (holidays, conferences)
- Cross-reference with other sources

### Performance

- Large date ranges (90+ days) may load slowly
- Filter topics to reduce data volume
- Export charts instead of keeping page open

---

## Exporting Data

**Export Options:**
- **PNG/PDF**: Charts for presentations
- **CSV**: Raw data for Excel/R/Python analysis
- **JSON**: Complete data structure
- **Markdown Table**: For documentation

**How to Export:**
1. Generate your visualization
2. Click **Export** button (top-right)
3. Select format
4. Choose location to save

---

## Combining with Other Features

### Research Workflow

1. **Exploratory Analytics** → Identify interesting patterns
2. **Article Investigator** → Drill into specific articles
3. **Narrative Explorer** → AI analysis of patterns
4. **Six Articles** → Executive summary

### Monthly Reporting

1. **Exploratory Analytics** → Generate trend charts
2. Export charts as PNG
3. Add to monthly report template
4. Include commentary on notable trends

### Quality Control

1. **Source Analysis** → Check bias distribution
2. **Credibility Charts** → Ensure high-quality sources
3. **Collection Volume** → Verify consistent collection
4. Alert on anomalies

---

## Troubleshooting

### Charts not loading

- Too much data (narrow date range or topics)
- Browser compatibility (use Chrome/Firefox)
- Check JavaScript console for errors

### Data seems wrong

- Verify filter settings (did you exclude data accidentally?)
- Check date range (timezone issues?)
- Refresh data (click reload button)

### Slow performance

- Reduce date range
- Filter to specific topics
- Export data instead of live visualization

### Missing visualizations

- Ensure you have data for selected filters
- Some charts require minimum data (e.g., 10+ articles)
- Check that JavaScript is enabled

---

## Related Documentation

- [Model Bias Arena](getting-started-model-bias-arena.md) - Compare AI models
- [Article Investigator](getting-started-article-investigator.md) - Detailed article review
- [Operations HQ](getting-started-operations-hq.md) - System health metrics

---

*Last updated: 2025-11-25*
