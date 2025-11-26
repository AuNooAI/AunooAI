# Advanced Features

## Overview

AunooAI includes advanced analytical tools for power users, researchers, and teams that need deeper insights into their intelligence data. These features go beyond basic collection and analysis to provide comparative analysis, bias detection, and exploratory data visualization.

---

## Model Bias Arena

**Location**: Analyze → Model Bias Arena

### What Is It?

Model Bias Arena is a comparative testing environment that evaluates and compares AI models for bias across multiple dimensions. It helps you understand how different AI providers (OpenAI, Anthropic, Google) interpret and analyze the same content.

### Why Use It?

- **Model Selection**: Compare which AI model best fits your analysis needs
- **Bias Detection**: Identify systematic biases in AI-generated analysis
- **Quality Assurance**: Validate that AI outputs are consistent and reliable
- **Vendor Evaluation**: Make data-driven decisions about AI provider contracts

### How It Works

The arena runs the same articles through multiple AI models and compares:
- **Summary Quality**: How well each model captures key points
- **Tone and Sentiment**: How each model interprets article sentiment
- **Factual Accuracy**: Consistency with source material
- **Political Bias**: Whether models inject political framing
- **Length and Detail**: Verbosity vs. conciseness
- **Entity Extraction**: Accuracy in identifying organizations, people, etc.

### Getting Started

#### Step 1: Create New Evaluation

1. Click **New Evaluation** button
2. Enter evaluation name (e.g., "AI News Bias Test - January 2025")
3. Add optional description
4. Click **Create**

#### Step 2: Select Articles

Choose articles to test:
- **Topic Filter**: Select specific topics (e.g., "Ransomware", "APT Groups")
- **Date Range**: Choose time period
- **Article Count**: 5-20 articles recommended (more = longer evaluation)
- **Random Sample**: Check to get representative sample

#### Step 3: Select Models

Choose which AI models to compare:
- **OpenAI Models**: GPT-4, GPT-4-turbo, GPT-3.5-turbo
- **Anthropic Models**: Claude 3 Opus, Claude 3 Sonnet, Claude 3 Haiku
- **Google Models**: Gemini Pro, Gemini 1.5

**Tip**: Start with 2-3 models for faster results. You can run additional models later.

#### Step 4: Configure Analysis

Set parameters:
- **Summary Length**: 40-100 words
- **Analysis Depth**: Quick scan vs. deep analysis
- **Prompt Template**: Use default or customize

#### Step 5: Run Evaluation

Click **Start Evaluation** and wait:
- Small evaluations (5 articles, 2 models): 2-5 minutes
- Large evaluations (20 articles, 5 models): 10-20 minutes
- Progress bar shows completion

### Understanding Results

#### Overview Dashboard

Top-level metrics:
- **Model Rankings**: Overall performance scores
- **Bias Scores**: Average political bias detected
- **Consistency Scores**: Agreement between models
- **Quality Metrics**: Summary quality, accuracy, completeness

#### Article-by-Article Comparison

For each article, see:
- **Side-by-Side Summaries**: Compare outputs from each model
- **Sentiment Analysis**: How each model rates sentiment
- **Entity Extraction**: Which entities each model identified
- **Bias Detection**: Political framing differences
- **Factual Consistency**: Agreement with source material

#### Visualization Charts

- **Bias Scatter Plot**: Political bias vs. factual accuracy
- **Quality Heatmap**: Model performance across articles
- **Consistency Matrix**: Agreement between model pairs
- **Entity Comparison**: Entity extraction accuracy

### Use Cases

#### Selecting an AI Provider

**Scenario**: Your organization needs to choose between OpenAI and Anthropic.

**Workflow**:
1. Create evaluation: "Provider Selection Test"
2. Select 20 representative articles from your intelligence topics
3. Compare GPT-4 vs. Claude 3 Opus
4. Review bias scores, summary quality, and cost
5. Make data-driven decision

**Result**: Evidence-based vendor selection with documented comparison.

---

#### Detecting AI Bias

**Scenario**: You suspect your AI summaries are politically biased.

**Workflow**:
1. Create evaluation: "Bias Detection - Political Coverage"
2. Select articles from politically-charged topics
3. Run all available models (OpenAI, Anthropic, Google)
4. Compare political bias scores across models
5. Identify which models show least bias

**Result**: Objective measurement of AI bias, ability to switch models if needed.

---

#### Quality Assurance

