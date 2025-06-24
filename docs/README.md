# Article Processing Pipeline

This Python script implements a comprehensive article processing pipeline that:
1. Extracts article data from input files
2. Scrapes article content using BrightData API
3. Assesses article relevance using NLP
4. Enriches articles with additional metadata
5. Saves processed articles to a database/storage

## Setup

1. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Download spaCy model:
```bash
python -m spacy download en_core_web_sm
```

4. Create a `.env` file with required API keys:
```
BRIGHTDATA_API_KEY=your_brightdata_api_key
OPENAI_API_KEY=your_openai_api_key
NEWS_API_KEY=your_news_api_key
```

## Input File Format

The script expects a CSV file (`input_articles.csv`) with the following columns:
- original_id: Unique identifier for the article
- source: Source of the article
- url: URL of the article
- created_on: Publication date (YYYY-MM-DD format)
- language: Article language (default: 'en')
- sentiment: Sentiment score
- geo_lat: Latitude (optional)
- geo_long: Longitude (optional)
- geo_type: Geography type (optional)
- address: Location address (optional)
- author_name: Author's name (optional)
- author_username: Author's username (optional)
- author_avatar: Author's avatar URL (optional)
- author_link: Author's profile link (optional)

## Usage

Run the script:
```bash
python article_processor.py
```

The script will:
1. Read articles from `input_articles.csv`
2. Process each article through the pipeline
3. Save enriched articles to `processed_articles/` directory

## Output

Processed articles are saved as JSON files in the `processed_articles/` directory with:
- Original article metadata
- Scraped content
- Named entities
- Key phrases
- Topic relevance scores
- Keyword matches
- Processing metadata

## Logging

The script uses detailed logging with different levels:
- DEBUG: Detailed processing information
- INFO: General processing status
- WARNING: Non-critical issues
- ERROR: Critical issues that need attention

Logs are printed to stdout with timestamps and log levels.

## Error Handling

The script implements comprehensive error handling:
- Individual article processing errors don't stop the pipeline
- All errors are logged with details
- Failed articles can be reprocessed

## Dependencies

See `requirements.txt` for the complete list of dependencies and their versions.
