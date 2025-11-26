# AunooAI - Intelligence Platform

[![License](https://img.shields.io/badge/License-BSL%201.1-blue.svg)](LICENSE)
[![Converts to Apache 2.0](https://img.shields.io/badge/Converts%20to-Apache%202.0-green.svg)](LICENSE.md)
[![Change Date](https://img.shields.io/badge/Change%20Date-2028--11--21-orange.svg)](LICENSE.md)

A FastAPI-based intelligence analysis platform for research, monitoring, and strategic insights.

---

## Quick Start

### Installation

```bash
# 1. Clone the repository
git clone <repository-url>
cd aunoo-ai

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or: .venv\Scripts\activate  # Windows

# 3. Run setup (includes dependencies and database configuration)
python setup.py

# 4. Configure API keys
# Edit .env and add your API keys:
#   - OPENAI_API_KEY
#   - ANTHROPIC_API_KEY
#   - FIRECRAWL_API_KEY
#   - etc.

# 5. Start the application
python app/run.py
```

The application will be available at: http://localhost:10015

---

## Features

- **Research Intelligence**: Automated research and analysis
- **Keyword Monitoring**: Track topics and keywords across news sources
- **Vector Search**: Semantic search using ChromaDB embeddings
- **Analytics Dashboard**: Visualizations and insights
- **Multi-Source Data Collection**: NewsAPI, ArXiv, Bluesky, RSS feeds
- **AI-Powered Analysis**: OpenAI and Anthropic integration
- **User Authentication**: OAuth and session-based auth
- **Database Options**: SQLite (development) or PostgreSQL (production)

---

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
# Server
PORT=10015
DOMAIN=localhost
ENVIRONMENT=development

# Database (configured during setup)
DB_TYPE=sqlite  # or postgresql

# AI Providers (REQUIRED)
OPENAI_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here

# Data Sources
NEWSAPI_KEY=your_key_here
FIRECRAWL_API_KEY=your_key_here

# Optional Services
ELEVENLABS_API_KEY=your_key_here
```

### Database Setup

The setup script (`python setup.py`) will prompt you to choose:

**Option 1: SQLite (Default)**
- Simple file-based database
- Good for development and single-user
- No installation required

**Option 2: PostgreSQL**
- Production-grade database
- Better for concurrent users (50+)
- Automatic installation and configuration

For manual PostgreSQL setup:
```bash
python scripts/setup_postgresql.py
```

See [docs/POSTGRESQL_SETUP.md](docs/POSTGRESQL_SETUP.md) for details.

---

## Project Structure

```
aunoo-ai/
├── app/                          # Main application
│   ├── routes/                   # API endpoints
│   ├── services/                 # Business logic
│   ├── collectors/               # Data collection
│   ├── database.py               # Database interface
│   ├── ai_models.py              # LLM integration
│   └── run.py                    # Application entry point
├── scripts/                      # Setup and utility scripts
├── static/                       # Static assets
├── templates/                    # Jinja2 templates
├── .env                          # Environment configuration
├── requirements.txt              # Python dependencies
└── setup.py                      # Installation script
```

---

## Running the Application

### Development Mode
```bash
python app/run.py
```
- Auto-reload enabled
- Runs on port 10015 (configurable via PORT env var)
- SSL certificate auto-detection

### Production Mode
```bash
export ENVIRONMENT=production
export DISABLE_SSL=true  # If behind reverse proxy
python app/run.py
```

### Docker (Optional)
```bash
# Development
docker-compose up aunooai-dev

# Production
docker-compose up aunooai-prod --profile prod
```

---

## Database Management

### Migrations
```bash
# Run database migrations
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "Description"
```

### Database Tools
```bash
# Analyze database
python app/analyze_db.py

# Inspect schema
python app/utils/inspect_db.py

# Create fresh database
python app/utils/create_new_db.py
```

---

## Development

### Key Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
pytest

# Database analysis
python app/analyze_db.py

# Reindex vector store
python scripts/reindex_chromadb.py

# Initialize defaults
python scripts/init_defaults.py
```

### API Documentation

Once running, visit:
- Swagger UI: http://localhost:10015/docs
- ReDoc: http://localhost:10015/redoc

---

## Architecture

### Core Components

**FastAPI Application**
- Factory pattern: `app.core.app_factory.create_app()`
- Lifespan management for startup/shutdown
- Middleware: HTTPS redirect, sessions, CORS

**Database Layer**
- SQLAlchemy ORM with async support
- Dual support: SQLite and PostgreSQL
- Connection pooling and query optimization
- Vector embeddings via ChromaDB

**Data Collection**
- Factory pattern for collectors
- Sources: NewsAPI, ArXiv, Bluesky, RSS
- Scheduled and on-demand collection

**AI Integration**
- Multi-provider: OpenAI, Anthropic, LiteLLM
- Streaming responses
- Token counting and cost tracking

**Authentication**
- JWT-based sessions
- OAuth integration (Google, GitHub, etc.)
- Session middleware

---

## Advanced Configuration

### PostgreSQL Performance Tuning

Edit `.env`:
```bash
# Light load (<10 users)
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=5

# Medium load (10-50 users)
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=10

# Heavy load (50+ users)
DB_POOL_SIZE=50
DB_MAX_OVERFLOW=20
```

### SSL Configuration

Place certificates in project root:
```bash
cert.pem
key.pem
```

Or configure paths in `.env`:
```bash
CERT_PATH=/path/to/cert.pem
KEY_PATH=/path/to/key.pem
```

To disable SSL (e.g., behind nginx):
```bash
DISABLE_SSL=true
```

---

## Troubleshooting

### Database Connection Issues

The application checks database connectivity on startup:

```bash
python app/run.py
```

**Common errors:**

❌ `Missing PostgreSQL dependencies`
```bash
pip install asyncpg psycopg2-binary
```

❌ `Failed to connect to PostgreSQL`
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Check credentials in .env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=aunoo_db
DB_USER=aunoo_user
DB_PASSWORD=your_password
```

❌ `Port already in use`
```bash
# Change port in .env
PORT=10016

# Or kill existing process
lsof -ti :10015 | xargs kill -9
```

### Missing API Keys

Edit `.env` and add required keys:
```bash
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

### Import Errors

Ensure virtual environment is activated:
```bash
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# Reinstall dependencies
pip install -r requirements.txt
```

---

## Documentation

- [PostgreSQL Setup Guide](docs/POSTGRESQL_SETUP.md)
- [PostgreSQL Quick Reference](README_POSTGRESQL.md)
- [Future Async Migration](../bin/sqlplan/FUTURE_ASYNC_MIGRATION.md)
- [Database Query Progress](../bin/sqlplan/DATABASE_QUERY_FACADE_PROGRESS.md)

---

## Contributing

### Code Style
- Follow PEP 8
- Use type hints where possible
- Document complex functions
- Write tests for new features

### Pull Request Process
1. Create feature branch
2. Make changes with clear commits
3. Run tests
4. Update documentation
5. Submit PR with description

---

## Tech Stack

- **Framework**: FastAPI 0.68+
- **Database**: SQLite / PostgreSQL with SQLAlchemy
- **Vector Store**: ChromaDB
- **AI/LLM**: OpenAI, Anthropic, LiteLLM
- **NLP**: spaCy, NLTK, BERTopic
- **Templates**: Jinja2
- **Server**: Uvicorn (ASGI)
- **Auth**: JWT, OAuth (Authlib)
- **Visualization**: Plotly, Matplotlib

---

## System Requirements

**Minimum:**
- Python 3.12+
- 2GB RAM
- 5GB disk space

**Recommended:**
- Python 3.12+
- 4GB+ RAM
- 10GB+ disk space
- PostgreSQL 14+

---

## License

[Your License Here]

---

## Support

For issues and questions:
- GitHub Issues: [Repository Issues]
- Documentation: `docs/` directory
- Setup Help: Run `python setup.py` for guided setup

---

## Quick Reference

```bash
# Setup
python setup.py

# Start application
python app/run.py

# PostgreSQL setup
python scripts/setup_postgresql.py

# Database migrations
alembic upgrade head

# Reindex vectors
python scripts/reindex_chromadb.py
```

---

## License

Aunoo AI Platform is licensed under the **Business Source License 1.1**.

### What does this mean?

- ✅ **Free to use** for internal business purposes, development, testing, and research
- ✅ **Free to modify** and contribute improvements back to the project
- ✅ **Free to integrate** into non-competing products
- ❌ **Cannot** offer as a competing hosted/managed AI news intelligence service
- ❌ **Cannot** white-label and resell as your own product
- 🔄 **Converts to Apache 2.0** on 2028-11-21 (fully open source after 4 years)

For commercial licensing or to use Aunoo AI in a competing service, contact: licensing@aunoo.ai

See [LICENSE.md](LICENSE.md) for full terms.

---

**Version**: 1.0.0
**Last Updated**: 2024-11-21
**Copyright**: © 2024-present Aunoo Ltd. All rights reserved.
