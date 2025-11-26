# Getting Started with Aunoo

Aunoo Community Edition is an Open Strategic Intelligence Platform.

***

### Installing Aunoo Community Edition&#x20;

#### Prerequisites, or things to do before we start

There are some things you need to do and should have ready before you begin setting up AuNoo AI.

\- Docker Desktop (Windows) or Docker (Linux)

\- 4GB RAM minimum, 8GB recommended

***

## AuNoo’s Bring Your Own Keys (BYOK) Model

AuNoo Community uses several different  3rd party services and APIs to work. You will need to bring your own keys. This ensures maximum freedom from vendor lock-in, and allows maximum freedom of choice.

At minimum you will need three API keys for:

1. A newsfeed
2. An AI LLM
3. Firecrawl, for article scraping

### A News Feed

Aunoo is a news analysis tool, and needs access to news. Aunoo currently supports three different providers.

| **Provider**    | **URL**                     | **Free**                                  | **Business**                                                       |
| --------------- | --------------------------- | ----------------------------------------- | ------------------------------------------------------------------ |
| **NewsAPI**     | https://newsapi.org/        | 100 requests / day                        | $449 / month for 250k requests                                     |
| **The NewsAPI** | https://www.thenewsapi.com/ | -                                         | $19 / month for 2,500 requests daily, 25 articles per request      |
| **NewsData.io** | https://newsdata.io/        | 200 credits / day, 10 articles per credit | $199.99 / month for 20,000 credits and 50 articles max per credit. |

Newsdata.io is by far the most generous tier for researchers and casual users. We use [NewsData.io](http://newsdata.io) for our own backend and TheNewsapi for individual tenants.

***

### AI / LLM

Aunoo has been designed to work with a variety of different commercial and open-weights LLM’s.

| AI  | <p>​<a href="https://platform.openai.com/">https://platform.openai.com/</a>​</p><p><a href="https://claude.ai/">https://claude.ai/</a></p><p><a href="https://ai.google.dev/">https://ai.google.dev/</a> </p> | AuNoo utilizes LLMs to automate news analysis.  |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------- |

**\[TIP] What Size LLM do I need?**

While most LLMs will do a decent job of determining the topical content or sentiment of an article, we have found that some smaller models struggled to reliably and consistently generate output. For larger analyses, larger models yield deeper insights.

| **Task**                                                           | **Best Results Models**     |
| ------------------------------------------------------------------ | --------------------------- |
| Enrichment                                                         | OpenAI gpt4o-mini           |
| Auspex                                                             | OpenAI GPT4.1, GPT5, GPT5.1 |
| Anticipate Foresight Storyboards, Explore Narratives and Incidents | OpenAI GPT4.1               |

**\[TIP] Comparing LLM Models**

Under “Settings” -> “Model Bias Arena” you can compare different AI models against benchmark articles to see which ones work well.

A Note on Costs

We used OpenAI GPT-4o-mini throughout most analyses, using around $3 for upwards of 250 articles per month. You can also[ set a limit on costs](https://platform.openai.com/settings/organization/limits) to avoid any unpleasant surprises.

***

### Website Scraping

Most news aggregation feeds provide links to articles, but not always the content. So we use Firecrawl to fetch article content.<br>

* 1 scrape roughly corresponds to 1 article.&#x20;
* A newsletter like the Curious AI uses around 100-1000 per month
* For a larger enterprise monitoring 10 topics, around 10000 - 20000  articles per month is a good estimate.

| Website               | Free Plan                                                            | Hobby                                 | Standard                        |
| --------------------- | -------------------------------------------------------------------- | ------------------------------------- | ------------------------------- |
| https://firecrawl.dev | Firecrawl offers a free plan with a one-time 500 credits (or scrapes | $19/month for 3000 scrapes per month. | $99 / month for 100,000 scrapes |

***

### Getting AuNoo AI

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

**2. Start AunooAI**

```
docker-compose up -d
```

Wait 30-60 seconds for containers to start.

#### 3. Access & Configure

Open browser: [http://localhost:10001](http://localhost:10001)

Default Login:

* Username: admin
* Password: admin123<br>

<figure><img src=".gitbook/assets/unknown (8).png" alt=""><figcaption></figcaption></figure>



⚠️ Change your password after you log on.

You will be asked to create a new password after first logging in.

| At least 8 characters long                 | Must contain at least one number            |
| ------------------------------------------ | ------------------------------------------- |
| Must contain at least one uppercase letter | Must contain at least one special character |

***

### The News Firehose: Getting Data Into Aunoo AI and enriching it

After finishing the onboarding agent, select “Update Now” to kick off collecting the first articles. The News Firehose will start gathering and contextualising articles based on the keywords and news feed the onboarding agent set up.

You can now go and grab a beverage. Depending on how many keywords were set up, this may take a while. If you are running AuNoo as a server, you can also set up “Auto-Collect” to periodically fetch and enrich articles automatically.&#x20;

### Setting up Auto-Collect

The Auto-Collect pipeline automates the process of discovering, downloading, analyzing, and saving news articles based on your Topic. You can access these settings by clicking the “Auto-Collect” button on the News Firehose page.

#### Overview

&#x20; The Auto-Processing Pipeline automatically:

1. Downloads articles from keyword monitoring
2. Scores relevance using AI
3. Applies quality control filters
4. Saves approved articles to your database<br>

By default, we apply the following settings:

1. Enable Auto-collection every 24 hours
2. Search across articles for a maximum of the past 7 days
3. Maximum daily API requests 100
4. Whichever News API key was added during onboarding will be activated
5. Articles will be scored for at least medium relevance.
6. Article output will be quality assessed to ensure we don’t save CAPTCHA, errors or other bad data to the topic dataset.

You will want to configure the most suitable LLM model in the “Default LLM Model” Dropdown

<figure><img src=".gitbook/assets/unknown (9).png" alt=""><figcaption></figcaption></figure>

#### Best Practices

* Start Conservative: Begin with a 24-hour check interval and adjust based on your needs
* Balance API Usage: Use the Daily Request Limit to control costs while getting adequate coverage
* Tune Relevance Threshold: Monitor your statistics and adjust the threshold to find the right balance
* Enable Quality Control: Keep QC enabled to maintain high-quality article collections
* Test First: Use "Test Auto-Ingest" to verify your settings before relying on automated collection
* Multiple Providers: Select multiple news providers for broader coverage<br>

See [Auto-Collect Settings](useful-information.md) for a full list of settings

***
