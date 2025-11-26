# Getting Started with Submit Articles

## Overview

**Submit Articles** is your manual article ingestion tool—perfect for adding intelligence that wasn't captured by automated keyword monitoring. Whether you found an important article on social media, received a tip from a colleague, or discovered content behind a paywall, Submit Articles lets you analyze and enrich it with AI-powered insights before adding it to your intelligence database.

## What is Submit Articles?

Submit Articles provides manual control over your intelligence pipeline:

- **URL Analysis**: Fetch and analyze articles from any URL
- **Bulk Processing**: Submit up to 20 URLs at once for batch analysis
- **Paste Content**: Add articles that can't be accessed via URL (paywalled, private, etc.)
- **AI Enrichment**: Automatic summarization, entity extraction, and topic classification
- **Quality Control**: Review AI analysis before saving to your database
- **Recent History**: Track recently enriched articles in one place

## Why Use Submit Articles?

While **Gather** automates keyword-based collection, Submit Articles is essential for:

- **Social Media Finds**: Articles shared on Twitter, LinkedIn, threat intel communities
- **Analyst Tips**: Content recommended by colleagues or partners
- **Paywalled Content**: Premium sources requiring subscriptions
- **Non-News Sources**: Blog posts, research papers, vendor advisories
- **Manual Curation**: High-value content that doesn't match your keywords
- **One-Time Searches**: Specific topics you don't want to monitor continuously

## Getting Started

### Step 1: Configure Common Settings

Before submitting articles, set your analysis preferences (these apply to all submissions):

#### Topic
- Select the primary topic category (e.g., "Ransomware", "APT Groups", "Critical Vulnerabilities")
- This determines how the article is tagged and categorized
- Choose the most specific topic that fits

#### AI Model
- Select which AI model performs the analysis
- Options typically include GPT-4, Claude, or other configured models
- Better models = better analysis, but may cost more per article

#### Summary Length
- **40 words**: Ultra-brief (good for scanning)
- **50 words**: Default (balanced detail)
- **75 words**: Detailed (more context)
- **100 words**: Comprehensive (full picture)
- **Custom**: Specify your own word count

#### Summary Voice
Choose the analysis perspective:
- **Business Analyst**: Strategic, ROI-focused
- **Industry Analyst**: Market trends, competitive landscape
- **Tech Journalist**: Clear, accessible explanations
- **Investment Advisor**: Financial implications, risk assessment
- **Principal Security Engineer**: Technical depth, implementation details
- **CISO**: Executive security perspective, compliance, risk management
- **Custom**: Write your own voice/persona

**Tip**: For threat intelligence, **CISO** or **Principal Security Engineer** voices work best.

### Step 2: Choose Your Input Method

Submit Articles offers two modes:

## Method 1: URL Submission (Most Common)

**Best for**: Articles accessible online via direct links

### Single URL
1. Switch to the **URL** tab (default)
2. Enter one URL in the text area
3. Click **Analyze Articles**
4. Wait for the AI to fetch and analyze (15-30 seconds)
5. Review the analysis result
6. Click **Save Article** to add to your database

### Bulk URLs (Up to 20)
1. Switch to the **URL** tab
2. Enter multiple URLs, **one per line**:
   ```
   https://example.com/article1
   https://example.com/article2
   https://example.com/article3
   ```
3. Maximum 20 URLs (system enforced)
4. Click **Analyze Articles**
5. Wait for batch processing (30-90 seconds depending on count)
6. Review all results in the **Analysis Results** table
7. Click **Save All Articles** to add them to your database

**Notes:**
- URLs are processed in parallel for speed
- Failed fetches (404, paywall, etc.) will show errors
- You can save individual articles or all at once

---

## Method 2: Paste Content

**Best for**: Paywalled articles, PDFs, private documents, or content you copied elsewhere

