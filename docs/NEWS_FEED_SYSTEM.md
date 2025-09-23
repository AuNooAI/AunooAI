# Daily News Feed System

A Techmeme-inspired daily news feed system that generates minimalist, AI-powered news summaries with bias analysis and factuality assessment.

## Features

### 📰 Two Feed Types

1. **Daily Overview** - Techmeme-style summary page
   - 3-5 top stories with compelling headlines
   - Brief summaries and context
   - Source bias indicators
   - Related article coverage

2. **Six Articles Report** - In-depth analysis
   - Detailed analysis of 6 most interesting articles
   - Executive summary and key themes
   - Left/Center/Right perspective breakdown
   - Comprehensive bias and factuality analysis
   - Related coverage from different sources

### 🎯 Key Capabilities

- **AI-Powered Content Generation** using Auspex service integration
- **Bias Analysis** with Media Bias/Fact Check integration
- **Factuality Assessment** for source credibility
- **Perspective Breakdown** showing different political viewpoints
- **Minimalist Design** inspired by Techmeme's clean aesthetic
- **Markdown Export** for easy sharing and archiving
- **Automated Scheduling** with cron job support
- **Caching System** for performance optimization

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   News Feed     │    │   Auspex AI      │    │   Database      │
│   Routes        │◄──►│   Service        │◄──►│   Articles +    │
│                 │    │                  │    │   Bias Data     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Templates     │    │   News Feed      │    │   Scheduler     │
│   (HTML/CSS)    │    │   Service        │    │   (Cron Jobs)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## Setup and Installation

### 1. Run Setup Script

```bash
python scripts/setup_news_feed.py
```

This will:
- Create necessary database tables
- Generate sample cron job configurations
- Test the system (optional)

### 2. Configure Environment

Ensure you have AI model API keys configured:

```bash
# OpenAI API Key (for GPT models)
OPENAI_API_KEY=your_key_here

# Anthropic API Key (for Claude models)
ANTHROPIC_API_KEY=your_key_here
```

### 3. Set Up Automated Generation (Optional)

Install the generated cron jobs:

```bash
crontab cron_jobs_news_feed.txt
```

Or manually add to your crontab:

```bash
# Daily generation at 6:00 AM
0 6 * * * cd /path/to/project && python -m app.tasks.news_feed_scheduler --action generate

# Weekly cleanup at 2:00 AM Sunday
0 2 * * 0 cd /path/to/project && python -m app.tasks.news_feed_scheduler --action cleanup
```

## Usage

### Web Interface

- **Main Feed**: `http://localhost:8000/news-feed`
- **Overview Only**: `http://localhost:8000/news-feed/overview`
- **Six Articles**: `http://localhost:8000/news-feed/six-articles`

### API Endpoints

#### Generate Full Daily Feed
```http
GET /api/news-feed/daily?date=2024-01-15&topic=technology&model=gpt-4o
```

#### Generate Overview Only
```http
GET /api/news-feed/overview?date=2024-01-15&max_articles=30
```

#### Generate Six Articles Report
```http
GET /api/news-feed/six-articles?topic=ai&max_articles=50
```

#### Get Markdown Format
```http
GET /api/news-feed/markdown/overview?date=2024-01-15
GET /api/news-feed/markdown/six-articles?date=2024-01-15
```

### Manual Generation

Generate feeds manually using the command line:

```bash
# Generate today's feeds for all topics
python -m app.tasks.news_feed_scheduler --action generate

# Generate for specific date
python -m app.tasks.news_feed_scheduler --action generate --date 2024-01-15

# Generate for specific topic
python -m app.tasks.news_feed_scheduler --action generate --topic "artificial intelligence"

# Cleanup old feeds
python -m app.tasks.news_feed_scheduler --action cleanup --cleanup-days 30
```

## Configuration Options

### Request Parameters

- **date**: Target date (YYYY-MM-DD format, defaults to today)
- **topic**: Optional topic filter (e.g., "technology", "politics")
- **max_articles**: Maximum articles to analyze (10-200, default: 50)
- **model**: AI model to use ("gpt-4o", "gpt-4-turbo", "claude-3.5-sonnet")
- **include_bias_analysis**: Include bias and factuality analysis (default: true)

### Default Topics for Automated Generation

