# AunooAI - AI-Powered Research and Analysis Platform

## Application Purpose

AunooAI is a strategic foresight and research analysis platform built with FastAPI (Python 3.8+). It collects articles from multiple sources, analyzes them with AI models, and provides intelligent insights through a web interface.

## Configuration

Store application configuration in `.env` file at project root:

```env
# Required API Keys
OPENAI_API_KEY=<your_openai_key>
ANTHROPIC_API_KEY=<your_anthropic_key>
NEWSAPI_KEY=<your_newsapi_key>
THENEWSAPI_KEY=<your_thenewsapi_key>
FIRECRAWL_API_KEY=<your_firecrawl_key>

# Optional API Keys
HUGGINGFACE_API_KEY=<your_huggingface_key>
GEMINI_API_KEY=<your_gemini_key>

# Application Settings
ENVIRONMENT=dev  # dev, staging, or production
SECRET_KEY=<random_secret_key>
DATABASE_DIR=app/data
```

## Development Environment Setup

### Virtual Environment

**Linux/macOS:**
```bash
python -m venv .venv
source .venv/bin/activate
```

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

### Application Entry Points

**Development (local):**
```bash
python app/main.py
```

**Production (internet-facing server with reverse proxy):**
```bash
python app/server_run.py
```

The `server_run.py` entry point is optimized for production deployment with:
- Proper SSL/TLS configuration
- Reverse proxy compatibility
- Production logging settings
- Health check endpoints
- Process management

## Core Capabilities

The platform provides:
- Multi-source article collection (NewsAPI, arXiv, Bluesky, TheNewsAPI)
- AI-powered content analysis with strategic foresight methodology
- Semantic search using ChromaDB vector embeddings
- Interactive AI chat interface (Auspex) with specialized tools
- Real-time keyword monitoring with WebSocket updates
- Automated news feed generation
- News ticker with live updates and hover summaries
- Multi-tenant database architecture

## Architecture

### Core Components

- **FastAPI Backend**: RESTful API with async support
- **SQLite Database**: Multi-tenant database with optimized connection pooling
- **AI Models**: Multi-provider AI model integration (OpenAI, Anthropic, HuggingFace, Gemini)
- **Data Collectors**: Modular collectors for different data sources
- **Web Interface**: Jinja2 templated web UI with Bootstrap styling
- **Vector Store**: ChromaDB for semantic search and embeddings
- **Background Tasks**: Async task processing for data collection and analysis

### Technology Stack

- **Backend**: Python 3.8+, FastAPI, SQLAlchemy
- **Database**: SQLite with WAL mode optimization
- **AI/ML**: LiteLLM, ChromaDB, spaCy
- **Frontend**: HTML5, CSS3, JavaScript, Bootstrap 5
- **Deployment**: Docker, Google Cloud Run, Kubernetes
- **Authentication**: Session-based with OAuth support

## Database Schema

**Complete database specification**: [database.md](database.md)

### Overview

SQLite database with WAL mode for concurrent access. Database file located at `{DATABASE_DIR}/{instance}/fnaapp.db`.

### Core Tables

#### articles
Store collected and analyzed articles from various sources
- **Primary Key**: `uri` (Text, unique identifier from source URL)
- **Key Fields**: title, news_source, publication_date, summary, category, sentiment, future_signal, time_to_impact, topic, analyzed, relevance_score
- **Indexes**: topic, analyzed, publication_date, news_source

#### users  
User authentication and profile management
- **Primary Key**: `id` (Integer, auto-increment)
- **Key Fields**: username, email, hashed_password, is_active, is_admin
- **Indexes**: username (unique), email (unique)

#### topics
Research topics and their configurations  
- **Primary Key**: `name` (Text, topic identifier)
- **Key Fields**: description, keywords, config_json, news_query, paper_query, is_active
- **Indexes**: name+is_active, updated_at

#### keyword_alerts
Keyword monitoring and alerting system
- **Primary Key**: `id` (Integer, auto-increment)  
- **Key Fields**: user_id, keyword, topic, threshold, is_active, trigger_count
- **Indexes**: user_id+keyword, topic+is_active, created_at

