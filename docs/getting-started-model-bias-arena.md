# Model Bias Arena

## Overview

**Model Bias Arena** is a comparative testing environment that evaluates and compares AI models for bias across multiple dimensions. Test how different AI providers (OpenAI, Anthropic, Google) interpret and analyze the same threat intelligence content.

**Location**: Analyze → Model Bias Arena

---

## Why Use It?

- **Model Selection**: Compare which AI model best fits your analysis needs
- **Bias Detection**: Identify systematic biases in AI-generated analysis
- **Quality Assurance**: Validate that AI outputs are consistent and reliable
- **Vendor Evaluation**: Make data-driven decisions about AI provider contracts

---

## How It Works

The arena runs the same articles through multiple AI models and compares:

- **Summary Quality**: How well each model captures key points
- **Tone and Sentiment**: How each model interprets article sentiment
- **Factual Accuracy**: Consistency with source material
- **Political Bias**: Whether models inject political framing
- **Length and Detail**: Verbosity vs. conciseness
- **Entity Extraction**: Accuracy in identifying organizations, people, CVEs

---

## Quick Start

### Step 1: Create New Evaluation

1. Click **New Evaluation** button
2. Enter evaluation name (e.g., "AI News Bias Test - January 2025")
3. Add optional description
4. Click **Create**

### Step 2: Select Articles

Choose articles to test:
- **Topic Filter**: Select specific topics (e.g., "Ransomware", "APT Groups")
- **Date Range**: Choose time period
- **Article Count**: 5-20 articles recommended
- **Random Sample**: Check to get representative sample

### Step 3: Select Models

Choose which AI models to compare:
- **OpenAI**: GPT-4, GPT-4-turbo, GPT-3.5-turbo
- **Anthropic**: Claude 3 Opus, Claude 3 Sonnet, Claude 3 Haiku
- **Google**: Gemini Pro, Gemini 1.5

**Tip**: Start with 2-3 models for faster results.

### Step 4: Configure Analysis

- **Summary Length**: 40-100 words
- **Analysis Depth**: Quick scan vs. deep analysis
- **Prompt Template**: Use default or customize

### Step 5: Run Evaluation

Click **Start Evaluation** and wait:
- Small evaluations (5 articles, 2 models): 2-5 minutes
- Large evaluations (20 articles, 5 models): 10-20 minutes

---

## Understanding Results

### Overview Dashboard

Top-level metrics:
- **Model Rankings**: Overall performance scores
- **Bias Scores**: Average political bias detected
- **Consistency Scores**: Agreement between models
- **Quality Metrics**: Summary quality, accuracy, completeness

### Article-by-Article Comparison

For each article:
- **Side-by-Side Summaries**: Compare outputs from each model
- **Sentiment Analysis**: How each model rates sentiment
- **Entity Extraction**: Which entities each model identified
- **Bias Detection**: Political framing differences
- **Factual Consistency**: Agreement with source material

### Visualization Charts

- **Bias Scatter Plot**: Political bias vs. factual accuracy
- **Quality Heatmap**: Model performance across articles
- **Consistency Matrix**: Agreement between model pairs
- **Entity Comparison**: Entity extraction accuracy

---

## Use Cases

### Selecting an AI Provider

**Scenario**: Your organization needs to choose between OpenAI and Anthropic.

**Workflow**:
1. Create evaluation: "Provider Selection Test"
2. Select 20 representative articles from your intelligence topics
3. Compare GPT-4 vs. Claude 3 Opus
4. Review bias scores, summary quality, and cost
5. Make data-driven decision

**Result**: Evidence-based vendor selection with documented comparison.

---

### Detecting AI Bias

**Scenario**: You suspect your AI summaries are politically biased.

**Workflow**:
1. Create evaluation: "Bias Detection - Political Coverage"
2. Select articles from politically-charged topics
3. Run all available models (OpenAI, Anthropic, Google)
4. Compare political bias scores across models
5. Identify which models show least bias

**Result**: Objective measurement of AI bias, ability to switch models if needed.

---

### Quality Assurance

**Scenario**: Validating that AI summaries meet organizational standards.

**Workflow**:
1. Create evaluation monthly
2. Use same 10 "golden standard" articles each time
3. Track summary quality and consistency over time
4. Alert if quality degrades (model updates, API changes)

**Result**: Ongoing monitoring of AI output quality.

---

### Research and Publishing

**Scenario**: Writing a paper on AI bias in threat intelligence analysis.

**Workflow**:
1. Design evaluation with research methodology
2. Run large-scale comparison (50+ articles, all models)
3. Export raw data for statistical analysis
4. Generate visualizations for publication
5. Document methodology and findings

**Result**: Publishable research with reproducible methodology.

---

## Tips & Best Practices

### Article Selection

- Use diverse topics to avoid topic-specific bias
- Include articles from different sources (left/right/center bias)
- Mix breaking news with analytical pieces
- Ensure articles are in English (or model's native language)

### Model Comparison

- Test 3+ models for meaningful comparison
- Include at least one model from each provider
- Compare similar-tier models (GPT-4 vs. Claude Opus, not GPT-3.5 vs. Claude Opus)
- Run smaller test first, then scale up

### Interpreting Results

- No model is "perfect" - look for patterns, not perfection
- Low bias score doesn't mean unbiased, just less detected bias
- Consider cost vs. quality tradeoffs
- Re-run evaluations periodically (models change over time)

### Cost Management

- Evaluations consume API credits (# articles × # models)
- Start small (5 articles, 2 models)
- Use cheaper models (GPT-3.5, Claude Haiku) for testing
- Save expensive models (GPT-4, Claude Opus) for final runs

---

## Exporting Results

**Export Options:**
- **PDF Report**: Executive summary with charts
- **CSV Data**: Raw scores for statistical analysis
- **JSON**: Complete data dump for programmatic use
- **Markdown**: Documentation-friendly format

---

## Troubleshooting

### Evaluation taking too long

- Reduce article count (try 5 articles first)
- Fewer models (2-3 instead of 5+)
- Check API rate limits

### No results appearing

- Verify API keys are configured
- Check article selection criteria (did you get 0 articles?)
- Look at browser console for errors

### Inconsistent results

- AI models are non-deterministic (slight variation is normal)
- Run multiple evaluations and average results
- Use higher article counts for statistical significance

---

## Related Documentation

- [Exploratory Analytics](getting-started-exploratory-analytics.md) - Data visualization
- [Article Investigator](getting-started-article-investigator.md) - Detailed article review
- [Settings](getting-started-settings.md) - Configure AI models

---

*Last updated: 2025-11-25*
