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

router = APIRouter()
templates = Jinja2Templates(directory="templates")
logger = logging.getLogger(__name__)

# Add this class to define the expected request body
class ChatRequest(BaseModel):
    message: str
    topic: str
    model: str

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

   b) For sentiment analysis requests:
      - Do NOT use keywords like "sentiment" or "analysis"
      - For category-based analysis: use only the category parameter
      - For time-based analysis: use only the date_range parameter
      - For all articles: use no parameters
      Example:
      {{
          "queries": [
              {{
                  "description": "Get articles for sentiment analysis based on specified filter",
                  "params": {{
                      "category": ["AI Ethics"] or null,  # Only if category specified
                      "keyword": null,
                      "sentiment": null,
                      "future_signal": null,
                      "tags": null,
                      "date_range": "90" or null  # Only if time-based analysis
                  }}
              }}
          ]
      }}

2. FOR ALL OTHER REQUESTS:
1. ALWAYS check the available categories first:
    - Look at the list of available categories above
    - If you see a category that EXACTLY matches the topic (like "AI Carbon Footprint" for carbon footprint questions),
      use ONLY that category in your search
    - Example for carbon footprint question:""" + r"""
     {
         "queries": [
             {
                 "description": "Search in AI Carbon Footprint category",
                 "params": {
                     "category": ["AI Carbon Footprint"],
                     "keyword": null,
                     "sentiment": null,
                     "future_signal": null,
                     "tags": null,
                     "date_range": "30"  # Can be 7, 14, 30, 90, 365, or "all"
                 }
             }
         ]
     }""" + """

3. ONLY if no exact category match exists:
    - Use a simple keyword search
    - Example for a topic without a matching category:""" + r"""
     {
         "queries": [
             {
                 "description": "Search for articles about quantum computing",
                 "params": {
                     "category": null,
                     "keyword": "quantum computing",
                     "sentiment": null,
                     "future_signal": null,
                     "tags": null,
                     "date_range": null
                 }
             }
         ]
     }""" + """

Remember:
- For trend analysis, use ONLY date_range parameter
- For sentiment analysis, use ONLY category parameter if specified
- For category summaries, use both category and date_range parameters
- ALWAYS check categories first for other queries
- Use EXACT category names from the list
- Only use keyword search if no category matches
- Keep searches simple - don't mix multiple parameters
- IMPORTANT: Your response must be ONLY the JSON object, no additional text

Return your search strategy in this format:""" + r"""
{
    "queries": [
        {
            "description": "Brief description of what this query searches for",
            "params": {
                "category": ["Exact category names"] or null,
                "keyword": "main search term OR alternative term OR another term",
                "sentiment": "exact sentiment" or null,
                "future_signal": "exact signal" or null,
                "tags": ["relevant", "search", "terms"],
                "date_range": "7/30/365" or null
            }
        }
    ]
}"""},
            {"role": "user", "content": "Tell me about AI's carbon footprint"},
            {"role": "assistant", "content": r"""Looking at the available categories, I see "AI Carbon Footprint" which exactly matches this query.
{
    "queries": [
        {
            "description": "Search in AI Carbon Footprint category",
            "params": {
                "category": ["AI Carbon Footprint"],
                "keyword": null,
                "sentiment": null,
                "future_signal": null,
                "tags": null,
                "date_range": "30"  # Can be 7, 14, 30, 90, 365, or "all"
            }
        }
    ]
}}"""},
            {"role": "user", "content": "What about quantum computing?"},
            {"role": "assistant", "content": r"""I don't see a specific category for quantum computing, so I'll use a keyword search.
{
    "queries": [
        {
            "description": "Search for articles about quantum computing",
            "params": {
                "category": null,
                "keyword": "quantum computing",
                "sentiment": null,
                "future_signal": null,
                "tags": null,
                "date_range": null
            }
        }
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
                        per_page=50
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
                        per_page=50
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
            
            articles = unique_articles[:50]  # Keep top 50 most recent unique articles

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
            if search_strategy.get("date_range"):
                if search_strategy.get("date_range") == "all":
                    active_filters.append("Date Range: All time")
                else:
                    active_filters.append(f"Date Range: Last {search_strategy.get('date_range')} days (from {pub_date_start} to {pub_date_end})")

            search_summary = f"""## Search Criteria
{chr(10).join(['- ' + f for f in active_filters])}

## Results Overview
Found {total_count} total matching articles
Analyzing the {len(articles)} most recent articles
"""

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

You can help users find and analyze articles by:
- Searching for keywords in titles, summaries, and tags
- Filtering by any of the above attributes
- Filtering by date ranges
- Combining multiple criteria

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
                for article in articles
            ])

            messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": f"""
{search_summary}

Here are the {len(articles)} most recent articles out of {total_count} total matches:

{context}

User Question: {chat_request.message}

Please provide a comprehensive analysis of these {len(articles)} articles, noting that they represent the most recent subset of {total_count} total matching articles. 
Start your response with a summary of how many total articles were found and their general distribution across categories, sentiments, and future signals in this sample.

Please provide a clear and concise answer based on the articles provided. 
If the user asked for specific articles, summarize the search results first."""}
            ]

            logger.debug(f"Sending {len(articles)} articles to LLM for analysis")
            response = ai_model.generate_response(messages)
            return {
                "response": response,
                "search_criteria": search_strategy,
                "total_matches": total_count,
                "analyzed_count": len(articles)
            }
        except Exception as e:
            logger.error(f"Search error: {str(e)}", exc_info=True)
            articles = []
            total_count = 0
    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 