---
description: Getting Started with the News Firehose under “Gather”
---

# Collecting Data

The News Firehose is your automated intelligence collection system. This powerful tool monitors keywords across multiple news providers, automatically collects matching articles, and surfaces emerging trends before they become mainstream threats.

Think of the News Firehose as your 24/7 intelligence collector, constantly scanning the horizon for signals that matter to your organization.

***

### How does the News Firehose work?

The News Firehose automates the intelligence collection process:

* Keyword Monitoring: Track specific threats, actors, technologies, or topics
* Multi-Source Collection: Search across multiple news providers simultaneously
* Auto-Processing Pipeline: Automatically download, score, and approve relevant articles
* Emerging Trends: Visualize growth patterns and detect breakout stories
* Smart Alerts: Group related articles by topic and keyword clusters

***

### Key Concepts

#### Keyword Groups

Keywords are organized into groups by topic (e.g., "APT28", "Ransomware Trends", "Log4j"). Each group can contain multiple related keywords and tracks its own collection statistics.

#### Auto-Processing Pipeline

When enabled,the News Firehose automatically:

1. Searches news providers based on your keywords
2. Downloads matching articles
3. Scores relevance using AI
4. Filters low-quality or irrelevant content

Saves approved articles to your intelligence database

***

#### Emerging Trends Overview

A visual dashboard showing:

* Growth Status: Accelerating, stable, or declining trends
* Sparkline Charts: Article volume over time
* Alert Counts: Number of unread articles per group

Tags: Keywords that triggered the match

***

### Getting Started

#### Step 1: Set Up Your Keywords

You can skip this step if you’ve used the Onboarding Agent<br>

1. Click Manage Keywords in the toolbar
2. This takes you to the Keyword Monitor page where you can:
3. Create new keyword groups by topic
4. Add keywords to existing groups
5. Configure search operators (AND, OR, NOT)
6. Enable/disable specific keyword groups<br>

Tip: Start with 3-5 high-priority threat topics and expand from there.

#### Step 2: Configure Auto-Collection

1. **Click Auto-Collect in the toolbar**
2. **Configure your collection settings:**

* Enable Auto-Collection: Turn on automated searching
* Check Interval: How often to search (every 15 min to 24 hours)
* Search Date Range: How far back to look (1-30 days)
* News Providers: Select which sources to monitor
* Search Fields: Where to look (title, description, content)

3. Set up the Auto-Processing Pipeline:

* Relevance Threshold: Minimum score to auto-approve (0-100)
* Auto-Tagging: Automatically assign topics to articles
* Enrichment: Add entity extraction and geolocation
* Quality Control: Filter duplicates and low-credibility sources

_By default, we apply the following settings_

* _Enable Autocollection every 24 hours_
* _Search across articles for a maximum of the past 7 days_
* _Maximum daily API requests 100_
* _Whichever News API key was added during onboarding will be activated_
* _Articles will be scored for at least medium relevance._
* _Article output will be quality assessed to ensure we don’t save CAPTCHA, errors or other bad data to the topic dataset._

You will want to configure your LLM model of choice in the “Default LLM Model” Dropdown<br>

4. **Click Save Settings**

#### <sup>Step 3: Enable Auto-Processing</sup>

1. Toggle the Auto-Processing switch in the top-right corner to ON
2. Gather will now run automatically based on your check interval
3. Monitor the status ticker to see:
4. Last search time
5. Processing job count (if active)
6. Any errors or issues

#### Step 4: Manual Updates (Optional)

* Click Update Now to immediately search all active keyword groups
* Use this for breaking news or when you can't wait for the next scheduled run
* Monitor the progress in the status badge

***

### Understanding the Dashboard

#### Emerging Trends Table

Each row represents a keyword group with the following columns:

**Status Badge**

* Accelerating: Article volume increasing rapidly
* Stable: Steady flow of articles
* Declining: Fewer articles than before
* No Data: No recent articles found

**Emerging Trend**

* Group Name: Your keyword group (e.g., "APT28 Campaigns")
* Topic: The assigned topic category

**Growth Chart (Sparkline)**

* Visual representation of article volume over the last 7-14 days
* Helps identify sudden spikes or sustained growth
* Hover to see approximate counts

**Size (Alert Count)**

* X alerts: Number of unread articles in this group
* Click to expand and view the articles

**Tags & Enrichment**

* Keyword Tags: Which keywords triggered the match
* Shows first 3-5 keywords, expandable to see all

**Detected**

* When the trend was first detected
* Helps prioritize breaking vs. ongoing stories

***

#### Article Cards

**Each article shows:**

* Title & Source: Article headline and publisher
* Published Date: When the article was published
* Summary: AI-generated or source-provided summary
* Matched Keywords: Which keywords triggered this alert

**Actions:**

