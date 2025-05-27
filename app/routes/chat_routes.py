from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from app.security.session import verify_session
from app.database import Database
from app.ai_models import get_ai_model
from pydantic import BaseModel
import logging
import json
from datetime import datetime, timedelta
from app.analyze_db import AnalyzeDB
from app.vector_store import search_articles as vector_search_articles
from typing import List, Dict

router = APIRouter()
templates = Jinja2Templates(directory="templates")
logger = logging.getLogger(__name__)

# Add this class to define the expected request body
class ChatRequest(BaseModel):
    message: str
    topic: str
    model: str
    limit: int = 50  # Default to 50 if not provided
    conversation_history: List[Dict[str, str]] = []  # Add conversation history

def extract_json_from_response(response: str) -> str:
    """Extract JSON object from LLM response, handling any extra text."""
    try:
        # Try to find JSON object between curly braces
        start = response.find('{')
        end = response.rfind('}') + 1
        if start >= 0 and end > start:
            json_str = response[start:end]
            # Clean up double curly braces
            json_str = json_str.replace('{{', '{').replace('}}', '}')
            # Remove any leading/trailing whitespace
            json_str = json_str.strip()
            logger.debug(f"Cleaned JSON string: {json_str}")
            return json_str
        return response
    except Exception as e:
        logger.error(f"Error extracting JSON: {str(e)}")
        return response

@router.get("/database-chat")
async def chat_page(request: Request, session=Depends(verify_session)):
    return templates.TemplateResponse(
        "database_chat.html",
        {"request": request, "session": session}
    )

