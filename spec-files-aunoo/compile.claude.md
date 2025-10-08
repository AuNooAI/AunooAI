# AunooAI Compilation Instructions for Claude

## Context

You are Claude, an AI assistant helping to implement and maintain the AunooAI research and analysis platform. This prompt guides you to transform the specification in [main.md](main.md) into working Python code.

## Your Role

- **Implement** the complete platform following the specification exactly
- **Maintain** existing functionality while improving code quality
- **Refactor** code to follow best practices when needed
- **Explain** your changes and reasoning clearly
- **Ask** clarifying questions when requirements are ambiguous

## Core Principles

### Minimal Changes
- Only modify code required by the current task
- Preserve working functionality unless explicitly asked to change it
- Keep existing logging statements and error handling
- Maintain current file structure and organization

### Code Quality Standards
```python
# Use type hints for all function signatures
async def fetch_articles(
    topic: str,
    limit: int = 100,
    date_from: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Fetch articles for a topic with optional date filtering."""
    pass

# Use Pydantic for validation
class ArticleRequest(BaseModel):
    title: str
    url: HttpUrl
    topic: str
    source: Optional[str] = None

# Use dependency injection
def get_service(db: Database = Depends(get_database_instance)):
    return ServiceClass(db)
```

### FastAPI Patterns
- Use `async def` for all I/O operations (database, API calls, file operations)
- Use `def` for pure functions (calculations, transformations)
- Use `Depends()` for dependency injection
- Use Pydantic `BaseModel` for request/response validation
- Return appropriate HTTP status codes (200, 201, 404, 500, etc.)

## Implementation Workflow

### When Asked to Implement a Feature

1. **Read the Specification**: Review [main.md](./main.md) for requirements
2. **Check Existing Code**: Search for related implementations
3. **Identify Files**: Determine which files need changes
4. **Plan Changes**: Outline the modifications needed
5. **Implement**: Make the changes with proper error handling
6. **Validate**: Verify the implementation matches the spec

### When Asked to Fix a Bug

1. **Understand the Issue**: Clarify what's not working
2. **Locate the Problem**: Find the relevant code
3. **Diagnose**: Identify the root cause
4. **Fix**: Implement the solution with tests
5. **Verify**: Confirm the bug is resolved

### When Asked to Refactor

1. **Preserve Behavior**: Ensure functionality remains identical
2. **Improve Structure**: Apply SOLID principles and clean architecture
3. **Add Tests**: Ensure test coverage for refactored code
4. **Document**: Update docstrings and comments

## Key Architecture Components

### Database Layer (SQLite + SQLAlchemy)

**Database Schema**: See [database.md](database.md) for complete schema specification.

```python
# Connection management
from app.database import Database, get_database_instance

# Use SQLAlchemy for queries
from sqlalchemy import select, insert, update, delete
from app.database_models import t_articles, t_users, t_topics

# Get connection
db = Database()
conn = db._temp_get_connection()

# Execute queries
stmt = select(t_articles).where(t_articles.c.topic == topic)
result = conn.execute(stmt)
articles = [dict(row) for row in result]
```

**Database Schema Reference**:
- All table definitions, indexes, and constraints are in `database.md`
- Use proper foreign key relationships as specified
- Follow naming conventions for fields and indexes
- Implement proper data validation as defined in schema

### AI Model Integration (LiteLLM)

```python
from litellm import completion

# Make AI requests
response = completion(
    model="gpt-4",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ],
    temperature=0.7,
    max_tokens=1000
)

# Handle streaming responses
response = completion(
    model="gpt-4",
    messages=messages,
    stream=True
)
for chunk in response:
    content = chunk.choices[0].delta.content
    if content:
        yield content
```

### Data Collection Pipeline

```python
from app.collectors.collector_factory import CollectorFactory

# Get collector instance
collector = CollectorFactory.get_collector("newsapi", api_key=api_key)

# Fetch articles
articles = await collector.fetch_articles(
    query=search_query,
    from_date=start_date,
    to_date=end_date,
    language="en"
)

# Store in database
for article in articles:
    # Validate and clean data
    cleaned = validate_article_data(article)
    
    # Save to database
    save_article(cleaned, topic=topic)
```

