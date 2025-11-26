# Getting Started with Gather (News Firehose)

## Overview

**Gather** (also known as **News Firehose**) is your automated intelligence collection system. This powerful tool monitors keywords across multiple news providers, automatically collects matching articles, and surfaces emerging trends before they become mainstream threats.

Think of Gather as your 24/7 intelligence collector—constantly scanning the threat landscape for signals that matter to your organization.

## What is Gather?

Gather automates the intelligence collection process:

- **Keyword Monitoring**: Track specific threats, actors, technologies, or topics
- **Multi-Source Collection**: Search across multiple news providers simultaneously
- **Auto-Processing Pipeline**: Automatically download, score, and approve relevant articles
- **Emerging Trends**: Visualize growth patterns and detect breakout stories
- **Smart Alerts**: Group related articles by topic and keyword clusters

## Key Concepts

### Keyword Groups
Keywords are organized into **groups** by topic (e.g., "APT28", "Ransomware Trends", "Log4j"). Each group can contain multiple related keywords and tracks its own collection statistics.

### Auto-Processing Pipeline
When enabled, Gather automatically:
1. **Searches** news providers based on your keywords
2. **Downloads** matching articles
3. **Scores** relevance using AI
4. **Filters** low-quality or irrelevant content
5. **Saves** approved articles to your intelligence database

### Emerging Trends Overview
A visual dashboard showing:
- **Growth Status**: Accelerating, stable, or declining trends
- **Sparkline Charts**: Article volume over time
- **Alert Counts**: Number of unread articles per group
- **Tags**: Keywords that triggered the match

## Getting Started

### Step 1: Set Up Your Keywords

1. Click **Manage Keywords** in the toolbar
2. This takes you to the Keyword Monitor page where you can:
   - Create new keyword groups by topic
   - Add keywords to existing groups
   - Configure search operators (AND, OR, NOT)
   - Enable/disable specific keyword groups

**Tip**: Start with 3-5 high-priority threat topics and expand from there.

### Step 2: Configure Auto-Collection

1. Click **Auto-Collect** in the toolbar
2. Configure your collection settings:
   - **Enable Auto-Collection**: Turn on automated searching
   - **Check Interval**: How often to search (every 15 min to 24 hours)
   - **Search Date Range**: How far back to look (1-30 days)
   - **News Providers**: Select which sources to monitor
   - **Search Fields**: Where to look (title, description, content)

3. Set up the Auto-Processing Pipeline:
   - **Relevance Threshold**: Minimum score to auto-approve (0-100)
   - **Auto-Tagging**: Automatically assign topics to articles
   - **Enrichment**: Add entity extraction and geolocation
   - **Quality Control**: Filter duplicates and low-credibility sources

4. Click **Save Settings**

### Step 3: Enable Auto-Processing

1. Toggle the **Auto-Processing** switch in the top-right corner to **ON**
2. Gather will now run automatically based on your check interval
3. Monitor the status ticker to see:
   - Last search time
   - Processing job count (if active)
   - Any errors or issues

### Step 4: Manual Updates (Optional)

- Click **Update Now** to immediately search all active keyword groups
- Use this for breaking news or when you can't wait for the next scheduled run
- Monitor the progress in the status badge

## Understanding the Dashboard

### Emerging Trends Table

Each row represents a keyword group with the following columns:

#### Status Badge
- **Accelerating**: Article volume increasing rapidly
- **Stable**: Steady flow of articles
- **Declining**: Fewer articles than before
- **No Data**: No recent articles found

#### Emerging Trend
- **Group Name**: Your keyword group (e.g., "APT28 Campaigns")
- **Topic**: The assigned topic category

#### Growth Chart (Sparkline)
- Visual representation of article volume over the last 7-14 days
- Helps identify sudden spikes or sustained growth
- Hover to see approximate counts

#### Size (Alert Count)
- **X alerts**: Number of unread articles in this group
- Click to expand and view the articles

#### Tags & Enrichment
- **Keyword Tags**: Which keywords triggered the match
- Shows first 3-5 keywords, expandable to see all

