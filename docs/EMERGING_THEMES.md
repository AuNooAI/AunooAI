# Emerging Themes & Topic Configuration Guide

## Overview

AuNoo AI's Emerging Themes feature automatically detects and tracks developing narratives, trends, and patterns across your collected news articles. This guide covers the complete setup process from initial onboarding through advanced theme configuration.

---

## Table of Contents

1. [Onboarding Wizard](#onboarding-wizard)
2. [Emerging Themes Dashboard](#emerging-themes-dashboard)
3. [Theme Detection Configuration](#theme-detection-configuration)
4. [Understanding Theme Cards](#understanding-theme-cards)
5. [Observer Agents](#observer-agents)
6. [Best Practices](#best-practices)
7. [Configuration Reference](#configuration-reference)

---

## Onboarding Wizard

A 3-step wizard that helps you configure new topic monitoring.

### Step 1: API Keys

*Auto-skipped if already configured*

Configure the following API keys to enable AuNoo's full capabilities:

#### AI Provider Keys
| Provider | Purpose | Required |
|----------|---------|----------|
| OpenAI | Theme detection, analysis, Auspex research | Yes (or alternative) |
| Anthropic | Alternative AI provider | Optional |
| Google Gemini | Alternative AI provider | Optional |

#### News Provider Keys
| Provider | Purpose | Free Tier |
|----------|---------|-----------|
| NewsAPI | General news collection | 100 requests/day |
| TheNewsAPI | Extended news sources | 3 requests/day |
| NewsData.io | Global news coverage | 200 requests/day |

#### Additional Services
| Service | Purpose |
|---------|---------|
| Firecrawl | Web scraping for full article content |
| ElevenLabs | Podcast/audio generation (optional) |

> **Note:** The onboarding agent runs a basic connectivity test for each API before allowing you to continue.

### Step 2: Topic Setup

Enter your topic details to begin monitoring:

**Topic Name**
A clear, concise name for your monitoring focus (e.g., "APT28 Campaigns", "Cloud Market Trends")

**Description**
A detailed description of what you want to monitor. This helps the AI understand context and improve relevance.

#### What Can Be a Topic?

At the core of AuNoo AI are **topics**: flexible constructs that can represent:

| Type | Examples |
|------|----------|
| **Markets** | Cloud Service Providers, EV Battery Suppliers, Threat Intelligence Providers |
| **Knowledge Fields** | Neurology, Artificial Intelligence, Archeology |
| **Organizations/People** | AI researchers, competitors, specific companies |
| **Scenarios/Questions** | "Is AI hype?", "How strong is Cloud Repatriation?" |

#### AI-Generated Suggestions

After entering your topic name and description, click **"Suggest Categories"**. AuNoo's onboarding agent will generate:

**Future Signals**
Scenarios for the direction a topic can take:
- For AI tracking: "AI is transformative" vs "AI is overhyped"
- For market tracking: "Market Convergence" vs "Market Growth Stalling"

**Categories**
Subcategories for organizing and analyzing data:
- AI topic might include: "AI in Finance", "AI Ethics", "AI Infrastructure"
- Market topic might include: "Quarterly Earnings", "M&A Activity", "Regulatory Changes"

> **Tip:** Use "Get Different Suggestions" to regenerate if the initial suggestions don't fit your needs.

### Step 3: Keywords

Configure keywords for news feed searches:

**Why Keywords Matter**
While AuNoo is a semantic solution, most news feeds still use keyword-based searches. Keywords serve two purposes:
1. Enable searching across different news feeds
2. Improve relevance scoring by providing context to the AI

**Keyword Configuration**
- Review AI-suggested keywords based on your topic
- Add, remove, or edit keywords as needed
- Keywords are used by the Gather module for automated collection

> **Important:** Each keyword issues a separate search request, counting against your API quotas. See [Best Practices](#best-practices) for optimization tips.

---

## Emerging Themes Dashboard

The Emerging Themes tab provides a comprehensive view of detected themes across your collected articles.

### Dashboard Components

#### Stats Summary (Top Row)
Five metric cards showing:

| Metric | Description |
|--------|-------------|
| **Total Themes** | Number of detected emerging themes |
| **Total Signals** | Combined article count across all themes |
| **Accelerating** | Themes with increasing coverage velocity |
| **Stable** | Themes maintaining consistent coverage |
| **Slowing** | Themes with decreasing coverage velocity |

#### Emerging Themes Overview

**Topics Timeline (7 Days)**
Full-width chart showing theme emergence and coverage over time.

**Category Distribution**
Radar chart displaying theme distribution across your configured categories.

**Score Distribution**
Histogram showing the distribution of theme relevance scores.

**Velocity Distribution**
Breakdown of themes by momentum (accelerating/stable/slowing).

### Theme Cards

Each detected theme is displayed as an expandable card containing:

- **Theme Title** - AI-generated descriptive name
- **Velocity Indicator** - Trend direction with color coding
- **Article Count** - Number of related articles
- **Urgency Badge** - Low/Medium/High priority indicator
- **Category Badge** - Classification category
- **Detection Date** - When the theme was first identified

---

## Theme Detection Configuration

Access theme detection settings via the **gear icon** in the Emerging Themes tab header.

### Configuration Options

```json
{
  "daysBack": 7,
  "model": "gpt-4.1-mini",
  "minArticles": 3,
  "maxThemes": 20,
  "categories": ["Technology", "Policy", "Market"],
  "autoDetect": true,
  "detectInterval": 24
}
```

| Setting | Description | Default | Range |
|---------|-------------|---------|-------|
| `daysBack` | Days of articles to analyze | 7 | 1-30 |
| `model` | AI model for detection | gpt-4.1-mini | Configured models |
| `minArticles` | Minimum articles per theme | 3 | 1-10 |
| `maxThemes` | Maximum themes to detect | 20 | 5-50 |
| `autoDetect` | Enable scheduled detection | false | true/false |
| `detectInterval` | Hours between auto-detection | 24 | 1-168 |

### Manual Detection

Click **"Detect Emerging Themes"** to run detection immediately with current settings.

### Scheduled Detection

Enable **"Auto-detect"** to run theme detection on a schedule. Configure the interval based on your news volume and analysis needs.

---

## Understanding Theme Cards

### Expanded Theme View

Clicking a theme card reveals detailed information:

#### Summary Section
- **Key Takeaway** - Primary insight from the theme
- **Description** - Detailed explanation of what the theme represents

#### Events Timeline
Visual timeline showing:
- **Trigger Event** (Red) - The initiating event or development
- **Timeline Items** (Blue) - Chronological progression of related events
- **Current Status** (Green) - Present state of the theme

#### Implications
AI-generated analysis of potential impacts and significance.

#### Organization Implications
Specific implications for your organization or use case (when configured).

#### Related Articles
List of articles that contributed to theme detection, with:
- Article title and source
- Publication date
- Relevance score
- Direct link to full article

### Theme Actions

| Action | Description |
|--------|-------------|
| **Share** | Email theme summary with organization implications |
| **Future Horizons** | Generate forward-looking scenarios |
| **Ask Auspex** | Deep-dive research on the theme |
| **Track** | Add to tracked themes for ongoing monitoring |

---

## Observer Agents

Observer Agents automate article monitoring based on custom criteria.

### Creating an Observer Agent

1. Navigate to **Observer Agents** section
2. Click **"Add Agent"**
3. Configure agent settings:

#### Basic Configuration
- **Agent Name** - Descriptive name for the agent
- **Research Instruction** - What to look for in articles
- **Topic Filter** - Limit to specific topic (optional)
- **AI Model** - Model to use for analysis

#### Actions (When Matches Found)
- **Add Notification** - Alert in notification bell
- **Tag Articles** - Add signal tags for filtering
- **Star Articles** - Add to starred collection
- **Generate Report** - Create summary report
- **Generate Podcast** - Audio summary (requires ElevenLabs)
- **Deep Research** - Trigger Auspex investigation
- **Send Email** - Email notification
- **Send Bluesky DM** - Direct message on Bluesky

### Scheduled Execution

Enable automated agent runs with configurable:

| Setting | Options |
|---------|---------|
| **Schedule Type** | Interval or Daily |
| **Interval** | Every N minutes/hours/days |
| **Daily Time** | Specific time (server timezone) |
| **Article Timeframe** | How far back to analyze (1-30 days) |

#### Article Timeframe Configuration

When scheduling an agent, configure how far back to scan articles:

| Option | Use Case |
|--------|----------|
| **Last 24 hours** | High-frequency monitoring, breaking news |
| **Last 3 days** | Regular daily briefings |
| **Last 7 days** | Weekly summaries (default) |
| **Last 2 weeks** | Extended coverage analysis |
| **Last 30 days** | Monthly trend reports |

> **Important:** The Article Timeframe setting determines which articles are analyzed on each automated run. This is independent of the schedule frequency.

---

## Best Practices

### Keyword Optimization

1. **Start Focused** - Begin with 5-10 high-quality keywords
2. **Use Phrases** - Multi-word phrases reduce noise (e.g., "artificial intelligence" vs "AI")
3. **Avoid Generics** - Skip overly common terms that match too broadly
4. **Monitor Quotas** - Each keyword = 1 API request per collection cycle

### Theme Detection

1. **Accumulate Articles First** - Wait for 50+ articles before first detection
2. **Adjust Timeframe** - Longer timeframes find broader trends; shorter find breaking news
3. **Review Regularly** - Themes improve with feedback over time
4. **Track Important Themes** - Use tracking to monitor evolution

### Observer Agent Efficiency

1. **Specific Instructions** - Clear, detailed instructions improve accuracy
2. **Appropriate Timeframes** - Match article timeframe to schedule frequency
3. **Alert Thresholds** - Set minimum matches to avoid notification fatigue
4. **Combine Actions** - Use reports + email for comprehensive alerting

---

## Configuration Reference

### Theme Detection API

**Endpoint:** `POST /api/emerging-topics/detect`

```json
{
  "days_back": 7,
  "model": "gpt-4.1-mini",
  "sample_size": 100,
  "topic": "optional-topic-filter"
}
```

**Response:**
```json
{
  "success": true,
  "themes_detected": 12,
  "themes": [
    {
      "id": 1,
      "name": "AI Regulation Momentum",
      "description": "Growing legislative activity...",
      "velocity": "accelerating",
      "article_count": 8,
      "urgency": "high",
      "category": "Policy",
      "synthesis": {
        "key_takeaway": "...",
        "implications": ["..."],
        "model_used": "gpt-4.1-mini"
      }
    }
  ]
}
```

### Observer Agent Config Schema

```json
{
  "days_back": 7,
  "max_articles": 100,
  "search_strategy": "recent",
  "alert_threshold": 1,
  "model": "gpt-4o-mini",
  "tag_articles": true,
  "star_flagged_articles": false,
  "deep_research": false,
  "send_email": false,
  "email_recipient": "user@example.com",
  "bluesky_dm": false,
  "bluesky_recipient": "@user.bsky.social",
  "generate_podcast": false,
  "podcast_voice_id": "voice-id",
  "entities_to_monitor": ["Company A", "Person B"]
}
```

### Schedule Configuration

```json
{
  "schedule_enabled": true,
  "schedule_type": "interval",
  "schedule_interval": 24,
  "schedule_unit": "hours",
  "schedule_time": "09:00"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `schedule_enabled` | boolean | Enable/disable scheduled execution |
| `schedule_type` | string | "interval" or "daily" |
| `schedule_interval` | integer | Interval value (when type=interval) |
| `schedule_unit` | string | "minutes", "hours", or "days" |
| `schedule_time` | string | HH:MM format (when type=daily) |

---

## Troubleshooting

### Common Issues

**No themes detected**
- Ensure sufficient articles (50+) in the timeframe
- Check that articles have been analyzed (not just collected)
- Verify AI model has API quota available

**Themes seem irrelevant**
- Refine topic categories and description
- Adjust minimum article threshold
- Review and refine keywords

**Scheduled agent not running**
- Verify `schedule_enabled` is true
- Check server logs for errors
- Confirm next_run_at timestamp is in the past

**Email notifications not sending**
- Verify SMTP configuration in .env
- Check email_recipient is valid
- Confirm alert_threshold is being met

---

## Related Documentation

- [Topic Features Guide](./TOPIC_FEATURES.md)
- [Auspex Research Agent](./AUSPEX.md)
- [API Reference](./API_REFERENCE.md)
- [Best Practices for Keyword Monitoring](./KEYWORD_BEST_PRACTICES.md)