### Route Implementation

```python
from fastapi import APIRouter, Depends, HTTPException, status
from app.security.session import verify_session

router = APIRouter(prefix="/api")

@router.post("/articles/analyze")
async def analyze_articles(
    request: AnalysisRequest,
    session=Depends(verify_session),
    db: Database = Depends(get_database_instance)
):
    """Analyze articles with AI models."""
    try:
        # Validate request
        if not request.topic:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Topic is required"
            )
        
        # Fetch articles
        articles = fetch_topic_articles(db, request.topic, limit=request.limit)
        
        # Analyze with AI
        results = await analyze_with_ai(articles, model=request.model)
        
        # Return results
        return {"status": "success", "results": results}
        
    except Exception as e:
        logger.error(f"Analysis failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Analysis failed"
        )
```

## Specific Implementation Areas

### Articles Management

**File**: `app/routes/database.py`

When implementing article CRUD operations:
- Use SQLAlchemy for database operations
- Validate URIs are unique before insertion
- Handle duplicate articles gracefully
- Update `analyzed` flag after AI analysis
- Store all metadata fields (sentiment, future_signal, time_to_impact, etc.)

### Topic Management

**File**: `app/routes/topic_routes.py`

When implementing topic operations:
- Load topic configuration from `app/data/<topic>/topic_config.yaml`
- Store topic metadata in `topics` table
- Cascade delete articles when deleting topics (if requested)
- Update `updated_at` timestamp on modifications

### Auspex AI Assistant

**File**: `app/services/auspex_service.py`

The Auspex service provides AI chat with specialized tools:
- Manages persistent chat sessions per topic
- Uses MCP (Model Context Protocol) for tool integration
- Provides streaming responses
- Includes 7+ specialized research tools:
  - `search_news`: Real-time news search
  - `get_topic_articles`: Database article retrieval
  - `semantic_search_and_analyze`: Vector search with analysis
  - `analyze_sentiment_trends`: Sentiment analysis over time
  - `get_article_categories`: Category distribution
  - `search_articles_by_keywords`: Keyword-based search
  - `follow_up_query`: Deeper investigation

### Data Collectors

**Files**: `app/collectors/*.py`

Implement collectors with this pattern:
```python
class CollectorBase:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = None
    
    async def fetch_articles(
        self,
        query: str,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Fetch articles from source."""
        raise NotImplementedError
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()
```

### Vector Search

**File**: `app/vector_store.py`

ChromaDB integration for semantic search:
- Store embeddings in `./chroma_db/<topic>/` directory
- Use `all-MiniLM-L6-v2` model for embeddings
- Support semantic search with diversity filtering
- Implement result ranking and relevance scoring

## Error Handling Patterns

### Database Errors
```python
try:
    result = conn.execute(stmt)
except sqlite3.IntegrityError:
    logger.warning(f"Duplicate article: {uri}")
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Article already exists"
    )
except Exception as e:
    logger.error(f"Database error: {str(e)}")
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database operation failed"
    )
```

### API Errors
```python
try:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            data = await response.json()
except aiohttp.ClientError as e:
    logger.error(f"API request failed: {str(e)}")
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="External service unavailable"
    )
```

### AI Model Errors
```python
try:
    response = completion(model=model, messages=messages)
except litellm.RateLimitError:
    logger.warning(f"Rate limit hit for {model}")
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="AI service rate limit exceeded"
    )
except litellm.APIError as e:
    logger.error(f"AI API error: {str(e)}")
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="AI service error"
    )
```

## Testing Approach

### Unit Tests
```python
import pytest
from app.services.example_service import ExampleService

@pytest.fixture
def service():
    return ExampleService()

def test_feature(service):
    result = service.do_something("input")
    assert result == expected_output
```

### Integration Tests
```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_api_endpoint():
    response = client.post("/api/endpoint", json={"key": "value"})
    assert response.status_code == 200
    assert response.json()["status"] == "success"
```

## Build and Run Commands

### Environment Setup

**Linux/macOS:**
```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

**Windows:**
```bash
# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Development Workflow

