# Getting Started in 5 Minutes

## What is Aunoo AI?

Aunoo AI is a threat intelligence platform that automatically collects, analyzes, and organizes security news articles. It helps security teams stay informed without drowning in information overload.

## First-Time Setup

### 1. Configure API Keys (2 minutes)

You need API keys for three services:

**AI Provider** (choose one):
- OpenAI (GPT-4) - Best overall
- Anthropic (Claude) - Great for analysis
- Google Gemini - Cost-effective alternative

**News Provider** (choose one):
- NewsAPI - Most popular
- TheNewsAPI - Good alternative
- NewsData.io - Another option

**Web Scraper**:
- Firecrawl - Required for full article text

**How to add keys:**
1. Go to **Settings → AI-guided Topic Setup**
2. Paste your API keys in Step 1
3. Click **Save** on each

**Don't have keys yet?** Get them from:
- OpenAI: https://platform.openai.com/api-keys
- NewsAPI: https://newsapi.org/register
- Firecrawl: https://firecrawl.dev

---

### 2. Set Up Your First Topic (3 minutes)

Topics tell Aunoo what to monitor. Examples: "Ransomware", "APT28", "Log4j vulnerabilities"

**Using the wizard:**
1. Still in **AI-guided Topic Setup**, go to Step 2
2. Enter a topic name: "APT Groups" or "Ransomware Trends"
3. Describe what you want to monitor
4. AI suggests keywords automatically
5. Review keywords in Step 3, click **Save**

**Done!** Aunoo will now monitor news for your topic.

---

## Your First Actions

### Start Collecting Intelligence

**Manual submission** (immediate):
1. Go to **Gather → Submit Articles**
2. Paste 5-10 article URLs (one per line)
3. Click **Analyze Articles**
4. Click **Save All Articles**

**Automated collection** (ongoing):
1. Go to **Gather → Keyword Alerts**
2. Click **Auto-Collect** button
3. Enable auto-collection
4. Set check interval to 12 hours
5. Click **Save**

Now Aunoo will automatically search for articles every 12 hours.

---

### View Your Intelligence

**Explore View** - Your main workspace:
1. Click **Explore** in the sidebar
2. See all collected articles
3. Use filters to narrow by topic, date, source

**Six Articles** - Executive briefing:
1. Click **Explore → Six Articles** tab
2. Click **Write** button
3. Get AI-curated top 6 articles with analysis

---

## What's Next?

### Add More Topics (5 minutes)
1. Go to **Settings → AI-guided Topic Setup**
2. Repeat Step 2-3 for each new topic
3. Typical setup: 5-10 topics covering your threat landscape

### Configure Keywords (10 minutes)
1. Go to **Gather → Manage Keywords**
2. Review auto-generated keyword groups
3. Add specific threat actors, malware names, CVE IDs
4. Enable/disable groups as needed

### Set Up Daily Workflow (ongoing)
Each morning:
1. Check **Gather → Keyword Alerts** for overnight collection
2. Review trending keywords and alert counts
3. Jump to **Explore → Six Articles** for executive brief
4. Deep dive on critical items in Article Investigator

---

## Common Questions

**Q: How do I know if it's working?**
Go to **Operations HQ**. Check "Articles Today" count. If > 0, it's collecting.

**Q: I'm not seeing any articles**
- Check **Operations HQ → System Health** is HEALTHY
- Verify API keys in **Settings → App Configuration → Providers**
- Try manual submission first to test the pipeline

**Q: Too many irrelevant articles**
- Go to **Gather → Auto-Collect**
- Increase "Relevance Threshold" to 70-80
- Refine keywords to be more specific

**Q: Where do I see collected articles?**
**Explore → Article Investigator** shows everything. Use filters to narrow down.

**Q: How do I brief my team?**
**Explore → Six Articles** → Click **Write** → Export as PDF/Markdown

---

## Quick Navigation

| I want to... | Go here... |
|--------------|------------|
| Add articles manually | Gather → Submit Articles |
| See what was collected | Gather → Keyword Alerts |
| Analyze my intelligence | Explore → Article Investigator |
| Brief executives | Explore → Six Articles |
| Find patterns/trends | Explore → Narrative Explorer |
| Add API keys | Settings → App Configuration |
| Create new topics | Settings → AI-guided Topic Setup |
| Check system health | Operations HQ |

---

## Need More Help?

- [Explore View Guide](getting-started-explore-view.md) - Detailed analysis workflow
- [Gather Guide](getting-started-gather.md) - Automated collection setup
- [Settings Overview](getting-started-settings.md) - Configuration details

---

*Last updated: 2025-11-25*
