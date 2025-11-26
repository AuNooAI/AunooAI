# AunooAI Documentation

Welcome to the AunooAI documentation. AunooAI is a threat intelligence platform that automatically collects, analyzes, and organizes security news articles to help security teams stay informed without information overload.

## Quick Links

- **GitHub Repository**: https://github.com/AuNooAI/AunooAI
- **Docker Hub**: https://hub.docker.com/repository/docker/aunooai/aunoo-community
- **Community Support**: https://github.com/AuNooAI/AunooAI/issues

---

## Getting Started

### New User? Start Here

- **[Getting Started in 5 Minutes](getting-started-5-minutes.md)** - Quick setup guide for first-time users
- **[Docker Installation](docker-install.md)** - Install using Docker Hub image

### Installation Options

| Method | Difficulty | Use Case |
|--------|-----------|----------|
| [Docker Hub Image](docker-install.md) | Easy | Most users - pre-built image |
| Manual Installation | Advanced | Developers, custom deployments |

---

## User Guides

### Core Features

- **[Explore View](getting-started-explore-view.md)** - Main workspace overview
  - [Article Investigator](getting-started-article-investigator.md) - Research and filter articles
  - [Narrative Explorer](getting-started-narrative-view.md) - Pattern analysis and themes
  - [Six Articles](getting-started-six-articles.md) - Executive briefing tool

- **[Anticipate (Trend Convergence)](getting-started-anticipate.md)** - Strategic foresight dashboards
  - Strategic Recommendations
  - Market Signals & Strategic Risks
  - Consensus Analysis
  - Impact Timeline
  - Future Horizons

- **[Gather](getting-started-gather.md)** - Automated intelligence collection
  - [Submit Articles](getting-started-submit-articles.md) - Manual article submission

- **[Operations HQ](getting-started-operations-hq.md)** - System health and monitoring

- **[Settings](getting-started-settings.md)** - Configuration and setup
  - App Configuration
  - AI-guided Topic Setup
  - Topic Editor

### Advanced Features

- **[Model Bias Arena](getting-started-model-bias-arena.md)** - Compare AI models and detect bias
- **[Exploratory Analytics](getting-started-exploratory-analytics.md)** - Data visualization and statistical analysis

---

## Documentation by Role

### Security Analyst
Start with these guides:
1. [Getting Started in 5 Minutes](getting-started-5-minutes.md)
2. [Gather - Automated Collection](getting-started-gather.md)
3. [Article Investigator](getting-started-article-investigator.md)
4. [Narrative Explorer](getting-started-narrative-view.md)

**Daily Workflow:**
- Check [Gather](getting-started-gather.md) for overnight collection
- Use [Article Investigator](getting-started-article-investigator.md) for detailed review
- Run [Narrative Explorer](getting-started-narrative-view.md) weekly for patterns

---

### Security Leadership (CISO, Director)
Start with these guides:
1. [Getting Started in 5 Minutes](getting-started-5-minutes.md)
2. [Six Articles](getting-started-six-articles.md)
3. [Anticipate](getting-started-anticipate.md)

**Daily Workflow:**
- Review [Six Articles](getting-started-six-articles.md) briefing (10 min)
- Check [Anticipate Strategic Recommendations](getting-started-anticipate.md) weekly

---

### System Administrator
Start with these guides:
1. [Docker Installation](docker-install.md)
2. [Settings](getting-started-settings.md)
3. [Operations HQ](getting-started-operations-hq.md)

**Responsibilities:**
- Deploy using [Docker](docker-install.md)
- Configure API keys in [Settings](getting-started-settings.md)
- Monitor health via [Operations HQ](getting-started-operations-hq.md)

---

## Feature Overview

### Intelligence Collection (Gather)
- **Automated**: Keyword-based monitoring across multiple news sources
- **Manual**: Submit articles via URL or paste content
- **Auto-Processing**: AI scores relevance and enriches metadata

[→ Learn more about Gather](getting-started-gather.md)

---