#### Detected
- When the trend was first detected
- Helps prioritize breaking vs. ongoing stories

### Article Cards

When you expand a keyword group, each article shows:

- **Title & Source**: Article headline and publisher
- **Published Date**: When the article was published
- **Summary**: AI-generated or source-provided summary
- **Matched Keywords**: Which keywords triggered this alert
- **Actions**:
  - **View Full Article**: Open in Explore View for detailed analysis
  - **Mark as Read**: Remove from unread count
  - **Delete**: Remove from the firehose (doesn't delete from main database)
  - **Analyze**: Run deep analysis or add to investigation

## Common Workflows

### Daily Monitoring (10 minutes)

1. Open Gather page
2. Scan the Emerging Trends table for "Accelerating" status
3. Click to expand high-priority keyword groups
4. Review article titles and summaries
5. Click **View Full Article** for critical items
6. Mark others as read or delete noise

**Result**: Stay current on breaking threats without manual searching.

---

### Weekly Trend Analysis (30 minutes)

1. Review all keyword groups in the dashboard
2. Look for sustained growth patterns in sparklines
3. Identify new keywords appearing frequently
4. Expand groups with high alert counts
5. Bulk analyze selected articles
6. Update keyword groups based on findings:
   - Add new emerging keywords
   - Remove outdated or noisy keywords
   - Adjust relevance thresholds

**Result**: Understand evolving threat landscape and optimize collection.

---

### Breaking Threat Response (Immediate)

1. Hear about breaking vulnerability/attack
2. Click **Manage Keywords** → Create new group
3. Add keywords related to the threat (CVE ID, malware name, etc.)
4. Return to Gather page
5. Click **Update Now** to immediately collect articles
6. Review results in real-time as they appear
7. Use **Analyze Selected** for rapid threat assessment

**Result**: Rapid intelligence collection on emerging threats.

---

### Initial Setup (1 hour)

1. **Plan your coverage** (15 min)
   - List high-priority threat categories
   - Identify key threat actors, malware families, vulnerabilities
   - Note specific campaigns or technologies to monitor

2. **Create keyword groups** (30 min)
   - Click **Manage Keywords**
   - Create 5-10 groups by topic
   - Add 3-7 keywords per group
   - Test each group with manual search

3. **Configure auto-collection** (10 min)
   - Click **Auto-Collect**
   - Set check interval (recommend 6-12 hours initially)
   - Select news providers (start with 2-3 high-quality sources)
   - Enable auto-processing with moderate thresholds (60-70)

4. **Run first collection** (5 min)
   - Click **Update Now**
   - Review results
   - Adjust settings if too much noise or too few results

**Result**: Fully automated intelligence collection system.

---

### Bulk Analysis & Triage (20 minutes)

1. Expand a keyword group with many unread alerts
2. Click the checkbox column header to select all
3. Or manually select specific articles of interest
4. Click **Analyze Selected** in the toolbar
5. Choose analysis type:
   - Relevance scoring
   - Entity extraction
   - Threat classification
   - Duplicate detection
6. Review analysis results
7. Bulk mark as read or delete low-value items

**Result**: Efficiently process large volumes of collected intelligence.

## Key Features

### Submit Articles
Manually add articles that weren't caught by keyword monitoring:
- Click **Submit Articles**
- Enter article URL or paste text
- Assign topic and tags
- Article is processed like auto-collected content

### Update Now
Immediately trigger a search across all active keyword groups:
- Click **Update Now**
- Bypass the scheduled check interval
- Useful for breaking news or time-sensitive threats
- Monitor progress via status badge

### Auto-Collect Settings
Fine-tune your automated collection:

#### Article Collection
- **Enable/Disable**: Turn auto-collection on/off
- **Check Interval**: 15 minutes to 24 hours
- **Search Date Range**: 1-30 days lookback
- **Daily Request Limit**: API rate limiting (default 100)

#### Search Configuration
- **News Providers**: Select multiple sources (NewsAPI, GoogleNews, etc.)
- **Search Fields**: Title, description, and/or content
- **Language**: Filter by language (English, Russian, Chinese, etc.)
- **Sort By**: Newest first or most relevant

#### Auto-Processing Options
- **Relevance Threshold**: Minimum score (0-100) to auto-approve
- **Auto-Tagging**: Automatically assign topics based on content
- **Entity Extraction**: Identify organizations, people, locations
- **Duplicate Detection**: Filter out redundant articles
- **Quality Control**: Block low-credibility sources

### Manage Keywords
Jump to the Keyword Monitor page to:
- Create new keyword groups
- Edit existing keywords
- Enable/disable groups
- Test keyword queries before saving

### Cancel Task
Stop a running background collection job:
- Appears when a task is in progress
- Click **Cancel Task** to stop immediately
- Useful if you triggered a search by mistake

## Tips & Tricks

### Effective Keyword Strategy

**Use Specific Keywords**
- ✅ "APT28 Fancy Bear" (specific threat actor)
- ❌ "Russian hackers" (too broad)

**Combine Keywords**
- Group related keywords: "Log4j", "Log4Shell", "CVE-2021-44228"
- Use operators: "ransomware AND healthcare"
- Exclude noise: "data breach NOT celebrity"

**Monitor Multiple Variants**
- Include common misspellings or variations
- Track both code names and formal designations
- Consider language variations for international threats

### Optimizing Auto-Collection

**Start Conservative**
- Begin with 6-12 hour check intervals
- Use moderate relevance thresholds (60-70)
- Select 2-3 high-quality news providers
- Monitor for a week, then adjust

**Reduce Noise**
- Increase relevance threshold if too many low-value articles
- Enable duplicate detection
- Exclude specific sources in provider settings
- Refine keywords to be more specific

**Increase Coverage**
- Add more news providers
- Lower relevance threshold slightly (50-60)
- Expand search date range
- Add more keyword variations

### Reading the Dashboard

**Prioritize by Status**
1. **Accelerating** trends (potential breaking news)
2. High alert counts (lots of new content)
3. Groups you haven't checked in 24+ hours

**Use Sparklines**
- Sharp spikes = breaking story
- Sustained growth = ongoing campaign
- Flat lines = stable monitoring (expected for some topics)

**Manage Alert Overload**
- Bulk select and mark as read
- Delete obvious noise immediately
- Use the "Analyze Selected" feature for batch processing
- Consider disabling noisy keyword groups

### Integration with Other Features

**Gather → Explore View**
- Click "View Full Article" to open in Article Investigator
- Collected articles appear in Explore View automatically
- Use Narrative Explorer to find patterns across gathered articles

**Gather → Six Articles**
- Auto-collected articles feed into Six Articles briefings
- High-quality gathered articles appear in top recommendations
- Use Six Articles to brief leadership on gathered intelligence

**Gather → Investigations**
- Submit interesting articles to ongoing investigations
- Use gathered articles as seed data for threat hunting
- Track specific incidents by creating dedicated keyword groups

## Troubleshooting

### "No articles appearing after Update Now"

**Possible Causes:**
- Keywords too specific (no matching articles exist)
- Date range too narrow (expand to 7-14 days)
- News providers not returning results (check provider status)
- API rate limits exceeded (wait or increase daily limit)

**Solutions:**
1. Check **Manage Keywords** to verify keywords are enabled
2. Click **Auto-Collect** to verify news providers are selected
3. Try broader keywords temporarily to test
4. Check error messages in the status ticker

---

### "Too many irrelevant articles"

**Possible Causes:**
- Keywords too broad (matching unrelated content)
- Relevance threshold too low (auto-approving everything)
- Search fields including noisy content (description/content)

**Solutions:**
1. Increase relevance threshold in Auto-Collect settings (try 70-80)
2. Make keywords more specific (add context or operators)
3. Enable duplicate detection
4. Search title only (uncheck description/content)
5. Review and delete noisy articles, then adjust keywords

---

### "Auto-processing not running"

**Possible Causes:**
- Auto-Processing toggle is OFF
- Check interval too long (24 hours)
- Background worker not running (server issue)

**Solutions:**
1. Verify the Auto-Processing toggle is **ON** (top-right)
2. Click **Auto-Collect** and verify "Enable Auto-Collection" is checked
3. Check "Last search" time to see if it's running at all
4. Use **Update Now** to manually trigger (tests the pipeline)
5. Contact administrator if manual updates work but auto doesn't

---

### "Processing jobs stuck"

**Possible Causes:**
- Large number of articles being processed
- AI scoring taking longer than expected
- Background worker crashed

**Solutions:**
1. Wait 5-10 minutes (large jobs take time)
2. Click **Cancel Task** to stop the current job
3. Refresh the page and check status
4. Try **Update Now** again with fewer keyword groups enabled

---

### "Rate limit exceeded"

**Possible Causes:**
- Too many API requests in 24 hours
- Check interval too frequent (every 15 min)
- Many keyword groups with overlapping searches

**Solutions:**
1. Increase check interval (6-12 hours recommended)
2. Reduce the number of active keyword groups
3. Increase "Daily Request Limit" in Auto-Collect settings
4. Wait 24 hours for rate limit to reset
5. Consider upgrading news provider API tier

## Best Practices

### For Threat Intelligence Teams

**Daily Routine:**
- Check Gather first thing each morning (5-10 min)
- Review accelerating trends
- Mark irrelevant items as read
- Deep dive on high-priority alerts in Explore View

**Weekly Maintenance:**
- Analyze keyword performance (which groups find valuable content?)
- Add new keywords based on emerging threats
- Remove noisy or outdated keywords
- Adjust relevance thresholds based on quality

**Monthly Review:**
- Evaluate news provider effectiveness
- Consider adding new sources
- Review auto-processing metrics (approval rates, false positives)
- Share keyword strategies with team

### For Solo Analysts

**Automate Everything:**
- Set check interval to 12-24 hours
- Use high relevance thresholds (70-80) to reduce noise
- Enable all auto-processing features
- Focus your time on analysis, not collection

**Curate Keywords:**
- Start with 5-7 high-priority groups
- Add keywords gradually based on what you actually use
- Don't try to monitor everything—focus on your organization's risk profile

**Leverage Integrations:**
- Use Gather for collection, Explore for analysis
- Run Six Articles on gathered intelligence for daily briefs
- Archive valuable finds in investigations or reports

### For Large Organizations

**Divide Responsibilities:**
- Assign keyword groups to specific analysts or teams
- One person manages Auto-Collect settings globally
- Share successful keyword strategies across teams

**Standardize Workflows:**
- Document which groups map to which topics
- Establish SLAs for reviewing high-priority alerts
- Use consistent tagging and enrichment settings

**Integrate with SIEM/TIP:**
- Export gathered articles via API for downstream systems
- Use Gather as first-stage collection before SOAR automation
- Track metrics (collection volume, approval rates, time-to-detection)

## Advanced Features

### Bulk Operations

**Bulk Delete:**
- Select multiple articles with checkboxes
- Click **Delete Selected** in toolbar
- Quickly clear noise without reviewing each article

**Bulk Analyze:**
- Select articles of interest
- Click **Analyze Selected**
- Run AI analysis, entity extraction, or classification in batch

### Custom Enrichment

Configure in Auto-Collect settings:
- **Auto-Tagging**: Assign topics based on content analysis
- **Entity Extraction**: Identify organizations, people, CVEs
- **Geolocation**: Map to countries/regions
- **Media Bias Detection**: Label source political lean
- **Credibility Scoring**: Rate source trustworthiness

### API Integration

For developers:
- Gather exposes API endpoints for programmatic access
- Retrieve collected articles via `/api/keyword_alerts`
- Trigger manual searches via `/api/check_keywords`
- Manage keyword groups via CRUD endpoints
- See API documentation for details

## Need Help?

### Related Documentation
- [Keyword Monitor Guide](getting-started-keyword-monitor.md) - Managing keywords and groups
- [Article Investigator Guide](getting-started-article-investigator.md) - Analyzing collected articles
- [Explore View Guide](getting-started-explore-view.md) - Working with your intelligence database

### Support
For additional support or to report issues, contact your Aunoo AI administrator or visit the support documentation.

---

*Last updated: 2025-11-25*
