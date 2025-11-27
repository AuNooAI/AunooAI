# Six Articles

Six Articles is your executive briefing tool, designed to transform overwhelming intelligence feeds into a curated, actionable digest for senior leadership. This AI-powered feature selects and analyzes the most strategically relevant articles, providing executive-level insights in a format optimized for time-constrained decision-makers.

***

### What is Six Articles?

Six Articles delivers research-backed intelligence curation:

* Smart Selection: AI identifies the most relevant articles from your data set
* Executive Analysis: Each article includes strategic takeaways, actions, and impact assessments
* Persona-Specific: Tailored insights for CEO, CTO, CISO, or CMO perspectives
* Time-Optimized: 8-12 minute reading experience for morning briefings
* Export-Ready: One-click export to Markdown, HTML, PDF, or audio podcast

### Why "Six" Articles?

The number isn't arbitrary. It's actually backed by research:

* Cognitive Load: Executives can effectively process 5-9 distinct items ([Miller's Law](https://lawsofux.com/millers-law/))
* Diversity: Six articles cover multiple domains without overwhelming
* Time Constraint: Six curated articles take 8-12 minutes to read
* Decision Quality: Research shows decision quality plateaus after 5-7 data points

According to the [Stagwell "Future of News" Study](https://www.stagwellglobal.com/ceos-and-board-directors-view-news-media-as-powerful-advertising-tool-to-influence-key-stakeholders-and-say-brand-safety-is-overapplied-reveals-stagwell-future-of-news-stgw-study), CEOs and board directors view news media as a powerful tool for:

* Forecasting: Identifying emerging trends before they become mainstream
* Risk Management: Early detection of regulatory, competitive, and reputational threats
* Stakeholder Engagement: Understanding how narratives shape perceptions

***

### Getting Started

#### Step 1: Set Your Context

1. Navigate to the Six Articles tab in the main navigation
2. Use the filters at the top of the page:
3. Topics: Select threat intelligence categories relevant to your organization
4. Date Range: Choose your time window (typically last 24-48 hours for daily briefings)

#### Step 2: Configure Settings

Click the Settings dropdown to customize:

**Target Persona**

Choose the executive perspective for analysis:

* CEO: Strategic positioning, market dynamics, organizational impact
* CTO: Technical architecture, innovation, engineering implications
* CISO: Security posture, threat assessment, compliance risks
* CMO: Brand reputation, customer perception, market positioning

**Article Count**

Select how many articles to analyze (3-8 articles):

* 3-4 articles: Quick daily scan for time-constrained executives
* 6 articles: Optimal balance (recommended default)
* 7-8 articles: Deep dive mode for research-intensive roles or weekly digests

#### Step 3: Generate Your Briefing

1. Click the Write button in the toolbar
2. Wait 30-90 seconds while the AI:
3. Analyzes all available articles in your selected range
4. Selects the most strategically relevant articles
5. Generates executive-level insights for each
6. Review the generated briefing

#### Step 4: Explore the Analysis

Each article in your briefing includes:

**Executive Takeaway**

A critical insight summarized in \~15 words—designed for rapid scanning.

**Strategic Relevance**

Why this article matters for your role, with context about business impact and organizational implications.

**Time Horizon**

When the impact will be felt:

* Immediate: Action required this week
* Medium-term: Planning needed within 1-3 months
* Long-term: Strategic positioning for 6+ months

**Risk/Opportunity Assessment**

Clear classification to help prioritize response:

* Risk: Potential threat requiring mitigation
* Opportunity: Strategic advantage to pursue
* Mixed: Both upside and downside considerations

**Executive Actions**

Specific, actionable next steps you can take—not generic recommendations.

**Selection Scores**

Transparency into why this article was chosen:

* Relevance (1-5): Alignment with your topics and persona
* Novelty (1-5): New information vs. already known
* Credibility (1-5): Source trustworthiness
* Representativeness (1-5): How well it represents the broader trend

***

### Advanded Configuration

The Six Articles Config button opens a configuration modal that controls how the AI generates curated executive briefings tailored to specific C-Suite personas.

#### System Prompt

Customize the analyst prompt template that guides article selection and summarization.

**Available Placeholders:**

| Placeholder            | Purpose                              |
| ---------------------- | ------------------------------------ |
| {persona}              | Target persona (CEO, CMO, CTO, CISO) |
| {article\_count}       | Number of articles to select (1-8)   |
| {audience\_profile}    | Organizational profile context       |
| {articles\_summary}    | Corpus of candidate articles         |
| {persona\_priorities}  | Persona-specific priorities          |
| {starred\_instruction} | Instructions for starred articles    |

Actions: Reset to Default, Preview with Sample Data, Validate Template

***

#### Personas

Define characteristics, priorities, and focus areas for each C-Suite persona.

**CEO (Chief Executive Officer)**

* Priorities: Regulation, enterprise adoption, market dynamics
* Risk Appetite: Moderate (default)
* Focus: Business strategy, market positioning, competitive advantage

**CMO (Chief Marketing Officer)**

* Priorities: Market trends, customer behavior, brand impact
* Risk Appetite: High (default)
* Focus: Marketing strategies, customer engagement, brand differentiation

**CTO (Chief Technology Officer)**

* Priorities: Technical breakthroughs, infrastructure, scalability
* Risk Appetite: High (default)
* Focus: Technical architecture, development practices, engineering excellence

**CISO (Chief Information Security Officer)**

* Priorities: Security threats, vulnerabilities, compliance
* Risk Appetite: Low (default)
* Focus: Security risks, compliance requirements, threat mitigation

Each persona is fully customizable with editable priorities, risk appetite (Low/Moderate/High), and focus areas.

***

#### Output Format

Define the JSON schema for Six Articles output.

**Required Fields:**

| Field                | Description                                   |
| -------------------- | --------------------------------------------- |
| title                | Article title with source & date              |
| source               | Publisher name                                |
| date                 | YYYY-MM-DD format                             |
| url                  | Canonical URL                                 |
| executive\_takeaway  | \~15 word summary                             |
| summary              | 2-3 sentence overview                         |
| strategic\_relevance | Why it matters                                |
| time\_horizon        | Immediate/Medium/Long-term                    |
| risk\_opportunity    | risk/opportunity/mixed                        |
| signal\_strength     | weak/moderate/strong                          |
| executive\_action    | Array of recommended actions                  |
| category             | policy/market/tech/workforce/security/society |
| scores               | Relevance/novelty/credibility/reputation      |

***

#### Why Six Articles?

Background on the research-backed design:

The Science:

* Cognitive Load: Executives process 5-9 items effectively (Miller's Law)
* Time: 6 articles takes \~8-12 minutes to review
* Decision Quality: Plateaus after 5-7 data points

Flexibility (1-8 articles):

| Count | Use Case                             |
| ----- | ------------------------------------ |
| 1-2   | Crisis mode – immediate threats only |
| 3-4   | Quick daily scan                     |
| 6     | Optimal balance (recommended)        |
| 7-8   | Deep dive / weekly digest            |

### Key Features

#### Deep Analysis Tools

Each article card provides options for deeper investigation:

* Deep Dive: Multi-source analysis with broader context
* Consensus Analysis: Compare perspectives across multiple sources
* Impact Timeline: Project short/medium/long-term implications
* Ask Auspex: Interactive Q\&A about the article
* SWOT Analysis: Structured strengths/weaknesses/opportunities/threats breakdown
* Scenario Planning: Explore different futures based on the article's themes

#### Export Options

Share your briefing with stakeholders:

* Export Markdown: Plain text format for email or Slack
* Six Articles Markdown: Focused export of just the six articles
* Download HTML (Classic): Simple HTML for archiving
* Download HTML (Enhanced): Styled HTML with branding
* Export to PDF: Professional document for presentations or printing

#### Generate Podcast

_**TIP: You have to add an Elevenlabs API Key to Settings -> Config -> Providers for Podcast Generation**_

Click the Podcast button to:

* Convert your briefing to an AI-narrated audio file
* Listen during commutes or while multitasking
* Choose voice (Rachel by default) and length (90 seconds recommended)

#### Advanced Configuration

Click the Config button for power-user options:

* System Prompt: Customize the AI's analysis instructions
* Persona Profiles: Define custom executive personas beyond the defaults
* Output Schema: Adjust which fields appear in the analysis
* Selection Criteria: Fine-tune how articles are scored and selected

***

### Tips & Tricks

#### Getting the Best Results

* Narrow your topics: Fewer, more focused topics yield better article selection
* Match persona to audience: Use CISO for security teams, CEO for board meetings
* Refresh daily: Run Six Articles each morning for consistent briefings
* Experiment with count: Try 4 articles for speed, 7-8 for depth

#### Time-Saving Strategies

* Use Podcast mode: Listen during commutes or between meetings
* Bookmark the page: Save with your preferred settings in the URL
* Set up a routine: Same time daily (e.g., 7 AM) for consistency
* Export for sharing: Send to leadership before their morning coffee

#### Advanced Usage

* Compare personas: Generate briefings with CEO and CISO personas to see different angles
* Track over time: Export daily briefings to watch trend evolution
* Combine with Narrative View: Use Six Articles for daily scan, Narrative View for deeper patterns
* Custom prompts: Use Config modal to tailor analysis to your organization's specific needs

***

### Understanding Article Selection

The AI selects articles based on a sophisticated scoring system:

#### Selection Criteria

1. Relevance: How well the article matches your topics and persona priorities
2. Novelty: Is this new information or rehashing known facts?
3. Credibility: How trustworthy is the source?
4. Representativeness: Does it represent a broader trend or isolated incident?
5. Strategic Impact: Will this affect business decisions or operations?

#### What Gets Filtered Out

* Duplicate coverage of the same story
* Low-credibility sources
* Off-topic articles (even if in your date range)
* Purely tactical/technical details without strategic implications
* Opinion pieces without actionable intelligence

***

### Troubleshooting

**No articles generated?**

* Verify you have articles loaded for the selected date range and topics
* Try expanding your date range (e.g., last 48 hours instead of last 24)
* Check that at least 3-4 topics are selected
* Click "Load Articles" first in Article Investigator to confirm data availability

**Analysis seems generic or off-target?**

* Switch to a more specific persona (CISO instead of CEO for security focus)
* Narrow your topic selection to 3-5 highly relevant categories
* Use the Config modal to customize the system prompt
* Try regenerating—AI results can vary

**Generation taking too long?**

* Large date ranges (7+ days) with many topics can take 60-90 seconds
* Check your internet connection
* Try reducing the number of articles (6 → 4)
* Refresh the page if it exceeds 2 minutes

<br>

Executive Actions seem too generic?

<br>

* This may indicate limited article quality or generic source material
* Use the Deep Dive tool for more specific recommendations
* Consider customizing the system prompt in Config to emphasize actionability
* Try a different persona—CTO/CISO often yield more specific actions than CEO

<br>

Scores don't make sense?

<br>

* Scores are relative to your current article set, not absolute
* A "3/5 Relevance" may still be highly relevant if few articles match
* Focus on the Strategic Relevance text, not just scores
* If consistently low scores, broaden your topic selection