### Intelligence Analysis (Explore)
- **Article Investigator**: Browse, filter, and manage articles
- **Narrative Explorer**: AI-powered pattern recognition
- **Six Articles**: Executive briefing generator

[→ Learn more about Explore View](getting-started-explore-view.md)

---

### Strategic Foresight (Anticipate)
- **Strategic Recommendations**: Near/mid/long-term actions
- **Market Signals**: Emerging trends and disruptions
- **Consensus Analysis**: Agreement across sources
- **Impact Timeline**: Event sequencing
- **Future Horizons**: Scenario planning

[→ Learn more about Anticipate](getting-started-anticipate.md)

---

### System Operations
- **Operations HQ**: System health dashboard
- **Settings**: Configuration and API keys
- **Database**: PostgreSQL with pgvector

[→ Learn more about Operations HQ](getting-started-operations-hq.md)

---

## Common Tasks

### How do I...

| Task | Guide | Section |
|------|-------|---------|
| Install AunooAI | [Docker Installation](docker-install.md) | Quick Start |
| Add API keys | [Settings](getting-started-settings.md) | App Configuration |
| Set up monitoring topics | [Settings](getting-started-settings.md) | AI-guided Topic Setup |
| Collect articles automatically | [Gather](getting-started-gather.md) | Auto-Collection |
| Submit articles manually | [Submit Articles](getting-started-submit-articles.md) | URL Submission |
| Analyze collected articles | [Article Investigator](getting-started-article-investigator.md) | Getting Started |
| Find patterns and themes | [Narrative Explorer](getting-started-narrative-view.md) | How to Use |
| Brief executives | [Six Articles](getting-started-six-articles.md) | Getting Started |
| Forecast future impacts | [Anticipate](getting-started-anticipate.md) | Future Horizons |
| Check system health | [Operations HQ](getting-started-operations-hq.md) | System Health Status |
| Backup my data | [Docker Installation](docker-install.md) | Backup Data |

---

## Troubleshooting

### Installation Issues
See: [Docker Installation - Troubleshooting](docker-install.md#troubleshooting)

### Application Issues
- Check [Operations HQ](getting-started-operations-hq.md) for system health
- Review logs: `docker-compose logs -f aunooai`
- Verify API keys in [Settings](getting-started-settings.md)

### Feature-Specific Issues
- **Gather not collecting**: [Gather - Troubleshooting](getting-started-gather.md#troubleshooting)
- **Analysis failing**: [Anticipate - Troubleshooting](getting-started-anticipate.md#troubleshooting)
- **No articles showing**: [Article Investigator - Troubleshooting](getting-started-article-investigator.md#troubleshooting)

---

## Support

### Community Resources
- **GitHub Issues**: https://github.com/AuNooAI/AunooAI/issues
- **Docker Hub**: https://hub.docker.com/repository/docker/aunooai/aunoo-community
- **Documentation**: You're here!

### Getting Help
1. Check the relevant guide above
2. Search GitHub Issues for similar problems
3. Open a new issue with:
   - AunooAI version
   - Docker/system info
   - Steps to reproduce
   - Error messages/logs

---

## Contributing

We welcome contributions! Please see our GitHub repository for:
- Contributing guidelines
- Development setup
- Code standards
- Issue templates

**Repository**: https://github.com/AuNooAI/AunooAI

---

## Architecture

### Technology Stack
- **Backend**: Python (Flask/FastAPI)
- **Frontend**: React + Jinja2 templates
- **Database**: PostgreSQL with pgvector extension
- **AI**: OpenAI, Anthropic Claude, Google Gemini
- **Deployment**: Docker + Docker Compose

### System Requirements
- **Minimum**: 4GB RAM, 10GB disk, Docker 20.10+
- **Recommended**: 8GB RAM, 50GB disk, Docker 24.0+

---

## Version History

See GitHub releases: https://github.com/AuNooAI/AunooAI/releases

---

## License

See: https://github.com/AuNooAI/AunooAI/blob/main/LICENSE

---

*Documentation last updated: 2025-11-25*
