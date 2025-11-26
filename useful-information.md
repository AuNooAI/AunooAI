# Useful Information

### Topic Features

## A typical topic has the following features:

| <h2>Feature</h2> | <h2>Description</h2>                                                                                                                                                                                                                                                                                                                                                                      | <h2>Examples</h2>                                                                                                                                                  |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Topic Name       | Description of the topic, could be a question, a market, a field or even a group of people.                                                                                                                                                                                                                                                                                               | <ul><li>How big is the cloud repatriation trend?</li><li>How much of AI is hype</li><li>What are our competitors doing?</li></ul><p><br></p><ul><li><br></li></ul> |
| Categories       | A topic is composed of categories. Categorizing your data points will allow us to mine and analyze them better and will help us understand our topics intimately. For example, nuclear power seems critical to powering an AI revolution. Cloud providers earnings results seem relevant to cloud repatriation, and your competitors would also be something you want to track in detail. | <ul><li>AI in Finance</li><li>Cloud Quarterly Earnings</li><li>Ford Motor Company</li></ul>                                                                        |
| Future Signals   | Future signals are indicators for the direction a topic can take. For example, future signals for an AI hype model could be "AI is hype" or "AI is evolving gradually.". In the case of tracking a market, it could be "Market Convergence" or "Market Growth Stalling.". But we can also get more granular, for example "New Hire", or "New Feature."                                    | <ul><li>AI will evolve gradually</li><li>Hypergrowth</li><li>New Customer Acquisition</li></ul><p>​</p>                                                            |
| Sentiments       | <p>We mean the sentiment towards the topic, for example, optimistic towards AI progress.</p><p>The simplest form is: Positive, Neutral, Negative.</p><p>AuNoo AI can go even deeper and ask if the tone of an article is mocking, critical, or hyperbolic.</p>                                                                                                                            | <ul><li>Positive, Neutral, Negative</li><li>Critical, Skeptical</li><li>Hyperbolic, Optimistic, Pessimistic</li></ul><p>​</p>                                      |
| Time to Impact   | In what time frame is the impact is expected in, for example, immediate, short term (3-18 months), mid term (18-60 months), long term (5 years+)?                                                                                                                                                                                                                                         | <ul><li>Immediate</li><li>Short term</li><li>Mid term</li><li>Long term</li></ul><p>​</p>                                                                          |
| Driver Types     | What effect does the data point have on the topic? For example, a lack of progress in the nuclear power supply chain build-out would be an inhibitor for a fast AI revolution. Or a new discovery in developing faster, cheaper GPU memory will act as an accelerator or even catalyst for other AI fields.                                                                               | <ul><li>Accelerator</li><li>Delayer</li><li>Blocker</li><li>Initiator</li><li>Catalyst</li></ul>                                                                   |
|                  |                                                                                                                                                                                                                                                                                                                                                                                           |                                                                                                                                                                    |

***

### Auto-Collect Settings

**Article Collection Settings**

Enable Auto-Collection

Enables or disables automatic article collection. When enabled, the system will automatically check for new articles based on your keyword monitoring rules.<br>

**Check Interval**

Controls how frequently the system checks for new articles matching your keywords:

&#x20; \- Every 15 minutes - For time-critical monitoring

&#x20; \- Every 30 minutes - Frequent updates

&#x20; \- Every hour - Regular monitoring

&#x20; \- Every 2 hours

&#x20; \- Every 4 hours

&#x20; \- Every 6 hours

&#x20; \- Every 8 hours

&#x20; \- Every 12 hours

&#x20; \- Every 24 hours (Default) - Daily digest

**Search Configuration Settings**

**Search Date Range**

Defines how far back in time to search when checking for articles. For example, setting this to 7 means the system will look for articles published in the last 7 days.



**Daily Request Limit**

Maximum number of API requests the system can make per day. This helps control costs and prevents API rate limiting.

**News Providers**

Select which news provider APIs to search across. You can select multiple providers to cast a wider net for article discovery. Available providers are loaded dynamically based on your configuration.

#### Supported News Providers

AuNoo’s “Collectors” get data into the solution. AuNoo currently supports the following Collectors:

| News Feeds                                                                         | Research Feeds                      | Social Media |
| ---------------------------------------------------------------------------------- | ----------------------------------- | ------------ |
| <p><a href="http://newsdata.io">newsdata.io</a></p><p>TheNewsAPi</p><p>NewsAPI</p> | <p>Semantic Scholar</p><p>Arxiv</p> | Bluesky      |

If you’ve completed the onboarding wizard, you will already have a preconfigured topic and keyword group.&#x20;

#### News Collection Settings

**Search Fields**

Controls which fields the keyword search applies to:

* Title - Search article headlines
* Description - Search article summaries
* Content - Search full article text

**Language**

&#x20; Limit article collection to a specific language:

&#x20; \- English, Arabic, German, Spanish, French, Hebrew, Italian, Dutch, Norwegian, Portuguese, Russian, Swedish, Chinese

**Sort By**

Controls how search results are prioritized:

* Newest First - Most recent articles appear first
* Most Relevant - Best keyword matches appear first
* Most Popular - Most-shared/viewed articles appear first

**Results Per Search**

Maximum number of articles to retrieve per keyword search. Higher values collect more articles but consume more API requests.

#### Article Processing Settings

**Enable Auto-Processing**

When enabled, collected articles are automatically analyzed and enriched with AI-powered insights. If disabled, articles are collected but not processed.

**Quality Control**

Enables AI-powered quality review and filtering. Articles are evaluated for relevance, credibility, and quality before being saved.

#### Quality Filters

**Minimum Relevance Score**

Sets the threshold for auto-processing articles. Articles scoring below this relevance level will not be automatically processed.

* Lower values (0-30%) - Accept broader range of articles
* Medium values (30-60%) - Balanced filtering
* Higher values (60-100%) - Only high-relevance articles

#### LLM Configuration

**Default LLM Model**

Selects which AI model to use for relevance scoring and quality control. Available models are loaded from your system configuration.

**Temperature**

Controls AI response consistency:

* Lower values (0-0.5) - More consistent, deterministic results
* Medium values (0.6-1.0) - Balanced creativity and consistency
* Higher values (1.1-2.0) - More varied, creative responses

**Max Tokens**

Controls the maximum length of AI-generated analysis. Higher values allow more detailed analysis but consume more resources.

#### Processing Options

**Save Approved Only**

When enabled, only articles that pass quality control are saved to the database. Articles that fail QC are discarded.

**Max Articles Per Run**

Limits how many articles are processed in each auto-collection batch. This prevents overwhelming your system with too many articles at once.

**Auto-Regenerate Reports**

When enabled, automatically updates the Six Articles report and Dashboard after each auto-collection run completes. This keeps your analytics current without manual intervention.

**Auto-Ingest Statistics**

The settings modal displays real-time statistics:

* Total Processed - Total articles analyzed by the auto-collection system
* Approved - Articles that passed quality control
* Below Threshold - Articles filtered out due to low relevance scores
* Failed QC - Articles that failed quality control checks
