# Observer Agents

Observer Agents automate article monitoring based on custom criteria.

***

#### Creating an Observer Agent

1. Navigate to **Observer Agents** section
2. Click **"Add Agent"**
3. Configure agent settings:

**Basic Configuration**

* **Agent Name** - Descriptive name for the agent
* **Research Instruction** - What to look for in articles
* **Topic Filter** - Limit to specific topic (optional)
* **AI Model** - Model to use for analysis

**Actions (When Matches Found)**

* **Add Notification** - Alert in notification bell
* **Tag Articles** - Add signal tags for filtering
* **Star Articles** - Add to starred collection
* **Generate Report** - Create summary report
* **Generate Podcast** - Audio summary (requires ElevenLabs)
* **Deep Research** - Trigger Auspex investigation
* **Send Email** - Email notification
* **Send Bluesky DM** - Direct message on Bluesky

<figure><img src="../.gitbook/assets/image (3).png" alt=""><figcaption></figcaption></figure>

***

#### Scheduled Execution

Enable automated agent runs with configurable:

| Setting               | Options                             |
| --------------------- | ----------------------------------- |
| **Schedule Type**     | Interval or Daily                   |
| **Interval**          | Every N minutes/hours/days          |
| **Daily Time**        | Specific time (server timezone)     |
| **Article Timeframe** | How far back to analyze (1-30 days) |

**Article Timeframe Configuration**

When scheduling an agent, configure how far back to scan articles:

| Option            | Use Case                                 |
| ----------------- | ---------------------------------------- |
| **Last 24 hours** | High-frequency monitoring, breaking news |
| **Last 3 days**   | Regular daily briefings                  |
| **Last 7 days**   | Weekly summaries (default)               |
| **Last 2 weeks**  | Extended coverage analysis               |
| **Last 30 days**  | Monthly trend reports                    |

> **Important:** The Article Timeframe setting determines which articles are analyzed on each automated run. This is independent of the schedule frequency.

***

### Best Practices

#### Keyword Optimization

1. **Start Focused** - Begin with 5-10 high-quality keywords
2. **Use Phrases** - Multi-word phrases reduce noise (e.g., "artificial intelligence" vs "AI")
3. **Avoid Generics** - Skip overly common terms that match too broadly
4. **Monitor Quotas** - Each keyword = 1 API request per collection cycle

#### Theme Detection

1. **Accumulate Articles First** - Wait for 50+ articles before first detection
2. **Adjust Timeframe** - Longer timeframes find broader trends; shorter find breaking news
3. **Review Regularly** - Themes improve with feedback over time
4. **Track Important Themes** - Use tracking to monitor evolution

#### Observer Agent Efficiency

1. **Specific Instructions** - Clear, detailed instructions improve accuracy
2. **Appropriate Timeframes** - Match article timeframe to schedule frequency
3. **Alert Thresholds** - Set minimum matches to avoid notification fatigue
4. **Combine Actions** - Use reports + email for comprehensive alerting

***

### Configuration Reference

#### Theme Detection API

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

#### Observer Agent Config Schema

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

#### Schedule Configuration

```json
{
  "schedule_enabled": true,
  "schedule_type": "interval",
  "schedule_interval": 24,
  "schedule_unit": "hours",
  "schedule_time": "09:00"
}
```

| Field               | Type    | Description                         |
| ------------------- | ------- | ----------------------------------- |
| `schedule_enabled`  | boolean | Enable/disable scheduled execution  |
| `schedule_type`     | string  | "interval" or "daily"               |
| `schedule_interval` | integer | Interval value (when type=interval) |
| `schedule_unit`     | string  | "minutes", "hours", or "days"       |
| `schedule_time`     | string  | HH:MM format (when type=daily)      |
