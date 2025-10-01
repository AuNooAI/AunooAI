# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the Application
- **Development**: `python app/run.py` (runs with SSL auto-fallback and reload)
- **Production**: Set `DISABLE_SSL=true` and `ENVIRONMENT=production` in environment
- **Docker Development**: `docker-compose up aunooai-dev` (port 6005)
- **Docker Production**: `docker-compose up aunooai-prod --profile prod` (port 5008)
- **Docker Staging**: `docker-compose up aunooai-staging --profile staging` (port 5009)

### Database Management
- **Run Migrations**: `python run_migration.py`
- **Database Analysis**: `python app/analyze_db.py`
- **Create New Database**: `python app/utils/create_new_db.py`
- **Database Inspection**: `python app/utils/inspect_db.py`

### Common Scripts
- **Setup**: `python scripts/setup.py`
- **Install FFmpeg**: `python scripts/install_ffmpeg.py`
- **Initialize Defaults**: `python scripts/init_defaults.py`
- **Setup News Feed**: `python scripts/setup_news_feed.py`
- **Reindex ChromaDB**: `python scripts/reindex_chromadb.py`

### Testing
- **Run Tests**: Individual test files use `if __name__ == "__main__"` pattern
- **Test Files**: Located in `app/tests/` and `tests/` directories
- **Key Test Areas**: KissQL operators, relevance implementation, SQLite performance

## Architecture Overview

### Application Structure
- **FastAPI Application**: Main app created via `app.core.app_factory.create_app()`
- **Entry Point**: `app/run.py` handles SSL configuration and uvicorn server startup
- **Main Module**: `app/main.py` contains legacy FastAPI setup (being migrated to factory pattern)
- **Router System**: 37+ route modules in `app/routes/` for different features

### Core Components

#### Database Layer
- **Primary Database**: SQLite with SQLAlchemy ORM
- **Database Class**: `app/database.py` - main database interface with connection pooling
- **Query Facade**: `app/database_query_facade.py` - simplified query interface
- **Models**: `app/database_models.py` - SQLAlchemy model definitions
- **Vector Store**: `app/vector_store.py` - ChromaDB integration for embeddings

#### Data Collection System
- **Collector Factory**: `app/collectors/collector_factory.py` - creates data collectors
- **Available Collectors**: NewsAPI, ArXiv, Bluesky, NewsData, TheNewsAPI
- **Base Pattern**: All collectors inherit from `base_collector.py`

#### AI and Analysis
- **AI Models**: `app/ai_models.py` - LLM integration (OpenAI, Anthropic, LiteLLM)
- **Research Engine**: `app/research.py` - core research functionality
- **Analytics**: `app/analytics.py` - data analysis and insights
- **Relevance Assessment**: `app/relevance.py` - content relevance scoring
- **Bulk Research**: `app/bulk_research.py` - batch processing capabilities

#### Key Services
- **Auspex Service**: `app/services/auspex_service.py` - advanced analysis service
- **Chart Service**: `app/services/chart_service.py` - data visualization
- **Feed Service**: `app/services/feed_group_service.py` - content feed management
- **MCP Server**: `app/services/mcp_server.py` - Model Context Protocol server
- **Ontology Service**: `app/services/ontology_service.py` - knowledge organization

### Security and Authentication
- **Auth System**: `app/security/auth.py` - user authentication and authorization
- **OAuth Integration**: `app/security/oauth.py` - third-party authentication
- **Session Management**: `app/security/session.py` - session handling
- **HTTPS Middleware**: `app/middleware/https_redirect.py` - SSL enforcement

### Configuration
- **Settings**: `app/config/settings.py` - application configuration
- **Environment**: `.env` file contains API keys and secrets
- **Config Management**: `app/config/config.py` - runtime configuration handling

### Data Processing Pipeline
1. **Collection**: Data collectors gather content from various sources
2. **Storage**: Raw data stored in SQLite database
3. **Analysis**: Content processed through relevance assessment and AI analysis
4. **Vectorization**: Text content converted to embeddings in ChromaDB
5. **Insights**: Analytics engine generates insights and reports
6. **Presentation**: Results exposed through API routes and web interface

### Key Technologies
- **FastAPI**: Web framework and API
- **SQLite**: Primary database with SQLAlchemy ORM
- **ChromaDB**: Vector database for embeddings
- **Jinja2**: Template engine for web interface
- **Uvicorn**: ASGI server
- **Docker**: Containerization for deployment
- **LiteLLM**: Multi-provider LLM interface
- **NLTK/spaCy**: Natural language processing
- **BERTopic**: Topic modeling
- **Plotly**: Data visualization

### Development Patterns
- **Factory Pattern**: App creation uses factory pattern in `app.core.app_factory`
- **Dependency Injection**: Database and service instances injected via FastAPI dependencies
- **Router Organization**: Features separated into individual router modules
- **Middleware Stack**: Custom middleware for HTTPS, sessions, CORS
- **Async/Await**: Extensive use of async patterns throughout the application
- **Environment-based Configuration**: Different settings for dev/staging/production

### Database Schema
- **Articles**: Core content storage with metadata
- **Topics**: Configurable research topics and keywords
- **Feeds**: Content feed definitions and groupings
- **Users**: Authentication and user management
- **Organizational Profiles**: Entity-specific configurations
- **Vector Embeddings**: Stored in ChromaDB for semantic search