The scheduler generates feeds for these topics by default:
- Artificial Intelligence
- Technology
- Politics
- Business
- Science
- Climate
- General (no topic filter)

Customize in `app/tasks/news_feed_scheduler.py`.

## Database Schema

### daily_news_feeds Table

```sql
CREATE TABLE daily_news_feeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    feed_date DATE NOT NULL,
    overview_data TEXT NOT NULL,
    six_articles_data TEXT NOT NULL,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processing_time_seconds REAL,
    model_used TEXT,
    UNIQUE(topic, feed_date)
);
```

## AI Prompts and Generation

The system uses carefully crafted prompts to generate:

### Overview Prompt
- Focuses on Techmeme-style concise headlines
- Emphasizes significance and broad interest
- Includes "why it matters" context
- Maintains journalistic objectivity

### Six Articles Prompt
- Deep analysis with bias perspective breakdown
- Executive summary of key themes
- Comprehensive factuality assessment
- Related article discovery across different sources

## Bias and Factuality Analysis

The system leverages your existing Media Bias/Fact Check integration:

### Bias Categories
- **Left**: Liberal/progressive perspective
- **Left-Center**: Slightly left-leaning
- **Center**: Neutral/centrist
- **Right-Center**: Slightly right-leaning  
- **Right**: Conservative perspective
- **Mixed**: Varied bias depending on topic

### Factuality Ratings
- **Very High**: Excellent factual reporting
- **High**: Good factual reporting
- **Mostly Factual**: Generally reliable
- **Mixed**: Some factual issues
- **Low**: Significant factual problems
- **Very Low**: Poor factual reporting

## Templates and Styling

### Design Philosophy
- **Minimalist**: Clean, uncluttered Techmeme-inspired design
- **Readable**: Optimized typography and spacing
- **Responsive**: Works on desktop and mobile
- **Fast**: Lightweight CSS with no external dependencies

### Template Files
- `templates/news_feed.html` - Main combined interface
- `templates/news_overview.html` - Overview-only page
- `templates/six_articles.html` - Detailed analysis page

### Customization
Modify the CSS in the template files to match your brand:
- Colors and typography
- Layout and spacing
- Bias indicator styling
- Mobile responsiveness

## Performance and Caching

### Caching Strategy
- Generated feeds are cached in the database
- Configurable cache duration (default: 24 hours)
- Automatic cleanup of old cached feeds
- Cache keys include all generation parameters

### Performance Tips
- Use appropriate `max_articles` limits (50-100 for most use cases)
- Enable caching for production use
- Run cleanup regularly to manage database size
- Consider using faster models for overview generation

## Monitoring and Logging

### Logging
The system provides detailed logging for:
- Feed generation success/failure
- Processing times and article counts
- AI model responses and parsing
- Database operations
- Scheduler execution

### Monitoring
Monitor these metrics:
- Generation success rates
- Processing times
- Article counts per topic
- Cache hit rates
- Database size growth

## Troubleshooting

### Common Issues

**No Articles Found**
- Ensure articles are present in your database
- Check date range and topic filters
- Verify article publication dates

**AI Generation Errors**
- Verify API keys are configured
- Check model availability and quotas
- Review AI response parsing in logs

**Template Rendering Issues**
- Check template file paths
- Verify Bootstrap CSS is loaded
- Review browser console for JavaScript errors

**Performance Issues**
- Reduce `max_articles` parameter
- Enable caching
- Check database indices
- Monitor AI model response times

### Debug Mode
Enable debug logging in your application:

```python
import logging
logging.getLogger('app.services.news_feed_service').setLevel(logging.DEBUG)
logging.getLogger('app.routes.news_feed_routes').setLevel(logging.DEBUG)
```

## Future Enhancements

### Planned Features
- RSS/Atom feed export
- Email newsletter integration  
- Social media sharing
- Advanced topic categorization
- Real-time feed updates
- Multi-language support
- Custom bias source integration

### Integration Opportunities
- Slack/Discord bot integration
- API webhooks for external systems
- Mobile app API endpoints
- Third-party news aggregators
- Analytics dashboard integration

## Contributing

When contributing to the news feed system:

1. Follow the existing code patterns
2. Add tests for new features
3. Update documentation
4. Test with various article datasets
5. Verify AI prompt effectiveness
6. Check mobile responsiveness

## License

This news feed system is part of the AunooAI project and follows the same licensing terms.