#### auspex_chats
AI chat session management
- **Primary Key**: `id` (Integer, auto-increment)
- **Key Fields**: user_id, topic, title, metadata, is_active
- **Indexes**: user_id+topic, created_at

#### auspex_messages
Individual chat messages
- **Primary Key**: `id` (Integer, auto-increment)
- **Key Fields**: chat_id, role, content, model_used, tokens_used
- **Indexes**: chat_id+created_at, role

### Database Operations

Use SQLAlchemy for all database operations:
```python
from app.database import Database, get_database_instance
from app.database_models import t_articles, t_users, t_topics

# Get connection
db = Database()
conn = db._temp_get_connection()

# Query pattern
stmt = select(t_articles).where(t_articles.c.topic == topic_name)
result = conn.execute(stmt)
articles = [dict(row) for row in result]
```

## API Endpoints

### Authentication Routes (`/auth`)
- `POST /login` - User authentication
- `POST /logout` - Session termination
- `POST /register` - User registration
- `GET /profile` - User profile retrieval

### Article Management (`/api`)
- `GET /articles` - Retrieve articles with filtering
- `POST /articles` - Submit new article
- `GET /articles/{uri}` - Get specific article
- `PUT /articles/{uri}` - Update article
- `DELETE /articles/{uri}` - Delete article
- `POST /articles/bulk-analyze` - Bulk analysis

### Topic Management (`/api`)
- `GET /topics` - List all topics
- `POST /topics` - Create new topic
- `PUT /topics/{name}` - Update topic
- `DELETE /topics/{name}` - Delete topic
- `GET /topics/{name}/articles` - Get topic articles

### Research and Analysis (`/api`)
- `POST /research` - Start research process
- `GET /research/{id}` - Get research status
- `POST /chat` - Interactive chat with database
- `GET /analytics` - Get analytics data
- `POST /report` - Generate reports

### Data Collection (`/api`)
- `POST /collect/newsapi` - Collect from NewsAPI
- `POST /collect/arxiv` - Collect from arXiv
- `POST /collect/bluesky` - Collect from Bluesky
- `POST /collect/bulk` - Bulk data collection
- `GET /collect/status` - Collection status

### Keyword Monitoring (`/api`)
- `GET /keyword-monitor` - Monitor keywords
- `POST /keyword-monitor` - Create keyword alert
- `PUT /keyword-monitor/{id}` - Update alert
- `DELETE /keyword-monitor/{id}` - Delete alert
- `GET /keyword-monitor/ws` - WebSocket for real-time updates

### Vector Search (`/api`)
- `POST /vector/search` - Semantic search
- `POST /vector/embed` - Generate embeddings
- `GET /vector/similar` - Find similar articles

### News Ticker (`/api/news-feed`)
- `GET /news-ticker` - Get recent articles for ticker display

## Data Collection Pipeline

### Collectors

#### NewsAPICollector
- Fetches articles from NewsAPI
- Supports date range filtering
- Handles pagination automatically
- Rate limiting and error handling

#### ArxivCollector
- Retrieves academic papers from arXiv
- Supports category filtering
- Extracts metadata and abstracts
- Handles API rate limits

#### BlueskyCollector
- Collects social media posts from Bluesky
- Real-time data streaming
- Content filtering and moderation
- User engagement metrics

### Processing Pipeline

1. **Data Ingestion**: Collectors fetch data from sources
2. **Validation**: Validate data format and completeness
3. **Deduplication**: Remove duplicate articles
4. **Analysis**: AI-powered content analysis
5. **Storage**: Save to database with metadata
6. **Indexing**: Update search indices and embeddings

## AI Integration

### Model Providers
- **OpenAI**: GPT models for text analysis
- **Anthropic**: Claude models for reasoning
- **HuggingFace**: Open-source models
- **Google**: Gemini models for multimodal analysis

### Analysis Features
- **Content Categorization**: Automatic topic classification
- **Sentiment Analysis**: Emotional tone assessment
- **Future Signal Detection**: Trend identification
- **Bias Assessment**: Content bias evaluation
- **Relevance Scoring**: Content relevance ranking
- **Summary Generation**: Automatic article summarization

### Prompt Management
- Dynamic prompt templates
- Context-aware prompting
- Model-specific optimizations
- A/B testing for prompt effectiveness