1. Switch to the **Paste Content** tab
2. Fill in the required fields:
   - **Article Title**: The headline (required)
   - **Article Source**: Publisher name (e.g., "The New York Times", "TechCrunch")
   - **Publication Date**: When it was published (optional but recommended)
   - **Source URL**: Where you found it (required—even if paywalled)
   - **Article Content**: Paste the full text (required)

3. Click **Analyze Article**
4. Wait for AI analysis (15-30 seconds)
5. Review the analysis result
6. Click **Save Article** to add to your database

**Why Source URL is required:**
- Tracks provenance for citations
- Prevents duplicate submissions
- Enables link-outs in reports
- If no direct URL exists, use the source homepage or a DOI

---

## Understanding the Analysis Result

After submission, the AI generates a comprehensive analysis:

### Article Metadata
- **Title**: Extracted or provided title
- **Source**: Publisher name
- **Publication Date**: When it was published
- **URL**: Original article link
- **Topic**: Your selected category

### AI-Generated Summary
- Condensed overview in your chosen length (40-100 words)
- Written in your selected voice/persona
- Captures key points, not just first paragraph
- Useful for quick scanning and executive briefings

### Entity Extraction
Automatically identified entities including:
- **Organizations**: Companies, government agencies, threat groups
- **People**: Researchers, executives, threat actors
- **Technologies**: Products, platforms, protocols mentioned
- **Locations**: Countries, cities, regions
- **CVEs/Vulnerabilities**: Specific security flaws referenced

### Topic Classification
- **Primary Topic**: The main category (your selection)
- **Related Topics**: Additional relevant categories (AI-suggested)
- **Tags**: Specific keywords and themes

### Credibility & Bias Assessment
- **Source Credibility Score**: How trustworthy the publisher is
- **Media Bias Rating**: Political lean (left, center, right)
- **Confidence Level**: How certain the AI is about its analysis

### Sentiment Analysis
- **Overall Sentiment**: Positive, negative, or neutral
- **Threat Level**: If applicable (high, medium, low)
- **Urgency**: Time-sensitivity of the information

---

## Reviewing & Saving Articles

### Before You Save

**Quality Check:**
- ✅ Does the summary accurately represent the article?
- ✅ Are entities correctly identified?
- ✅ Is the topic classification appropriate?
- ✅ Does the threat level seem right?

**Common Issues:**
- **Inaccurate Summary**: Change Summary Voice or Length and resubmit
- **Wrong Topic**: Go back and select a different topic before resubmitting
- **Missing Entities**: AI may miss some—you can edit after saving
- **Paywall Content**: Use "Paste Content" method instead

### Saving Options

**Single Article:**
- Review the analysis
- Click **Save Article**
- Article is immediately added to your database
- Appears in Explore View, Gather, and other tools

**Bulk Articles:**
- Review all results in the table
- Uncheck any articles you don't want to save
- Click **Save All Articles** to save checked items
- Or save individual articles one at a time

**Clear & Resubmit:**
- Click **Clear** to remove the current analysis
- Adjust your settings (voice, length, topic)
- Resubmit the same URL/content with new settings

---

## Recently Enriched Articles Panel

The bottom of the Submit Articles page shows your recent submissions:

### What's Shown
- Last 10-20 articles you've enriched
- Sorted by submission time (newest first)
- Includes metadata, summary, and analysis

### Actions
- **View Details**: Click to expand full analysis
- **Edit**: Modify topic, tags, or entities
- **Delete**: Remove from database if saved in error
- **Re-analyze**: Run analysis again with different settings

### Why This Is Useful
- **Quality Control**: Spot-check your recent work
- **Duplicate Prevention**: See if you already submitted something
- **Quick Reference**: Access recently added intel without searching
- **Team Awareness**: See what colleagues submitted (if shared database)

---

## Common Workflows

### Social Media Intelligence Gathering (5 minutes)

**Scenario**: You're monitoring threat intel Twitter accounts and see 5 interesting articles shared.

