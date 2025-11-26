# Getting Started in 5 Minutes

### What is Aunoo AI?

Aunoo AI is an open strategic intelligence platform that automatically collects, analyzes, and organizes news articles and research reports.&#x20;

### First-Time Setup

The simplest way to install Aunoo for self-hosting is using Docker

#### 1. Download Deployment Files

Windows (PowerShell):

```
mkdir aunooai 
cd aunooai
Invoke-WebRequest -Uri 
"https://raw.githubusercontent.com/AuNooAI/AunooAI/refs/heads/main/docker-compose.yml" 
-OutFile "docker-compose.yml"
```

Linux:

```
mkdir aunooai && cd aunooai

curl -O https://raw.githubusercontent.com/AuNooAI/AunooAI/refs/heads/main/docker-compose.yml
```

#### **2. Start AunooAI**

```
docker-compose up -d
```

Wait 30-60 seconds for containers to start.

***

#### 3. Access & Configure

Open browser: [http://localhost:10001](http://localhost:10001)\
Default Login:<br>

* Username: admin
* Password: admin123

***

#### 4. Configure API Keys

You need API keys for three services:

Don't have keys yet? Get them from:

* LLM - OpenAI: [https://platform.openai.com/api-keys](https://platform.openai.com/api-keys)
* News Feed - The NewsAPI: [https://www.thenewsapi.com/register](https://www.thenewsapi.com/register)&#x20;
* Scraper - Firecrawl: [https://firecrawl.dev](https://firecrawl.dev)

#### How to add keys:

1. AI-guided Topic Setup
2. Paste your API keys in Step 1
3. Click Test and then Save on each

<figure><img src=".gitbook/assets/unknown (5).png" alt=""><figcaption></figcaption></figure>

***

#### 5. Set Up Your First Topic

Topics tell Aunoo what to monitor. Examples: "How strong is the cloud repatriation movement?", "What is APT28 up to?", "How close are we to Quantum Advantage"?

Using the wizard:

1. Still in AI-guided Topic Setup, go to Step 2
2. Enter a topic name: "APT Groups" or "Ransomware Trends"
3. Describe what you want to monitor
4. AI suggests suitable Future Signals, essentially possible scenarios, and suitable categories to break down your topic. When you are happy with the selection, go to Step 3.&#x20;

<figure><img src=".gitbook/assets/unknown (1) (1) (1) (1).png" alt=""><figcaption></figcaption></figure>

6. AI suggests keywords to collect news for your topic automatically

<figure><img src=".gitbook/assets/unknown (2) (1) (1).png" alt=""><figcaption></figcaption></figure>

7. Review keywords in Step 3, click Save

<figure><img src=".gitbook/assets/unknown (3) (1) (1).png" alt=""><figcaption></figcaption></figure>

Done! Aunoo will now monitor news for your topic.

***

### Your First Actions

#### Start Collecting Intelligence

Automated collection (ongoing):<br>

1. Go to Gather → Keyword Alerts
2.  Click Auto-Collect button

    <figure><img src=".gitbook/assets/unknown (4) (1).png" alt=""><figcaption></figcaption></figure>
3. Enable auto-collection
4. Select the LLM you want to use for automated processing
5. Set check interval to 24 hours
6. Click Save

Now Aunoo will automatically search for articles every 24 hours.

Manual submission (immediate):

1. Go to Gather → Submit Articles
2. Paste up to 50 article URLs (one per line)
3. Click Analyze Articles
4. Click Save All Articles

***

#### View Your Intelligence

Explore View - Your main workspace:

1. Click Explore in the sidebar
2. See all collected articles

<figure><img src=".gitbook/assets/unknown (5) (1).png" alt=""><figcaption></figcaption></figure>

3. Use filters to narrow by topic, date, source
4. Drill down into topics by asking Auspex, the AI Futurist.

<figure><img src=".gitbook/assets/unknown (6).png" alt=""><figcaption></figcaption></figure>

***

### What's Next?

#### Add More Topics (5 minutes)

1. Go to Settings → AI-guided Topic Setup
2. Repeat Step 2-3 for each new topic
3. Typical setup: 5-10 topics covering your threat landscape

#### Configure Keywords (10 minutes)

1. Go to Gather → Manage Keywords
2. Review auto-generated keyword groups
3. Add specific threat actors, malware names, CVE IDs
4. Enable/disable groups as needed

<figure><img src=".gitbook/assets/unknown (7).png" alt=""><figcaption></figcaption></figure>

***

### Common Questions

Q: How do I know if it's working?&#x20;

* Go to Operations HQ. Check "Articles Today" count. If > 0, it's collecting.

Q: I'm not seeing any articles

* Check Operations HQ → System Health is HEALTHY
* Verify API keys in Settings → App Configuration → Providers
* Try manual submission first to test the pipeline

Q: Too many irrelevant articles

* Go to Gather → Auto-Collect
* Increase "Relevance Threshold" to 70-80
* Refine keywords to be more specific

Q: Where do I see collected articles?&#x20;

* Explore → Article Investigator shows everything. Use filters to narrow down.

Q: How do I brief my team?&#x20;

* Explore → Six Articles → Click Write → Export as PDF/Markdown

***

### Quick Navigation

| I want to...            | Go here...                       |
| ----------------------- | -------------------------------- |
| Add articles manually   | Gather → Submit Articles         |
| See what was collected  | Gather → Keyword Alerts          |
| Analyze my intelligence | Explore → Article Investigator   |
| Brief executives        | Explore → Six Articles           |
| Find patterns/trends    | Explore → Narrative Explorer     |
| Add API keys            | Settings → App Configuration     |
| Create new topics       | Settings → AI-guided Topic Setup |
| Check system health     | Operations HQ                    |