* **Mark as Read:** Remove from unread count
* **Analyze:** Run deep analysis or add to investigation
* **Archived View:** View on [Archive.is](http://archive.is)
* **Bypass Paywall:** View on 12ft.io

***

### Key Features

#### Submit Articles

Manually add articles that weren't caught by keyword monitoring:

* Click Submit Articles
* Enter article URL or paste text
* Assign topic and tags
* Article is processed like auto-collected content

#### Update Now

Immediately trigger a search across all active keyword groups:

* Click Update Now
* Bypass the scheduled check interval
* Useful for breaking news or time-sensitive threats
* Monitor progress via status badge

#### Auto-Collect Settings

Fine-tune your automated collection:

**Article Collection**

* Enable/Disable: Turn auto-collection on/off
* Check Interval: 15 minutes to 24 hours
* Search Date Range: 1-30 days lookback
* Daily Request Limit: API rate limiting (default 100)

**Search Configuration**

* News Providers: Select multiple sources (NewsAPI, GoogleNews, etc.)
* Search Fields: Title, description, and/or content
* Language: Filter by language (English, Russian, Chinese, etc.)
* Sort By: Newest first or most relevant

**Auto-Processing Options**

* Relevance Threshold: Minimum score (0-100) to auto-approve
* Auto-Tagging: Automatically assign topics based on content
* Entity Extraction: Identify organizations, people, locations
* Duplicate Detection: Filter out redundant articles
* Quality Control: Block low-credibility sources

#### Manage Keywords

Jump to the [Keyword Monitor](https://docs.google.com/document/d/1Rkk_Hz4fXedv-J4-R_h_cTaLuQWJWsBEc6GreckkinM/edit?tab=t.yq9zz97d4deg) page to:

* Create new keyword groups
* Edit existing keywords
* Enable/disable groups
* Test keyword queries before saving

#### Cancel Task

Stop a running background collection job:

* Appears when a task is in progress
* Click Cancel Task to stop immediately
* Useful if you triggered a search by mistake

***

#### Optimizing Auto-Collection

**Start Conservative**

* Begin with 6-12 hour check intervals
* Use moderate relevance thresholds (60-70)
* Select 2-3 high-quality news providers
* Monitor for a week, then adjust

**Reduce Noise**

* Increase relevance threshold if too many low-value articles
* Enable duplicate detection
* Exclude specific sources in provider settings
* Refine keywords to be more specific

**Increase Coverage**

* Add more news providers
* Lower relevance threshold slightly (50-60)
* Expand search date range
* Add more keyword variations

#### Reading the Dashboard

Prioritize by Status

1. Accelerating trends (potential breaking news)
2. High alert counts (lots of new content)
3. Groups you haven't checked in 24+ hours

**Use Sparklines**

* Sharp spikes = breaking story
* Sustained growth = ongoing campaign
* Flat lines = stable monitoring (expected for some topics)

**Manage Alert Overload**

* Bulk select and mark as read
* Delete obvious noise immediately
* Use the "Analyze Selected" feature for batch processing
* Consider disabling noisy keyword groups

***

### Troubleshooting

#### "No articles appearing after Update Now"

**Possible Causes:**

* Keywords too specific (no matching articles exist)
* Date range too narrow (expand to 7-14 days)
* News providers not returning results (check provider status)
* API rate limits exceeded (wait or increase daily limit)

**Solutions:**

1. Check Manage Keywords to verify keywords are enabled
2. Click Auto-Collect to verify news providers are selected
3. Try broader keywords temporarily to test
4. Check error messages in the status ticker

***

#### "Too many irrelevant articles"

**Possible Causes:**

* Keywords too broad (matching unrelated content)
* Relevance threshold too low (auto-approving everything)
* Search fields including noisy content (description/content)

**Solutions:**

1. Increase relevance threshold in Auto-Collect settings (try 70-80)
2. Make keywords more specific (add context or operators)
3. Enable duplicate detection
4. Search title only (uncheck description/content)
5. Review and delete noisy articles, then adjust keywords

***

#### "Auto-processing not running"

**Possible Causes:**

* Auto-Processing toggle is OFF
* Check interval too long (24 hours)
* Background worker not running (server issue)

**Solutions:**

1. Verify the Auto-Processing toggle is ON (top-right)
2. Click Auto-Collect and verify "Enable Auto-Collection" is checked
3. Check "Last search" time to see if it's running at all
4. Use Update Now to manually trigger (tests the pipeline)
5. Contact administrator if manual updates work but auto doesn't

***

#### "Processing jobs stuck"

**Possible Causes:**

* Large number of articles being processed
* AI scoring taking longer than expected
* Background worker crashed

**Solutions:**

1. Wait 5-10 minutes (large jobs take time)
2. Click Cancel Task to stop the current job
3. Refresh the page and check status
4. Try Update Now again with fewer keyword groups enabled

***

#### "Rate limit exceeded"

**Possible Causes:**

* Too many API requests in 24 hours
* Check interval too frequent (every 15 min)
* Many keyword groups with overlapping searches

**Solutions:**

1. Increase check interval (6-12 hours recommended)
2. Reduce the number of active keyword groups
3. Increase "Daily Request Limit" in Auto-Collect settings
4. Wait 24 hours for rate limit to reset
5. Consider upgrading news provider API tier

***

### Advanced Features

#### Bulk Operations

**Bulk Delete:**<br>

* Select multiple articles with checkboxes
* Click Delete Selected in toolbar
* Quickly clear noise without reviewing each article

**Bulk Analyze:**

* Select articles of interest
* Click Analyze Selected
* Run AI analysis, entity extraction, or classification in batch