1. Copy all 5 URLs
2. Open Submit Articles
3. Set Topic: "APT Groups" (or relevant category)
4. Set Voice: "CISO" or "Principal Security Engineer"
5. Paste all 5 URLs in the URL tab (one per line)
6. Click **Analyze Articles**
7. Review batch results
8. Click **Save All Articles**

**Result**: 5 curated articles added to your database in minutes, ready for analysis in Explore View.

---

### Paywalled Content Submission (2 minutes)

**Scenario**: You have a subscription to a premium threat intel service and want to add a critical report.

1. Open the paywalled article in your browser
2. Copy the full text
3. Go to Submit Articles → **Paste Content** tab
4. Fill in:
   - Title: Copy from article
   - Source: Publisher name
   - Publication Date: From article
   - Source URL: The paywalled URL (even though it's not publicly accessible)
   - Article Content: Paste the full text
5. Set Topic: "Threat Intelligence Reports"
6. Set Voice: "CISO"
7. Click **Analyze Article**
8. Review and **Save Article**

**Result**: High-value paywalled content enriched and saved with full AI analysis.

---

### Vendor Advisory Processing (10 minutes)

**Scenario**: Microsoft releases a critical security advisory with 8 related KB articles.

1. Open Submit Articles
2. Set Topic: "Critical Vulnerabilities"
3. Set Voice: "Principal Security Engineer"
4. Set Summary Length: 75 words (need more detail for advisories)
5. Paste all 8 KB article URLs in URL tab
6. Click **Analyze Articles**
7. Wait for batch processing
8. Review results:
   - Check that CVE IDs are extracted correctly
   - Verify threat level is appropriate
   - Ensure affected products are identified
9. Click **Save All Articles**
10. Jump to Explore View → Filter by "Critical Vulnerabilities" to see them

**Result**: Complete vendor advisory set enriched and ready for response planning.

---

### Analyst Tip Follow-Up (3 minutes)

**Scenario**: A colleague sends you a link saying "This looks relevant to our APT28 research."

1. Click the link to verify it's relevant
2. Copy the URL
3. Go to Submit Articles
4. Set Topic: "APT Groups"
5. Paste URL in URL tab
6. Click **Analyze Articles**
7. Review analysis:
   - Confirm it mentions APT28
   - Check summary for relevance
   - Look at entity extraction
8. If relevant: **Save Article**
9. If not: **Clear** and move on

**Result**: Quick validation and enrichment of colleague-provided intelligence.

---

### Weekly Research Round-Up (30 minutes)

**Scenario**: Every Friday, you manually add 10-15 high-quality articles you found during the week.

1. Throughout the week, bookmark/save URLs in a notes app
2. Friday afternoon, open Submit Articles
3. Set Topic: Varies (change for each batch)
4. Group similar articles and submit in batches of 5-10
5. For batch 1 (e.g., 5 ransomware articles):
   - Topic: "Ransomware"
   - Voice: "CISO"
   - Paste 5 URLs
   - Analyze & Save
6. For batch 2 (e.g., 7 vulnerability articles):
   - Topic: "Critical Vulnerabilities"
   - Voice: "Principal Security Engineer"
   - Paste 7 URLs
   - Analyze & Save
7. Review all in Recently Enriched Articles panel
8. Jump to Explore View to see the week's additions

**Result**: Systematic enrichment of manually curated weekly findings.

---

## Tips & Tricks

### URL Submission Tips

**Copy URLs Efficiently:**
- Use browser extensions to copy multiple tabs as URLs
- Use "Copy Link" instead of copying from address bar (avoids tracking parameters)
- Strip URL tracking parameters before submitting (everything after `?utm_`)

**Handle Redirects:**
- Some URLs redirect (bit.ly, t.co, etc.)
- Submit the final URL after following redirects
- Or submit the short URL—AI will follow it automatically

**Check URL Limits:**
- Maximum 20 URLs per batch (hard limit)
- For more, submit multiple batches
- Each URL counts toward your API usage

### Content Pasting Tips

**Get the Full Text:**
- Copy from "reader mode" in browsers for cleaner text
- Avoid copying ads, comments, or navigation elements
- Include byline and date if not auto-detected

**Handling PDFs:**
- Copy text from PDF viewer
- Preserve paragraph breaks (don't paste as one long block)
- Include title and author from PDF metadata

**Formatting:**
- Basic Markdown formatting is preserved (headers, lists)
- HTML is stripped automatically
- Line breaks help readability

### AI Model & Voice Selection

**When to Use Which Model:**
- **GPT-4**: Best overall, balanced cost/quality
- **Claude**: Excellent for long-form content and nuanced analysis
- **Smaller models**: Faster and cheaper for bulk processing

**Voice Recommendations by Content Type:**
- **Threat advisories**: Principal Security Engineer
- **Executive briefings**: CISO or Business Analyst
- **Market analysis**: Industry Analyst or Investment Advisor
- **Technical deep dives**: Principal Security Engineer
- **Policy/compliance**: CISO

**Summary Length by Use Case:**
- **Daily scanning**: 40-50 words
- **Executive briefs**: 50-75 words
- **Research archives**: 75-100 words
- **Detailed analysis**: 100+ words (custom)

### Avoiding Duplicates

**Check Before Submitting:**
- Look at Recently Enriched Articles panel
- Search Explore View for the article title
- System will warn if URL already exists (usually)

**If You Accidentally Duplicate:**
- Delete the duplicate from Recently Enriched Articles
- Or keep both if analysis settings differed significantly

### Batch Processing Strategy

**Group Similar Content:**
- Submit all ransomware articles together with "Ransomware" topic
- Submit all APT articles together with "APT Groups" topic
- Don't mix unrelated articles in one batch (confuses topic classification)

**Optimal Batch Sizes:**
- **5-10 URLs**: Sweet spot for speed and manageability
- **1-3 URLs**: For urgent content that needs immediate review
- **15-20 URLs**: Maximum batch, use only when necessary

**Monitor Progress:**
- Watch for errors in batch results
- Failed URLs don't block successful ones
- Retry failed URLs individually if needed

---

## Troubleshooting

### "Failed to fetch URL"

**Possible Causes:**
- URL is behind paywall or login
- Website blocks automated scraping
- URL is broken (404, 500 error)
- Timeout (very slow website)

**Solutions:**
1. Verify the URL loads in your browser
2. If paywalled, switch to **Paste Content** method
3. If 404, find the correct URL
4. If scraping blocked, copy content and use **Paste Content**

---

### "Analysis result seems off"

**Possible Causes:**
- Wrong topic selected
- Voice/persona doesn't fit content type
- AI model hallucinating or misinterpreting
- Article is low-quality or poorly written

**Solutions:**
1. Click **Clear** and resubmit with different settings
2. Try a different AI model
3. Change Summary Voice to better fit content
4. For technical content, use "Principal Security Engineer" voice
5. Manually edit after saving if only minor issues

---

### "URL limit exceeded"

**Possible Causes:**
- Pasted more than 20 URLs
- URLs contain line breaks or extra whitespace

**Solutions:**
1. Count your URLs (one per line)
2. Remove any blank lines
3. Split into multiple batches if > 20 URLs
4. Submit first 20, then submit remaining URLs separately

---

### "Entities not extracted correctly"

**Possible Causes:**
- Article uses uncommon terminology
- Entities are ambiguous (e.g., "Phoenix" = city or malware?)
- AI model unfamiliar with niche threat actors

**Solutions:**
1. Manually edit entities after saving (in Explore View)
2. Try a different AI model (some excel at entity extraction)
3. Add custom entities in your profile/settings
4. Accept that AI isn't perfect—manual review is normal

---

### "Batch processing stuck"

**Possible Causes:**
- One or more URLs taking very long to fetch
- API rate limits or quotas exceeded
- Background worker overloaded

**Solutions:**
1. Wait 2-3 minutes (some sites are slow)
2. Refresh the page if no progress after 5 minutes
3. Resubmit URLs individually to identify problem URL
4. Check API usage/quotas in settings
5. Contact administrator if persistent

---

### "Can't save article - duplicate error"

**Possible Causes:**
- Article already exists in database (same URL)
- URL redirects to previously saved article

**Solutions:**
1. Check Explore View to see if it's already there
2. If truly a duplicate, skip saving
3. If URL differs but content same, save anyway (system allows)
4. Delete old version if new analysis is better

---

## Best Practices

### For Daily Use

**Establish a Routine:**
- Check threat intel Twitter/feeds in morning
- Submit 3-5 key articles via Submit Articles
- Review analysis before saving (don't auto-trust AI)
- Jump to Explore View to read full articles

**Use Consistent Settings:**
- Same topic categories as your team
- Same voice/persona for consistency
- Same summary length unless content demands more

**Quality Over Quantity:**
- Don't submit everything—curate
- 5 high-quality articles > 20 mediocre ones
- If it doesn't add value, don't submit

### For Team Collaboration

**Coordinate Coverage:**
- Divide responsibility by topic or source
- One analyst monitors social media, another monitors vendor sites
- Share "Recently Enriched" for awareness

**Standardize Settings:**
- Agree on voice/persona per topic
- Agree on summary length
- Use consistent topic categorization

**Document Sources:**
- Always include Source URL (even for pasted content)
- Add notes in article metadata about provenance
- Track where high-value content comes from

### For Research Projects

**Create Dedicated Workflows:**
- Submit all project-related articles with consistent topic tag
- Use custom voice tailored to project goals
- Export enriched articles for project reports

**Maintain Research Archives:**
- Submit articles even if not immediately useful (for future reference)
- Use detailed summary length (75-100 words) for archival
- Tag with project-specific keywords

**Track Down Footnotes:**
- When reading research, submit cited articles
- Build comprehensive background on topics
- Use Explore View to see connections

### For Compliance & Audit

**Document Everything:**
- Always include Source URL for citations
- Preserve publication dates
- Note who submitted (automatic in system logs)

**Avoid Copyright Issues:**
- Don't copy/paste entire paywalled articles for public sharing
- Use summaries for internal use only
- Link to original sources in reports

**Track Provenance:**
- Use Recently Enriched panel to audit recent submissions
- Export metadata for compliance records
- Maintain chain of custody for critical intelligence

---

## Advanced Features

### Custom Summary Voice

If pre-defined voices don't fit your needs:

1. Select "Custom" in Summary Voice dropdown
2. Enter a custom persona, e.g.:
   - "Military intelligence analyst focused on state-sponsored threats"
   - "SOC analyst prioritizing IOCs and tactical response"
   - "Board member concerned with business continuity and reputation"

3. AI will adapt its analysis to your custom voice

### Integration with Other Tools

**Submit Articles → Explore View:**
- All saved articles appear in Explore View immediately
- Filter by today's date to see just your submissions
- Use Article Investigator to review in detail

**Submit Articles → Six Articles:**
- Manually submitted articles are eligible for Six Articles briefings
- High-quality submissions often rank higher in relevance
- Use to ensure critical content appears in executive briefs

**Submit Articles → Gather:**
- Submitted articles can trigger new keyword groups
- If an article matches existing keywords, it appears in Gather
- Use to seed keyword monitoring with known good content

### API Access

For developers or power users:
- Submit articles programmatically via API
- Automate bulk submissions from RSS feeds
- Integrate with SIEM or ticketing systems
- See API documentation for endpoints and authentication

---

## Need Help?

### Related Documentation
- [Gather Guide](getting-started-gather.md) - Automated keyword collection
- [Explore View Guide](getting-started-explore-view.md) - Analyzing your intelligence database
- [Article Investigator Guide](getting-started-article-investigator.md) - Detailed article review

### Support
For additional support or to report issues, contact your Aunoo AI administrator or visit the support documentation.

---

*Last updated: 2025-11-25*