@router.post("/api/chat")
async def chat_with_database(
    request: Request,
    chat_request: ChatRequest,
    session=Depends(verify_session)
):
    try:
        db = Database()
        analyze_db = AnalyzeDB(db)
        ai_model = get_ai_model(chat_request.model)

        # Get available options for this topic
        topic_options = analyze_db.get_topic_options(chat_request.topic)

        # Enhanced search strategy: Use both SQL and vector search
        # First, try vector search for semantic understanding
        vector_articles = []
        try:
            # Build metadata filter for vector search
            metadata_filter = {"topic": chat_request.topic}
            vector_results = vector_search_articles(
                query=chat_request.message,
                top_k=100,
                metadata_filter=metadata_filter
            )
            
            # Convert vector results to article format
            for result in vector_results:
                if result.get("metadata"):
                    vector_articles.append({
                        "uri": result["metadata"].get("uri"),
                        "title": result["metadata"].get("title"),
                        "summary": result["metadata"].get("summary"),
                        "category": result["metadata"].get("category"),
                        "sentiment": result["metadata"].get("sentiment"),
                        "future_signal": result["metadata"].get("future_signal"),
                        "time_to_impact": result["metadata"].get("time_to_impact"),
                        "publication_date": result["metadata"].get("publication_date"),
                        "news_source": result["metadata"].get("news_source"),
                        "tags": result["metadata"].get("tags", "").split(",") if result["metadata"].get("tags") else [],
                        "similarity_score": result.get("score", 0)
                    })
            
            logger.debug(f"Vector search found {len(vector_articles)} semantically relevant articles")
            
        except Exception as e:
            logger.warning(f"Vector search failed, falling back to SQL search: {e}")
            vector_articles = []

        # If vector search found good results, use them; otherwise fall back to SQL search
        if len(vector_articles) >= 10:
            # Enhanced selection: Apply diversity and quality filtering
            articles = select_diverse_articles(vector_articles, chat_request.limit)
            total_count = len(vector_articles)
            search_method = "semantic vector search with diversity filtering"
            
            # Format search criteria for display
            search_summary = f"""## Search Method: Enhanced Semantic Search
- **Query**: "{chat_request.message}"
- **Topic Filter**: {chat_request.topic}
- **Search Type**: Vector similarity search using embeddings
- **Results**: Found {total_count} semantically relevant articles
- **Analysis Limit**: {chat_request.limit} articles

## Results Overview
Analyzing the {len(articles)} most semantically similar articles
"""
        else:
            # Fall back to original SQL-based search logic
            # First, let the LLM determine if this is a search request and what parameters to use
            available_options = f"""Available search options:
1. Categories: {', '.join(topic_options['categories'])}
2. Sentiments: {', '.join(topic_options['sentiments'])}
3. Future Signals: {', '.join(topic_options['futureSignals'])}
4. Time to Impact: {', '.join(topic_options['timeToImpacts'])}
5. Keywords in title, summary, or tags
6. Date ranges (last week/month/year)"""

            search_intent_messages = [
                {"role": "system", "content": f"""You are an AI assistant that helps search through articles about {chat_request.topic}.
Your job is to create effective search queries based on user questions.

{available_options}

IMPORTANT: You must follow these exact steps in order:

1. SPECIAL QUERY TYPES:
   a) For trend analysis requests:
      - Do NOT use keywords like "trends" or "patterns"
      - Instead, use ONLY the date_range parameter
      - Return ALL articles within that timeframe
      Example:
      {{
          "queries": [
              {{
                  "description": "Get all articles from the last 90 days for trend analysis",
                  "params": {{
                      "category": null,
                      "keyword": null,
                      "sentiment": null,
                      "future_signal": null,
                      "tags": null,
                      "date_range": "90"
                  }}
              }}
          ]
      }}

Return your search strategy in this format:
{{
    "queries": [
        {{
            "description": "Brief description of what this query searches for",
            "params": {{
                "category": ["Exact category names"] or null,
                "keyword": "main search term OR alternative term OR another term",
                "sentiment": "exact sentiment" or null,
                "future_signal": "exact signal" or null,
                "time_to_impact": "exact impact timing" or null,
                "tags": ["relevant", "search", "terms"],
                "date_range": "7/30/365" or null
            }}
        }}
    ]
}}"""},
                {"role": "user", "content": chat_request.message}
            ]

            # Get search parameters from LLM
            search_response = ai_model.generate_response(search_intent_messages)
            logger.debug(f"LLM search response: {search_response}")
            try:
                json_str = extract_json_from_response(search_response)
                logger.debug(f"Extracted JSON: {json_str}")
                search_strategy = json.loads(json_str)
                logger.debug(f"Search strategy: {json.dumps(search_strategy, indent=2)}")
                
                all_articles = []
                total_count = 0
                
                for query in search_strategy["queries"]:
                    params = query["params"]
                    logger.debug(f"Executing query: {query['description']}")
                    logger.debug(f"Query params: {json.dumps(params, indent=2)}")
                    
                    # Calculate date range if specified
                    pub_date_start = None
                    pub_date_end = None
                    if params.get("date_range"):
                        if params["date_range"] != "all":
                            pub_date_end = datetime.now()
                            pub_date_start = pub_date_end - timedelta(days=int(params["date_range"]))
                            pub_date_end = pub_date_end.strftime('%Y-%m-%d')
                            pub_date_start = pub_date_start.strftime('%Y-%m-%d')

                    # If we have a category match, use only that
                    if params.get("category"):
                        articles, count = db.search_articles(
                            topic=chat_request.topic,
                            category=params.get("category"),
                            pub_date_start=pub_date_start,
                            pub_date_end=pub_date_end,
                            page=1,
                            per_page=chat_request.limit
                        )
                    # Otherwise, use keyword search
                    else:
                        articles, count = db.search_articles(
                            topic=chat_request.topic,
                            keyword=params.get("keyword"),
                            sentiment=[params.get("sentiment")] if params.get("sentiment") else None,
                            future_signal=[params.get("future_signal")] if params.get("future_signal") else None,
                            tags=params.get("tags"),
                            pub_date_start=pub_date_start,
                            pub_date_end=pub_date_end,
                            page=1,
                            per_page=chat_request.limit
                        )
                    
                    logger.debug(f"Query returned {count} articles")
                    all_articles.extend(articles)
                    total_count += count
                
                # Remove duplicates based on article URI
                seen_uris = set()
                unique_articles = []
                for article in all_articles:
                    if article['uri'] not in seen_uris:
                        seen_uris.add(article['uri'])
                        unique_articles.append(article)
                
                articles = unique_articles[:chat_request.limit]  # Use user's selected limit instead of 50
                search_method = "structured keyword search"

                # Format search criteria for display
                active_filters = []
                if search_strategy.get("keyword"):
                    active_filters.append(f"Keywords: {search_strategy.get('keyword').replace('|', ' OR ')}")
                if search_strategy.get("category"):
                    active_filters.append(f"Categories: {', '.join(search_strategy.get('category'))}")
                if search_strategy.get("sentiment"):
                    active_filters.append(f"Sentiment: {search_strategy.get('sentiment')}")
                if search_strategy.get("future_signal"):
                    active_filters.append(f"Future Signal: {search_strategy.get('future_signal')}")
                if search_strategy.get("tags"):
                    active_filters.append(f"Tags: {', '.join(search_strategy.get('tags'))}")

                search_summary = f"""## Search Method: {search_method.title()}
{chr(10).join(['- ' + f for f in active_filters])}
- **Analysis Limit**: {chat_request.limit} articles

## Results Overview
Found {total_count} total matching articles
Analyzing the {len(articles)} most recent articles
"""
            except Exception as e:
                logger.error(f"Search error: {str(e)}", exc_info=True)
                articles = []
                total_count = 0
                search_method = "error fallback"
                search_summary = "## Search Error\nFell back to basic search due to parsing error."

        # Create system message with topic options
        system_message = f"""You are an AI assistant analyzing articles about {chat_request.topic}. 
You have access to a database of articles with the following attributes:

Available Categories:
{', '.join(topic_options['categories'])}

Available Sentiments:
{', '.join(topic_options['sentiments'])}

Available Future Signals:
{', '.join(topic_options['futureSignals'])}

Available Time to Impact:
{', '.join(topic_options['timeToImpacts'])}

The articles were retrieved using {search_method}, which means they are either:
- Semantically relevant to the user's query (vector search)
- Matching specific criteria like categories, keywords, or filters (SQL search)

When analyzing articles, consider:
1. Sentiment Analysis:
   - Distribution of sentiments across articles
   - Sentiment trends over time
   - Correlation between sentiment and other attributes

2. Future Impact Analysis:
   - Distribution of future signals
   - Time to impact predictions
   - Driver types and their explanations

3. Category Analysis:
   - Distribution of articles across categories
   - Category-specific trends
   - Cross-category comparisons

4. Temporal Analysis:
   - Publication date patterns
   - Submission date trends
   - Time-based impact analysis

Format your responses using markdown for better readability:
- Use ## for section headings
- Use bullet points for lists
- Use **bold** for emphasis
- Use `code` for technical terms
- Use > for quotes from articles
- Use tables when comparing multiple articles

When summarizing multiple articles, use clear sections and formatting to organize the information.
Provide insights about trends, patterns, and key findings across the articles."""

        # Format articles for context
        context = "\n\n".join([
            f"Title: {article['title']}\n"
            f"Summary: {article['summary']}\n"
            f"Category: {article['category']}\n"
            f"Future Signal: {article['future_signal']}\n"
            f"Sentiment: {article['sentiment']}\n"
            f"Time to Impact: {article['time_to_impact']}\n"
            f"Tags: {', '.join(article['tags']) if article.get('tags') else 'None'}\n"
            f"Publication Date: {article.get('publication_date', 'Unknown')}"
            + (f"\nSimilarity Score: {article.get('similarity_score', 'N/A')}" if 'similarity_score' in article else "")
            for article in articles
        ])

        # Build messages array with conversation history
        messages = [
            {"role": "system", "content": system_message}
        ]
        
        # Add conversation history if available
        if chat_request.conversation_history:
            messages.extend(chat_request.conversation_history)
        
        # Add current message with context
        messages.append({
            "role": "user", 
            "content": f"""
{search_summary}

Here are the {len(articles)} most relevant articles out of {total_count} total matches:

{context}

User Question: {chat_request.message}

Please provide a comprehensive analysis of these {len(articles)} articles, noting that they represent the most relevant subset of {total_count} total matching articles using {search_method}. 
Start your response with a summary of how many total articles were found and their general distribution across categories, sentiments, and future signals in this sample.

Please provide a clear and concise answer based on the articles provided. 
If the user asked for specific articles, summarize the search results first."""
        })

        logger.debug(f"Sending {len(articles)} articles to LLM for analysis using {search_method}")
        response = ai_model.generate_response(messages)
        return {
            "response": response,
            "search_method": search_method,
            "total_matches": total_count,
            "analyzed_count": len(articles)
        }
    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def select_diverse_articles(articles, limit):
    """Select diverse articles from a larger pool based on category, source, and recency."""
    if len(articles) <= limit:
        return articles
    
    # Sort by similarity score first (best matches first)
    sorted_articles = sorted(articles, key=lambda x: x.get('similarity_score', 1.0))
    
    selected = []
    seen_categories = set()
    seen_sources = set()
    
    # First pass: Select top articles ensuring category diversity
    for article in sorted_articles:
        if len(selected) >= limit:
            break
            
        category = article.get('category', 'Unknown')
        source = article.get('news_source', 'Unknown')
        
        # Prefer articles from new categories and sources
        category_bonus = 0 if category in seen_categories else 1
        source_bonus = 0 if source in seen_sources else 0.5
        
        # Add if we have space and it adds diversity, or if it's a very good match
        if (len(selected) < limit * 0.7 or  # Always fill 70% with top matches
            category_bonus > 0 or source_bonus > 0):
            selected.append(article)
            seen_categories.add(category)
            seen_sources.add(source)
    
    # Fill remaining slots with best remaining articles
    remaining_needed = limit - len(selected)
    if remaining_needed > 0:
        remaining_articles = [a for a in sorted_articles if a not in selected]
        selected.extend(remaining_articles[:remaining_needed])
    
    return selected[:limit] 