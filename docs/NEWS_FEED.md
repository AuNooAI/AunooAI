# News Feed Page - User Guide

## Overview

The News Feed page is AuNoo AI's primary interface for exploring, analyzing, and monitoring news articles. Designed with a Google News-inspired layout, it combines AI-powered insights with intuitive navigation to help you stay informed on topics that matter.

---

## Table of Contents

1. [Page Layout](#page-layout)
2. [Navigation Tabs](#navigation-tabs)
3. [Feed Tab](#feed-tab)
4. [Emerging Themes Tab](#emerging-themes-tab)
5. [Observer Agents Tab](#observer-agents-tab)
6. [Saved Tab](#saved-tab)
7. [Configuration Options](#configuration-options)
8. [Auspex Research Assistant](#auspex-research-assistant)
9. [Keyboard Shortcuts & Tips](#keyboard-shortcuts--tips)

---

## Page Layout

### Header Bar

The header provides quick access to essential controls:

| Element | Description |
|---------|-------------|
| **Topic Selector** | Switch between configured topics |
| **Date Range** | Filter articles by time period (24h, 3d, 7d, 30d, All) |
| **Refresh Button** | Manually refresh article data |
| **Schedule Button** | Configure automated dashboard generation |
| **Notification Bell** | View alerts from Observer Agents |
| **Settings Gear** | Access section visibility controls |

### Navigation Tabs

Four main tabs organize the interface:

```
┌─────────────────────────────────────────────────────────────┐
│  Feed  │  Emerging Themes  │  Observer Agents  │  Saved    │
└─────────────────────────────────────────────────────────────┘
```

---

## Feed Tab

The main news browsing experience, divided into four configurable sections.

### Section 1: Your Briefing

An AI-generated executive summary of the most important stories.

**Features:**
- **Top Stories** - 6 curated articles with AI-generated summaries
- **Persona Selection** - Customize the briefing perspective:
  - Executive Overview
  - Technical Deep Dive
  - Risk & Compliance Focus
  - Market Intelligence
- **Quick Actions** - Star articles, click for details, ask Auspex

**Configuration:**
Click the gear icon to customize:
- Number of articles (3-10)
- Summary style and length
- Focus areas and priorities

### Section 2: Highlights (Incident Tracking)

AI-detected significant events and developments across your articles.

**Features:**
- **Incident Cards** - Each highlight shows:
  - Incident name and severity
  - Related article count
  - Key entities involved
  - Sentiment indicator
- **Save/Track** - Bookmark incidents for ongoing monitoring
- **Expand** - View all related articles

**What Qualifies as an Incident:**
- Breaking news with significant impact
- Major announcements or policy changes
- Security events or breaches
- Market-moving developments

### Section 3: Narratives

Thematic analysis showing how stories connect and evolve.

**Features:**
- **Theme Cards** - Display:
  - Theme name and summary
  - Sentiment analysis (positive/negative/neutral)
  - Confidence score
  - Article and source count
  - Key entities
- **Save Narrative** - Track themes over time
- **Ask Auspex** - Deep dive into any narrative

**Narrative vs Incident:**
- **Incidents** = Discrete events (what happened)
- **Narratives** = Ongoing themes (what's the story)

### Section 4: Latest News (Topic Clusters)

Google News-style grid of articles organized by category.

**Layout:**
- Multi-column grid (3 columns on desktop)
- Top 9 categories displayed with articles
- Remaining categories shown as clickable chips
- Each cluster shows:
  - Category name with icon
  - Article count
  - Related articles (semantically clustered)

**Interactions:**
- Click article to open detail panel
- Click "See more" to view full category
- Star articles for later reference

---

## Emerging Themes Tab

Automated detection of developing trends and patterns.

*See [EMERGING_THEMES.md](./EMERGING_THEMES.md) for complete documentation.*

### Quick Overview

**Dashboard Components:**
- Stats summary (Total Themes, Signals, Velocity breakdown)
- Topics Timeline chart
- Category Distribution radar
- Score Distribution histogram
- Velocity Distribution breakdown

**Theme Cards:**
- Expandable cards with full analysis
- Events timeline visualization
- Implications and organization impact
- Actions: Share, Future Horizons, Auspex, Track

**Detection Configuration:**
- Days back (1-30)
- AI model selection
- Auto-detection scheduling

---

## Observer Agents Tab

Automated monitoring agents that scan articles based on custom criteria.

### Agents Overview

View and manage all configured Observer Agents:

| Column | Description |
|--------|-------------|
| **Status** | Active/Paused indicator |
| **Name** | Agent name and description |
| **Last Run** | Time since last execution |
| **Alerts** | Unread alert count |
| **Schedule** | Interval or daily schedule |
| **Actions** | Run, Edit, Delete |

### Creating an Agent

1. Click **"Add Agent"**
2. Configure basic settings:
   - **Name** - Descriptive identifier
   - **Research Instruction** - What to look for
   - **Topic Filter** - Limit to specific topic (optional)
   - **AI Model** - Model for analysis

3. Configure actions (when matches found):
   - Add notification
   - Tag matching articles
   - Star matching articles
   - Generate report
   - Generate podcast summary
   - Trigger deep research
   - Send email notification
   - Send Bluesky DM

4. Configure scheduling (optional):
   - **Schedule Type** - Interval or Daily
   - **Interval** - Every N minutes/hours/days
   - **Daily Time** - Specific time (server timezone)
   - **Article Timeframe** - Days back to analyze (1-30)

### Quick Start Templates

Pre-configured agent templates:
- **Executive Mentions** - C-level announcements and decisions
- **Regulatory Changes** - Policy and compliance updates
- **Competitive Intelligence** - Competitor activities
- **Emerging Threats** - Security vulnerabilities and attacks
- **Adverse Media Screening** - Negative coverage and legal issues
- **Brand Monitoring** - Brand mentions and reputation
- **Competitor Monitoring** - Competitor news and activities

### Running Agents

**Manual Run:**
1. Click the play button on any agent
2. Select timeframe in the Run Modal
3. Choose to tag matching articles
4. Click "Run Agent"

**Run All Active:**
1. Click "Run All" button
2. Select timeframe for all agents
3. Optionally generate unified report
4. Click "Run All Agents"

### Viewing Alerts

Alerts appear in:
- Notification bell (header)
- Agent row alert count
- Alerts section in Observer Agents tab

Each alert shows:
- Matched article title and source
- Match reason/explanation
- Quick actions (view, dismiss, investigate)

---

## Saved Tab

Consolidated view of all bookmarked content.

### Saved Incidents

Incidents you've marked for tracking:
- Full incident details
- Related articles
- Option to unsave

### Saved Narratives

Tracked narrative themes:
- Theme name and summary
- Sentiment and confidence
- Key entities
- Article count

### Tracked Emerging Topics

Emerging themes you're monitoring:
- Topic name and velocity
- Quick navigation to full details

### Saved Podcasts

Audio summaries generated by Observer Agents:
- Podcast title and date
- Play/download options
- Source agent information

### Saved Reports

Intelligence reports from Observer Agents:
- Report title and date
- Full report content
- Source agent and run details

---

## Configuration Options

### Global Settings (Header Gear Icon)

**Section Visibility:**
Toggle which sections appear on the Feed tab:
- [ ] Your Briefing
- [ ] Highlights (Incidents)
- [ ] Narratives
- [ ] Latest News

**Category Management:**
- Reorder categories via drag-and-drop
- Hide/show specific categories
- Reset to default order

### Topic Configuration

Access via the topic selector:
- View topic description
- Edit categories and keywords
- Configure Future Signals
- Access topic-specific settings

### Date Range Options

| Option | Description |
|--------|-------------|
| **24h** | Last 24 hours |
| **3d** | Last 3 days |
| **7d** | Last 7 days (default) |
| **30d** | Last 30 days |
| **All** | All available articles |

### Scheduled Dashboard Generation

Configure automatic generation of dashboard content:

1. Click the **Schedule** button (calendar icon)
2. Enable scheduling
3. Set interval (daily, every 12h, etc.)
4. Choose generation options:
   - Briefing regeneration
   - Incident detection
   - Narrative analysis

---

## Auspex Research Assistant

The AI-powered research assistant is available throughout the interface.

### Accessing Auspex

- Click the **Auspex** floating button (bottom-right)
- Click "Ask Auspex" on any article, incident, or theme
- Use the `?auspex_query=` URL parameter for deep links

### Capabilities

**Research Queries:**
- "What are the key trends in [topic] this week?"
- "Summarize the latest news about [entity]"
- "Compare coverage of [event A] vs [event B]"

**Analysis Requests:**
- "Analyze sentiment around [topic]"
- "Identify emerging themes in [category]"
- "What are the implications of [event]?"

**Deep Dives:**
- Multi-source consensus analysis
- Trend identification
- Expert perspective synthesis

### Context-Aware Queries

When launched from an article or theme, Auspex has context:
- "Tell me more about this" - expands on current item
- "What's the background?" - provides historical context
- "What happens next?" - future implications

---

## Keyboard Shortcuts & Tips

### Navigation

| Shortcut | Action |
|----------|--------|
| `1` | Switch to Feed tab |
| `2` | Switch to Emerging Themes tab |
| `3` | Switch to Observer Agents tab |
| `4` | Switch to Saved tab |
| `R` | Refresh current view |
| `Esc` | Close open panels/modals |

### Article Interactions

| Action | Description |
|--------|-------------|
| **Click title** | Open article detail panel |
| **Click star** | Add/remove from starred |
| **Click source** | Open original article |
| **Click "Ask Auspex"** | Research this article |

### Pro Tips

1. **Use date ranges strategically** - Shorter ranges for breaking news, longer for trend analysis

2. **Star important articles** - Build a reference library for later research

3. **Track key narratives** - Saved narratives persist across sessions

4. **Schedule briefings** - Set up daily briefing generation for morning updates

5. **Combine agents** - Use multiple focused agents rather than one broad agent

6. **Deep link with Auspex** - Share URLs with `?auspex_query=` to guide colleagues to insights

---

## Troubleshooting

### Common Issues

**Articles not loading**
- Check date range selection
- Verify topic has collected articles
- Confirm API connectivity

**Briefing not generating**
- Ensure minimum article count (10+) in timeframe
- Check AI model API quota
- Verify topic configuration

**Incidents/Narratives empty**
- Run initial generation (may take 1-2 minutes)
- Check that articles have been analyzed
- Adjust sensitivity in config

**Observer Agent not matching**
- Review instruction clarity
- Check topic filter setting
- Verify articles exist in timeframe

---

## Related Documentation

- [Emerging Themes Guide](./EMERGING_THEMES.md)
- [Topic Features Guide](./TOPIC_FEATURES.md)
- [Auspex Research Agent](./AUSPEX.md)
- [Observer Agents Reference](./OBSERVER_AGENTS.md)
