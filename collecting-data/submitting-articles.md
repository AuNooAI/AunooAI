# Submitting Articles

You can manually submit articles for intelligence that wasn't captured by automated keyword monitoring. Whether you found an important article on social media, received a tip from a colleague, or discovered content behind a paywall, You can submit articles manually to analyze and enrich them with AI-powered insights before adding them to your intelligence database.

***

### How to submit articles manually

Submit Articles provides manual control over your intelligence pipeline:

* URL Analysis: Fetch and analyze articles from any URL
* Bulk Processing: Submit up to 50 URLs at once for batch analysis
* Paste Content: Add articles that can't be accessed via URL (paywalled, private, etc.)
* AI Enrichment: Automatic summarization, entity extraction, and topic classification
* Quality Control: Review AI analysis before saving to your database
* Recent History: Track recently enriched articles in one place

### When to submit articles manually

While the News Firehose automates keyword-based collection, submitting articles is essential for:

* Social Media Finds: Articles shared on Twitter, LinkedIn, threat intel communities
* Analyst Tips: Content recommended by colleagues or partners
* Paywalled Content: Premium sources requiring subscriptions
* Non-News Sources: Blog posts, research papers, vendor advisories
* Manual Curation: High-value content that doesn't match your keywords
* One-Time Searches: Specific topics you don't want to monitor continuously

***

### Getting Started

#### Step 1: Configure Common Settings

Before submitting articles, set your analysis preferences (these apply to all submissions):

<figure><img src="../.gitbook/assets/unknown (15).png" alt=""><figcaption></figcaption></figure>

**Topic**

* Select the primary topic category (e.g., "Ransomware", "APT Groups", "Critical Vulnerabilities")
* This determines how the article is tagged and categorized
* Choose the most specific topic that fits

**AI Model**

* Select which AI model performs the analysis
* Options typically include GPT-4, Claude, or other configured models
* Better models = better analysis, but may cost more per article

**Summary Length**

* 40 words: Ultra-brief (good for scanning)
* 50 words: Default (balanced detail)
* 75 words: Detailed (more context)
* 100 words: Comprehensive (full picture)
* Custom: Specify your own word count

**Summary Voice**

Choose the analysis perspective:

* Business Analyst: Strategic, ROI-focused
* Industry Analyst: Market trends, competitive landscape
* Tech Journalist: Clear, accessible explanations
* Investment Advisor: Financial implications, risk assessment
* Principal Security Engineer: Technical depth, implementation details
* CISO: Executive security perspective, compliance, risk management
* Custom: Write your own voice/persona<br>

_**Tip: For threat intelligence, CISO or Principal Security Engineer voices work best.**_

#### Step 2: Choose Your Input Method

Submit Articles offers two modes:

### Method 1: URL Submission (Most Common)

Best for: Articles accessible online via direct links

#### Single URL

1. Switch to the URL tab (default)
2. Enter one URL in the text area
3. Click Analyze Articles
4. Wait for the AI to fetch and analyze (15-30 seconds)
5. Review the analysis result
6. Click Save Article to add to your database

#### Bulk URLs (Up to 50)

1. Switch to the URL tab
2. Enter multiple URLs, one per line:

`https://example.com/article1`

`https://example.com/article2`

`https://example.com/article3`

_Maximum 50 URLs (system enforced)_

3. Click Analyze Articles
4. Wait for batch processing (30-90 seconds depending on count)
5. Review all results in the Analysis Results table
6. Click Save All Articles to add them to your database

**Notes:**

* URLs are processed in parallel for speed
* Failed fetches (404, paywall, etc.) will show errors
* You can save individual articles or all at once

***

### Method 2: Paste Content

Best for: Premium articles, PDFs, private documents, or content you copied elsewhere

1. Switch to the Paste Content tab
2. Fill in the required fields:

* Article Title: The headline (required)
* Article Source: Publisher name (e.g., "The New York Times", "TechCrunch")
* Publication Date: When it was published (optional but recommended)
* Source URL: Where you found it (required—even if paywalled)
* Article Content: Paste the full text (required)

3. Click Analyze Article
4. Wait for AI analysis&#x20;
5. Review the analysis result
6. Click Save Article to add to your database

***

### Understanding the Analysis Result

After submission, the AI generates a comprehensive analysis:

#### Article Metadata

* Title: Extracted or provided title
* Source: Publisher name
* Publication Date: When it was published
* URL: Original article link
* Topic: Your selected category

#### AI-Generated Summary

* Condensed overview in your chosen length (40-100 words)
* Written in your selected voice/persona
* Captures key points, not just first paragraph
* Useful for quick scanning and executive briefings

***

### Reviewing & Saving Articles

#### Before You Save

Quality Check:

* Does the summary accurately represent the article?
* Are entities correctly identified?
* Is the topic classification appropriate?
* Does the threat level seem right?

Common Issues:

* Inaccurate Summary: Change Summary Voice or Length and resubmit
* Wrong Topic: Go back and select a different topic before resubmitting
* Missing Entities: AI may miss some—you can edit after saving
* Paywall Content: Use "Paste Content" method instead

***

### Recently Enriched Articles Panel

The bottom of the Submit Articles page shows your recent submissions:

#### What's Shown

* Last 10-20 articles you've enriched
* Sorted by submission time (newest first)
* Includes metadata, summary, and analysis

#### Actions

* View Details: Click to expand full analysis
* Edit: Modify topic, tags, or entities
* Delete: Remove from database if saved in error
* Re-analyze: Run analysis again with different settings

***

### Advanced Features

#### Custom Summary Voice

If pre-defined voices don't fit your needs:

1. Select "Custom" in Summary Voice dropdown
2. Enter a custom persona, e.g.:
3. "Military intelligence analyst focused on state-sponsored threats"
4. "SOC analyst prioritizing IOCs and tactical response"
5. "Board member concerned with business continuity and reputation"
6. AI will adapt its analysis to your custom voice

***

### Troubleshooting

#### "Failed to fetch URL"

**Possible Causes:**

* URL is behind paywall or login
* Website blocks automated scraping
* URL is broken (404, 500 error)
* Timeout (very slow website)

**Solutions:**

1. Verify the URL loads in your browser
2. If paywalled, switch to Paste Content method
3. If 404, find the correct URL
4. If scraping blocked, copy content and use Paste Content

***

#### "Analysis result seems off"

**Possible Causes:**

* Wrong topic selected
* Voice/persona doesn't fit content type
* AI model hallucinating or misinterpreting
* Article is low-quality or poorly written

**Solutions:**

1. Click Clear and resubmit with different settings
2. Try a different AI model
3. Change Summary Voice to better fit content
4. For technical content, use "Principal Security Engineer" voice
5. Manually edit after saving if only minor issues

***

#### "URL limit exceeded"

**Possible Causes:**

* Pasted more than 50 URLs
* URLs contain line breaks or extra whitespace

**Solutions:**

1. Count your URLs (one per line)
2. Remove any blank lines
3. Split into multiple batches if > 50 URLs
4. Submit first 50, then submit remaining URLs separately

***

#### "Batch processing stuck"

**Possible Causes:**

* One or more URLs taking very long to fetch
* API rate limits or quotas exceeded
* Background worker overloaded

**Solutions:**

1. Wait 2-3 minutes (some sites are slow)
2. Refresh the page if no progress after 5 minutes
3. Resubmit URLs individually to identify problem URL
4. Check API usage/quotas in settings
5. Contact administrator if persistent

***
