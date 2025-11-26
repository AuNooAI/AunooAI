# Aunoo AI Getting Started Guide

![](.gitbook/assets/0.png)

Welcome to the AunooAI documentation. AunooAI is an open strategic intelligence platform that automatically collects, analyzes, and organizes security news articles to help researchers and foresight professionals to stay informed without information overload.



**Aunoo AI offers:**

* Multisource research, across news, research papers and social media
* Media Bias, Factuality and Credibility ratings&#x20;
* Relevance Scoring
* Quality Control
* Semantic search and analysis
* Foresight visualizations
* Deep Research Agent
* Topic Ontology Agent

### Quick Links

* GitHub Repository: [https://github.com/AuNooAI/AunooAI](https://github.com/AuNooAI/AunooAI)
* Docker Hub: [https://hub.docker.com/repository/docker/aunooai/aunoo-community](https://hub.docker.com/repository/docker/aunooai/aunoo-community)
* Community Support: [https://github.com/AuNooAI/AunooAI/issues](https://github.com/AuNooAI/AunooAI/issues)

***

### Getting Started

#### New User? Start Here

* [Getting Started in 5 Minutes](getting-started-in-5-minutes.md) - Quick setup guide for first-time users
* [Docker Installation](docker-installation-guide.md) - Install using Docker Hub image

#### Installation Options

| Method                                           | Difficulty | Use Case                       |
| ------------------------------------------------ | ---------- | ------------------------------ |
| [Docker Hub Image](docker-installation-guide.md) | Easy       | Most users - pre-built image   |
| Manual Installation                              | Advanced   | Developers, custom deployments |

### User Guides

#### Core Features

* [Gather](collecting-data/) - Automated intelligence collection
  * [Submit Articles](collecting-data/submitting-articles.md) - Manual article submission
* [Explore View](doing-research/) - Main workspace overview
* [Article Investigator](doing-research/article-investigator.md) - Research and filter articles
* [Narrative Explorer](doing-research/narrative-view.md) - Pattern analysis and themes
* [Six Articles](doing-research/six-articles.md) - Executive briefing tool
* [Anticipate ](anticipate-foresight-tools.md) - Strategic foresight dashboards
  * Strategic Recommendations
  * Market Signals & Strategic Risks
  * Consensus Analysis
  * Impact Timeline
  * Future Horizons
* [Operations HQ](operations-hq.md) - System health and monitoring
* [Settings](settings-overview.md) - Configuration and setup

***

### Feature Overview

#### Intelligence Collection (Gather)

* Automated: Keyword-based monitoring across multiple news sources
* Manual: Submit articles via URL or paste content
* Auto-Processing: AI scores relevance and enriches metadata

[→ Learn more about](http://getting-started-gather.md) [collecting news and other data](collecting-data/)

***

#### Intelligence Analysis (Explore)

* Article Investigator: Browse, filter, and manage articles
* Narrative Explorer: AI-powered pattern recognition
* Six Articles: Executive briefing generator

[→ Learn more about Intelligence analysis using AuNoo](doing-research/)

***

#### Strategic Foresight (Anticipate)

* Strategic Recommendations: Near/mid/long-term actions
* Market Signals: Emerging trends and disruptions
* Consensus Analysis: Agreement across sources
* Impact Timeline: Event sequencing
* Future Horizons: Scenario planning

[→ Learn more about strategic foresight in AuNoo](anticipate-foresight-tools.md)

***

#### System Operations

* Operations HQ: System health dashboard
* Settings: Configuration and API keys
* Database: PostgreSQL with pgvector

[→ Learn more about Operations HQ](http://getting-started-operations-hq.md)

***

### Common Tasks

#### How do I...

| Task                           | Guide                                                     | Section               |
| ------------------------------ | --------------------------------------------------------- | --------------------- |
| Install AunooAI                | [Docker Installation](docker-installation-guide.md)       | Quick Start           |
| Add API keys                   | [Settings](settings-overview.md)                          | App Configuration     |
| Set up monitoring topics       | [Settings](settings-overview.md)                          | AI-guided Topic Setup |
| Collect articles automatically | [Gather](collecting-data/)                                | Auto-Collection       |
| Submit articles manually       | [Submit Articles](collecting-data/submitting-articles.md) | URL Submission        |
| Analyze collected articles     | [Article Investigator](doing-research/)                   | Getting Started       |
| Find patterns and themes       | [Narrative Explorer](doing-research/)                     | How to Use            |
| Brief executives               | [Six Articles](doing-research/six-articles.md)            | Getting Started       |
| Forecast future impacts        | [Anticipate](anticipate-foresight-tools.md)               | Future Horizons       |
| Check system health            | [Operations HQ](operations-hq.md)                         | System Health Status  |
| Backup my data                 | [Docker Installation](docker-installation-guide.md)       | Backup Data           |

<br>

***

### Support

#### Community Resources

* GitHub Issues: [https://github.com/AuNooAI/AunooAI/issues](https://github.com/AuNooAI/AunooAI/issues)
* Docker Hub: [https://hub.docker.com/repository/docker/aunooai/aunoo-community](https://hub.docker.com/repository/docker/aunooai/aunoo-community)
* Documentation: You're here!

***

### Contributing

We welcome contributions! Please see our GitHub repository for:

* Contributing guidelines
* Development setup
* Code standards
* Issue templates

Repository: [https://github.com/AuNooAI/AunooAI](https://github.com/AuNooAI/AunooAI)



***

### Architecture

#### Technology Stack

* Backend: Python (Flask/FastAPI)
* Frontend: React + Jinja2 templates
* Database: PostgreSQL with pgvector extension
* AI: OpenAI, Anthropic Claude, Google Gemini
* Deployment: Docker + Docker Compose

#### System Requirements

* Minimum: 4GB RAM, 10GB disk, Docker 20.10+
* Recommended: 8GB RAM, 50GB disk, Docker 24.0+<br>

***

### Version History

See GitHub releases: [https://github.com/AuNooAI/AunooAI/releases](https://github.com/AuNooAI/AunooAI/releases)

***

### License

See: [https://github.com/AuNooAI/AunooAI/blob/main/LICENSE](https://github.com/AuNooAI/AunooAI/blob/main/LICENSE)