## Web Interface

### Dashboard
- System status overview
- Recent activity feed
- Quick access to key features
- Performance metrics

### Article Browser
- Advanced filtering options
- Search functionality
- Bulk operations
- Export capabilities

### Research Interface
- Interactive topic setup
- AI-guided research process
- Real-time progress tracking
- Result visualization

### Analytics Dashboard
- Content analysis charts
- Trend visualization
- Performance metrics
- Custom reporting

### News Ticker
- Live scrolling news headlines from active topics
- Hover interactions showing article summaries
- Real-time updates with caching
- Responsive design for all devices
- Integration with existing news feed system

## Configuration

### Environment Variables
- `OPENAI_API_KEY`: OpenAI API key
- `ANTHROPIC_API_KEY`: Anthropic API key
- `NEWSAPI_KEY`: NewsAPI key
- `FIRECRAWL_API_KEY`: Firecrawl API key
- `DATABASE_URL`: Database connection string
- `SECRET_KEY`: Session encryption key
- `ENVIRONMENT`: Deployment environment (dev/staging/prod)

### Multi-Tenant Support
- Instance-based data isolation
- Configurable database paths
- Tenant-specific settings
- Resource allocation per tenant

## Security

### Authentication
- Session-based authentication
- Password hashing with bcrypt
- OAuth integration support
- Admin role management

### Data Protection
- Input validation and sanitization
- SQL injection prevention
- XSS protection
- CSRF token validation

### API Security
- Rate limiting
- API key management
- Request validation
- Error handling without information disclosure

## Deployment

### Docker Support
- Multi-stage builds
- Environment-specific configurations
- Health checks
- Resource limits

### Cloud Deployment
- Google Cloud Run support
- Kubernetes deployment
- Auto-scaling configuration
- Load balancing

### Monitoring
- Application logging
- Performance metrics
- Error tracking
- Health check endpoints

## Development Workflow

### Code Organization
- Modular architecture
- Separation of concerns
- Dependency injection
- Async/await patterns

### Testing
- Unit tests for core functionality
- Integration tests for API endpoints
- Database migration testing
- Performance testing

### Database Management
- Migration system
- Backup and restore
- Performance optimization
- Connection pooling

## Performance Optimization

### Database
- WAL mode for concurrent access
- Connection pooling
- Query optimization
- Index management

### Caching
- In-memory caching
- Redis integration
- API response caching
- Static asset caching

### Async Processing
- Background task queues
- Non-blocking I/O
- Concurrent data processing
- Real-time updates via WebSocket

## Error Handling

### Logging
- Structured logging
- Log levels (DEBUG, INFO, WARNING, ERROR)
- Request tracing
- Performance monitoring

### Exception Management
- Graceful error handling
- User-friendly error messages
- Error reporting and tracking
- Recovery mechanisms

## Extensibility

### Plugin System
- Modular collector architecture
- Custom analysis plugins
- Third-party integrations
- API extensions

### Customization
- Configurable prompts
- Custom analysis templates
- Flexible data models
- Theme and UI customization

## Future Enhancements

### Planned Features
- Advanced ML models
- Real-time collaboration
- Mobile application
- Advanced analytics
- Integration marketplace

### Scalability
- Microservices architecture
- Distributed processing
- Cloud-native deployment
- Auto-scaling capabilities



## New features

### Select Six Articles Article Count
   
  On the @templates/news_feed.html page under Six Articles, add an option for users to
   - Select a target persona
   -- CEO
   -- CMO
   -- CTO
   -- CISO
   -- Custom
   - Select an article count 1-8


## Refactoring
### Simplify podcast generation logic
- we originally had a complex podcast generation system using dia, ffmpeg and elevenlabs
- we removed most of the frontend but still use i under @news_feed.html for six articles
- we have several issues:
-- we can remove dia entirely
-- we want to use the model we configure under the configuration panel for the entire page to generate the script from the six articles selection
-- we want to remove the ffmpeg dependency and just use https://elevenlabs.io/docs/api-reference/text-to-speech/convert
-- we want to allow a user to select the voice where they can select the six artiles persona and count. 
-- we want to allow a user to select the length between 45-150 seconds per articles