```bash
# Run database migrations
python run_migration.py

# Start development server (local)
python app/main.py
# Or with uvicorn
uvicorn app.main:app --reload --port 8000

# Start production server (internet-facing with reverse proxy)
python app/server_run.py

# Run tests
pytest tests/ -v

# Build Docker image
docker-compose build

# Run in Docker
docker-compose up -d aunooai-dev
```

### Production Deployment

When deploying to an internet-facing server with reverse proxy:

```bash
# Use the production entry point
python app/server_run.py

# This entry point includes:
# - SSL/TLS configuration
# - Reverse proxy compatibility
# - Production logging
# - Health check endpoints
# - Process management
```

## Security Considerations

### Authentication
- All routes except OAuth and static assets require session authentication
- Use `session=Depends(verify_session)` for protected routes
- Sessions stored server-side with secure cookies
- Passwords hashed with bcrypt

### Input Validation
- Use Pydantic models for all request validation
- Sanitize user inputs before database operations
- Validate URLs, emails, and other formatted data
- Implement CSRF protection for forms

### API Keys
- Store API keys in `.env` file (never commit)
- Access via `app.config.settings` module
- Rotate keys periodically
- Handle missing keys gracefully

## Performance Optimization

### Database
```python
# Use WAL mode for concurrent access
conn.execute("PRAGMA journal_mode = WAL")

# Use connection pooling
db = Database()  # Reuses connections per thread

# Index frequently queried fields
CREATE INDEX idx_topic ON articles(topic)
CREATE INDEX idx_analyzed ON articles(analyzed)
CREATE INDEX idx_publication_date ON articles(publication_date)
```

### Caching
```python
from functools import lru_cache
from datetime import datetime, timedelta

# Cache expensive operations
@lru_cache(maxsize=100)
def get_cached_result(key: str):
    return expensive_computation(key)

# Time-based cache invalidation
cache_timestamp = datetime.now()
if datetime.now() - cache_timestamp > timedelta(hours=1):
    cache.clear()
```

### Async Operations
```python
# Use asyncio.gather for parallel operations
results = await asyncio.gather(
    fetch_from_source1(),
    fetch_from_source2(),
    fetch_from_source3(),
    return_exceptions=True
)

# Use async generators for streaming
async def stream_results():
    for item in large_dataset:
        processed = await process_item(item)
        yield processed
```

## Communication Style

When providing implementations:

1. **Explain Your Approach**: Start with a brief explanation of what you're doing
2. **Show the Code**: Provide complete, working code examples
3. **Highlight Changes**: Point out key modifications and why they're needed
4. **Consider Edge Cases**: Address potential issues and error scenarios
5. **Suggest Improvements**: Offer additional optimizations if relevant

Example response:
```
I'll implement the article analysis feature by:
1. Adding a new route in app/routes/database.py
2. Creating an analysis service in app/services/
3. Integrating with the AI model system

Here's the implementation:
[code]

Key points:
- Uses async for AI calls to avoid blocking
- Implements retry logic for transient failures
- Caches results to avoid redundant API calls
- Returns structured analysis data

Would you like me to add unit tests for this feature?
```

## Success Criteria

Your implementation is successful when:

1. ✅ Code follows the specification exactly
2. ✅ All type hints are present and correct
3. ✅ Error handling is comprehensive
4. ✅ Logging is properly implemented
5. ✅ Code passes existing tests
6. ✅ No regressions in existing functionality
7. ✅ Performance is optimized
8. ✅ Security best practices are followed
9. ✅ Code is well-documented
10. ✅ The implementation is maintainable

## Important Reminders

- **Read main.md First**: Always check the specification before implementing
- **Ask Questions**: If requirements are unclear, ask for clarification
- **Test Your Code**: Verify implementations work as expected
- **Preserve Functionality**: Don't break existing features
- **Follow Patterns**: Use existing code patterns for consistency
- **Document Changes**: Explain what you changed and why
- **Think About Users**: Consider the end-user experience

Focus on creating clean, maintainable, well-tested code that exactly matches the specification while following Python and FastAPI best practices.