**Scenario**: Validating that AI summaries meet organizational standards.

**Workflow**:
1. Create evaluation monthly
2. Use same 10 "golden standard" articles each time
3. Track summary quality and consistency over time
4. Alert if quality degrades (model updates, API changes)

**Result**: Ongoing monitoring of AI output quality.

---

#### Research and Publishing

**Scenario**: Writing a paper on AI bias in threat intelligence analysis.

**Workflow**:
1. Design evaluation with research methodology
2. Run large-scale comparison (50+ articles, all models)
3. Export raw data for statistical analysis
4. Generate visualizations for publication
5. Document methodology and findings

**Result**: Publishable research with reproducible methodology.

---

### Tips & Best Practices

**Article Selection:**
- Use diverse topics to avoid topic-specific bias
- Include articles from different sources (left/right/center bias)
- Mix breaking news with analytical pieces
- Ensure articles are in English (or model's native language)

**Model Comparison:**
- Test 3+ models for meaningful comparison
- Include at least one model from each provider
- Compare similar-tier models (GPT-4 vs. Claude Opus, not GPT-3.5 vs. Claude Opus)
- Run smaller test first, then scale up

**Interpreting Results:**
- No model is "perfect" - look for patterns, not perfection
- Low bias score doesn't mean unbiased, just less detected bias
- Consider cost vs. quality tradeoffs
- Re-run evaluations periodically (models change over time)

**Cost Management:**
- Evaluations consume API credits (# articles × # models)
- Start small (5 articles, 2 models)
- Use cheaper models (GPT-3.5, Claude Haiku) for testing
- Save expensive models (GPT-4, Claude Opus) for final runs

### Exporting Results

**Export Options:**
- **PDF Report**: Executive summary with charts
- **CSV Data**: Raw scores for statistical analysis
- **JSON**: Complete data dump for programmatic use
- **Markdown**: Documentation-friendly format

---

## Exploratory Analytics

**Location**: Settings → Analytics (or Analyze → Data Insights)

### What Is It?

Exploratory Analytics provides interactive data visualization and statistical analysis of your intelligence database. It's designed for discovering patterns, trends, and anomalies that aren't obvious from reading articles.

### Key Features

#### Temporal Analysis
- **Articles Over Time**: Line charts showing collection volume
- **Trend Detection**: Identify spikes or declines in coverage
- **Seasonality**: Spot recurring patterns (e.g., more attacks on weekends)
- **Time-of-Day**: When are articles published?

#### Topic Distribution
- **Pie Charts**: Breakdown by topic category
- **Bar Charts**: Compare topic volumes
- **Topic Evolution**: How topics change over time
- **Topic Correlation**: Which topics appear together?

#### Source Analysis
- **Top Publishers**: Most prolific sources
- **Media Bias Distribution**: Left/center/right breakdown
- **Credibility Scores**: High vs. low credibility sources
- **Geographic Distribution**: Articles by country

#### Sentiment Analysis
- **Overall Sentiment**: Positive/negative/neutral breakdown
- **Sentiment by Topic**: Do some topics skew negative?
- **Sentiment Over Time**: Is coverage becoming more alarming?
- **Sentiment vs. Source Bias**: Correlation analysis

#### Entity Analysis
- **Top Entities**: Most-mentioned organizations, people, CVEs
- **Entity Co-occurrence**: Which entities appear together?
- **Entity Timeline**: When entities are mentioned
- **Entity Sentiment**: How entities are portrayed

#### Advanced Visualizations
- **Heatmaps**: Topic × Sentiment × Time
- **Scatter Plots**: Bias vs. Credibility
- **Radar Charts**: Multi-dimensional analysis
- **Network Graphs**: Entity relationships

### Getting Started

#### Step 1: Select Data

Filter your analysis:
- **Date Range**: Last 7 days, 30 days, custom range
- **Topics**: Select one or more topics (or all)
- **Sources**: Include/exclude specific publishers
- **Sentiments**: Filter by positive/negative/neutral

#### Step 2: Choose Visualization

Pick from available charts:
- **Quick Stats**: Overview cards (total articles, top topic, etc.)
- **Distribution Charts**: Pie/bar charts for categorical data
- **Temporal Charts**: Line charts for trends over time
- **Heatmaps**: Multi-dimensional data
- **Custom**: Build your own visualization

#### Step 3: Explore & Drill Down

Interactive features:
- **Click charts**: Filter to specific data points
- **Hover**: See detailed tooltips
- **Zoom**: Temporal charts support zooming
- **Export**: Save charts as PNG/PDF

### Use Cases

#### Weekly Intelligence Briefing

**Workflow**:
1. Set date range to "Last 7 days"
2. View "Articles Over Time" to spot spikes
3. Check "Topic Distribution" for hot topics
4. Review "Sentiment Over Time" for alarming trends
5. Export charts for slide deck

**Result**: Data-driven weekly briefing with visualizations.

---

#### Media Bias Audit

**Workflow**:
1. Set date range to "Last 30 days"
2. View "Media Bias Distribution" pie chart
3. Check "Sentiment by Bias" to see if bias affects tone
4. Review "Top Publishers" by bias category
5. Identify sources to diversify coverage

**Result**: Understanding of source bias, action plan for balance.

---

#### Threat Landscape Analysis

**Workflow**:
1. Set topics to all threat-related categories
2. View "Topic Distribution Over Time" heatmap
3. Identify emerging threats (growing topics)
4. Check "Entity Co-occurrence" for attack campaigns
5. Export data for strategic planning

**Result**: Visual representation of evolving threat landscape.

---

#### Incident Surge Investigation

**Scenario**: Sudden spike in ransomware coverage

**Workflow**:
1. Filter to "Ransomware" topic
2. View "Articles Over Time" to pinpoint spike
3. Check "Top Entities" during spike (which group?)
4. Review "Source Analysis" (is one source driving spike?)
5. Drill into articles from spike dates

**Result**: Understanding of whether spike is real trend or media echo chamber.

---

### Tips & Best Practices

**Data Selection:**
- Start broad, then narrow down
- Use representative date ranges (30 days minimum for trends)
- Include enough data for statistical significance (50+ articles)

**Visualization Choice:**
- Categorical data (topics, sources): Pie/bar charts
- Temporal data (trends): Line charts
- Multi-dimensional: Heatmaps or scatter plots
- Relationships: Network graphs

**Interpretation:**
- Correlation ≠ causation
- Watch for sampling bias (limited sources = skewed data)
- Consider external events (holidays, conferences)
- Cross-reference with other sources

**Performance:**
- Large date ranges (90+ days) may load slowly
- Filter topics to reduce data volume
- Export charts instead of keeping page open

### Exporting Data

**Export Options:**
- **PNG/PDF**: Charts for presentations
- **CSV**: Raw data for Excel/R/Python analysis
- **JSON**: Complete data structure
- **Markdown Table**: For documentation

---

## Combining Advanced Features

### Research Workflow

1. **Exploratory Analytics** → Identify interesting patterns
2. **Filter articles** based on findings
3. **Model Bias Arena** → Validate AI isn't biasing your analysis
4. **Six Articles** → Generate executive summary
5. **Document findings** with exported charts and reports

### Quality Assurance Pipeline

1. **Model Bias Arena** → Monthly QA evaluation
2. **Exploratory Analytics** → Check for data quality issues (missing metadata, etc.)
3. **Trend analysis** → Ensure collection coverage is consistent
4. **Alert on anomalies** → Spike in low-credibility sources, etc.

---

## Troubleshooting

### Model Bias Arena Issues

**Evaluation taking too long:**
- Reduce article count (try 5 articles first)
- Fewer models (2-3 instead of 5+)
- Check API rate limits

**No results appearing:**
- Verify API keys are configured
- Check article selection criteria (did you get 0 articles?)
- Look at browser console for errors

**Inconsistent results:**
- AI models are non-deterministic (slight variation is normal)
- Run multiple evaluations and average results
- Use higher article counts for statistical significance

### Exploratory Analytics Issues

**Charts not loading:**
- Too much data (narrow date range or topics)
- Browser compatibility (use Chrome/Firefox)
- Check JavaScript console for errors

**Data seems wrong:**
- Verify filter settings (did you exclude data accidentally?)
- Check date range (timezone issues?)
- Refresh data (click reload button)

**Slow performance:**
- Reduce date range
- Filter to specific topics
- Export data instead of live visualization

---

## Related Documentation

- [Article Investigator](getting-started-article-investigator.md) - For detailed article review
- [Six Articles](getting-started-six-articles.md) - For executive briefings
- [Anticipate](getting-started-anticipate.md) - For strategic analysis

---

*Last updated: 2025-11-25*
