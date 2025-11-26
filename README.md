# Aunoo AI Getting Started Guide

![](.gitbook/assets/0.png)

Welcome to the AunooAI documentation. AunooAI is an open strategic intelligence platform that automatically collects, analyzes, and organizes security news articles to help researchers and foresight professionals to stay informed without information overload.

### Quick Links

* GitHub Repository: [https://github.com/AuNooAI/AunooAI](https://github.com/AuNooAI/AunooAI)
* Docker Hub: [https://hub.docker.com/repository/docker/aunooai/aunoo-community](https://hub.docker.com/repository/docker/aunooai/aunoo-community)
* Community Support: [https://github.com/AuNooAI/AunooAI/issues](https://github.com/AuNooAI/AunooAI/issues)

***

### Getting Started

#### New User? Start Here

* [Getting Started in 5 Minutes](https://docs.google.com/document/d/1Rkk_Hz4fXedv-J4-R_h_cTaLuQWJWsBEc6GreckkinM/edit?tab=t.sxyt5rfi4h62) - Quick setup guide for first-time users
* [Docker Installation](https://docs.google.com/document/d/1Rkk_Hz4fXedv-J4-R_h_cTaLuQWJWsBEc6GreckkinM/edit?tab=t.fl0hlirgzr4n) - Install using Docker Hub image

#### Installation Options

| Method                                       | Difficulty | Use Case                       |
| -------------------------------------------- | ---------- | ------------------------------ |
| [Docker Hub Image](http://docker-install.md) | Easy       | Most users - pre-built image   |
| Manual Installation                          | Advanced   | Developers, custom deployments |

User Guides

#### Core Features

* [Explore View](https://docs.google.com/document/d/1Rkk_Hz4fXedv-J4-R_h_cTaLuQWJWsBEc6GreckkinM/edit?tab=t.abxpp4b9z7zq) - Main workspace overview
* [Article Investigator](https://docs.google.com/document/d/1Rkk_Hz4fXedv-J4-R_h_cTaLuQWJWsBEc6GreckkinM/edit?tab=t.5yyas848i3q) - Research and filter articles
* [Narrative Explorer](https://docs.google.com/document/d/1Rkk_Hz4fXedv-J4-R_h_cTaLuQWJWsBEc6GreckkinM/edit?tab=t.n3ewrs97kb62) - Pattern analysis and themes
* [Six Articles](https://docs.google.com/document/d/1Rkk_Hz4fXedv-J4-R_h_cTaLuQWJWsBEc6GreckkinM/edit?tab=t.q4hy9f7fxs4s) - Executive briefing tool

<br>

* [Anticipate (Trend Convergence)](http://getting-started-anticipate.md) - Strategic foresight dashboards

<br>

* Strategic Recommendations
* Market Signals & Strategic Risks
* Consensus Analysis
* Impact Timeline
* Future Horizons

<br>

* [Gather](https://docs.google.com/document/d/1Rkk_Hz4fXedv-J4-R_h_cTaLuQWJWsBEc6GreckkinM/edit?tab=t.j0aln8gij4m0) - Automated intelligence collection

<br>

* [Submit Articles](https://docs.google.com/document/d/1Rkk_Hz4fXedv-J4-R_h_cTaLuQWJWsBEc6GreckkinM/edit?tab=t.5ug2putuf6bb) - Manual article submission

<br>

* [Operations HQ](http://getting-started-operations-hq.md) - System health and monitoring

<br>

* [Settings](https://docs.google.com/document/d/1Rkk_Hz4fXedv-J4-R_h_cTaLuQWJWsBEc6GreckkinM/edit?tab=t.2lemnvp43c4h) - Configuration and setup

<br>

* App Configuration
* AI-guided Topic Setup
* Topic Editor

***

### Feature Overview

#### Intelligence Collection (Gather)

* Automated: Keyword-based monitoring across multiple news sources
* Manual: Submit articles via URL or paste content
* Auto-Processing: AI scores relevance and enriches metadata

<br>

[→ Learn more about Gather](http://getting-started-gather.md)

<br>

***

#### Intelligence Analysis (Explore)

* Article Investigator: Browse, filter, and manage articles
* Narrative Explorer: AI-powered pattern recognition
* Six Articles: Executive briefing generator

<br>

[→ Learn more about Explore View](http://getting-started-explore-view.md)

<br>

***

#### Strategic Foresight (Anticipate)

* Strategic Recommendations: Near/mid/long-term actions
* Market Signals: Emerging trends and disruptions
* Consensus Analysis: Agreement across sources
* Impact Timeline: Event sequencing
* Future Horizons: Scenario planning

<br>

[→ Learn more about Anticipate](http://getting-started-anticipate.md)

<br>

***

#### System Operations

* Operations HQ: System health dashboard
* Settings: Configuration and API keys
* Database: PostgreSQL with pgvector

<br>

[→ Learn more about Operations HQ](http://getting-started-operations-hq.md)

<br>

***

### Common Tasks

#### How do I...

| Task                           | Guide                                                                  | Section               |
| ------------------------------ | ---------------------------------------------------------------------- | --------------------- |
| Install AunooAI                | [Docker Installation](http://docker-install.md)                        | Quick Start           |
| Add API keys                   | [Settings](http://getting-started-settings.md)                         | App Configuration     |
| Set up monitoring topics       | [Settings](http://getting-started-settings.md)                         | AI-guided Topic Setup |
| Collect articles automatically | [Gather](http://getting-started-gather.md)                             | Auto-Collection       |
| Submit articles manually       | [Submit Articles](http://getting-started-submit-articles.md)           | URL Submission        |
| Analyze collected articles     | [Article Investigator](http://getting-started-article-investigator.md) | Getting Started       |
| Find patterns and themes       | [Narrative Explorer](http://getting-started-narrative-view.md)         | How to Use            |
| Brief executives               | [Six Articles](http://getting-started-six-articles.md)                 | Getting Started       |
| Forecast future impacts        | [Anticipate](http://getting-started-anticipate.md)                     | Future Horizons       |
| Check system health            | [Operations HQ](http://getting-started-operations-hq.md)               | System Health Status  |
| Backup my data                 | [Docker Installation](http://docker-install.md)                        | Backup Data           |

<br>

***

### Troubleshooting

#### Installation Issues

See: [Docker Installation - Troubleshooting](http://docker-install.md/#troubleshooting)

#### Application Issues

* Check [Operations HQ](http://getting-started-operations-hq.md) for system health
* Review logs: docker-compose logs -f aunooai
* Verify API keys in [Settings](http://getting-started-settings.md)

#### Feature-Specific Issues

* Gather not collecting: [Gather - Troubleshooting](http://getting-started-gather.md/#troubleshooting)
* Analysis failing: [Anticipate - Troubleshooting](http://getting-started-anticipate.md/#troubleshooting)
* No articles showing: [Article Investigator - Troubleshooting](http://getting-started-article-investigator.md/#troubleshooting)

<br>

***

### Support

#### Community Resources

* GitHub Issues: [https://github.com/AuNooAI/AunooAI/issues](https://github.com/AuNooAI/AunooAI/issues)
* Docker Hub: [https://hub.docker.com/repository/docker/aunooai/aunoo-community](https://hub.docker.com/repository/docker/aunooai/aunoo-community)
* Documentation: You're here!

#### Getting Help

1. Check the relevant guide above
2. Search GitHub Issues for similar problems
3. Open a new issue with:
4. AunooAI version
5. Docker/system info
6. Steps to reproduce
7. Error messages/logs

<br>

***

### Contributing

We welcome contributions! Please see our GitHub repository for:

<br>

* Contributing guidelines
* Development setup
* Code standards
* Issue templates

<br>

Repository: [https://github.com/AuNooAI/AunooAI](https://github.com/AuNooAI/AunooAI)

<br>

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
* Recommended: 8GB RAM, 50GB disk, Docker 24.0+

<br>

***

### Version History

See GitHub releases: [https://github.com/AuNooAI/AunooAI/releases](https://github.com/AuNooAI/AunooAI/releases)

<br>

***

### License

See: [https://github.com/AuNooAI/AunooAI/blob/main/LICENSE](https://github.com/AuNooAI/AunooAI/blob/main/LICENSE)

<br>

***

<br>

Documentation last updated: 2025-11-25

\
<br>

