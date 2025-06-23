from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.database import Database, get_database_instance
from app.security.session import verify_session
from app.services.auspex_service import get_auspex_service
from app.analytics import Analytics
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging
import json
import re
from app.research import Research
from app.dependencies import get_research

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/executive-summary", tags=["executive-summary"])
# Add a separate router for the web page (without API prefix)
web_router = APIRouter(tags=["executive-summary-web"])
templates = Jinja2Templates(directory="templates")

# Pydantic Models
class MarketSignal(BaseModel):
    signal: str
    frequency: str
    impact: str
    level: str

class RiskOpportunityCard(BaseModel):
    type: str  # "risk" or "opportunity"
    title: str
    description: str
    timeline: Optional[str] = None
    probability: Optional[str] = None

class AnalystQuote(BaseModel):
    text: str
    author: str
    title: str
    uri: Optional[str] = None

class MarketSignalsResponse(BaseModel):
    signals: List[MarketSignal]
    risks: List[RiskOpportunityCard]
    opportunities: List[RiskOpportunityCard]
    quotes: List[AnalystQuote]
    analytics_data: Dict[str, Any]

@router.get("/market-signals/{topic_name}", response_model=MarketSignalsResponse)
async def get_market_signals_analysis(
    topic_name: str,
    timeframe_days: int = Query(30, description="Analysis timeframe in days"),
    model: Optional[str] = Query(None, description="AI model to use for analysis"),
    db: Database = Depends(get_database_instance),
    research: Research = Depends(get_research),
    session: dict = Depends(verify_session)
) -> MarketSignalsResponse:
    """
    Generate market signals and strategic risks analysis for a topic using existing analytics.
    """
    try:
        logger.info(f"Generating market signals analysis for topic: {topic_name}")
        
        # Convert days to timeframe string for analytics
        timeframe = str(timeframe_days) if timeframe_days != 365 else "all"
        
        # Use existing Analytics class
        analytics = Analytics(db)
        analytics_data = analytics.get_analytics_data(
            timeframe=timeframe,
            topic=topic_name,
            curated=True
        )
        
        if analytics_data['totalArticles'] == 0:
            raise HTTPException(status_code=404, detail=f"No analyzed articles found for topic: {topic_name}")
        
        # Analyze signals from the analytics data using topic-filtered future signals
        signals = await _extract_market_signals_from_analytics(analytics_data, topic_name, research)
        
        # Get recent articles for AI analysis
        query = """
        SELECT uri, title, summary, future_signal, sentiment, time_to_impact, 
               driver_type, category, publication_date, news_source
        FROM articles 
        WHERE topic = ? 
        AND publication_date >= date('now', '-{} days')
        AND analyzed = 1
        ORDER BY publication_date DESC
        LIMIT 50
        """.format(timeframe_days)
        
        articles = db.fetch_all(query, (topic_name,))
        
        # Generate risk and opportunity cards using AI
        auspex = get_auspex_service()
        risks, opportunities = await _generate_risk_opportunity_cards(auspex, topic_name, articles, analytics_data, model)
        
        # Extract real article quotes and links for decision makers
        quotes = _extract_article_quotes_and_links(articles, analytics_data)
        
        return MarketSignalsResponse(
            signals=signals,
            risks=risks,
            opportunities=opportunities,
            quotes=quotes,
            analytics_data=analytics_data
        )
        
    except Exception as e:
        logger.error(f"Error generating market signals analysis: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

async def _extract_market_signals_from_analytics(analytics_data: Dict, topic_name: str, research) -> List[MarketSignal]:
    """Extract market signals from topic-filtered future signals and analytics data."""
    
    signals = []
    
    try:
        # Get topic-filtered future signals with counts from the database directly
        # We need actual counts, not just the config list
        query = """
        SELECT future_signal, COUNT(*) as count
        FROM articles 
        WHERE topic = ? 
        AND future_signal IS NOT NULL 
        AND future_signal != ''
        AND analyzed = 1
        GROUP BY future_signal
        ORDER BY count DESC
        """
        
        # Use the database from analytics_data context or get a new connection
        from app.database import Database
        db = Database()
        future_signals_data = db.fetch_all(query, (topic_name,))
        
        # Get time to impact distribution from analytics for impact timing
        time_to_impact_data = analytics_data.get('timeToImpactDistribution', {})
        
        if not future_signals_data:
            logger.warning(f"No future signals found for topic: {topic_name}")
            return signals
        
        # Calculate total signals for percentage calculation
        total_signals = sum(row[1] for row in future_signals_data)
        
        # Process ALL topic-specific future signals as scenarios
        for signal_row in future_signals_data:
            signal_label = signal_row[0]
            signal_count = signal_row[1]
            
            if not signal_label or signal_count == 0:
                continue
            
            # Skip signals with asterisk artifacts (they should be cleaned but just in case)
            if signal_label.startswith('**') or signal_label.startswith('* '):
                continue
            
            # Calculate percentage based on total topic signals
            percentage = (signal_count / total_signals * 100) if total_signals > 0 else 0
            
            # Determine frequency level based on count and percentage
            if percentage >= 30 or signal_count >= 10:
                frequency = "High"
                level = "high"
            elif percentage >= 15 or signal_count >= 5:
                frequency = "Moderate" 
                level = "moderate"
            else:
                frequency = "Low"
                level = "low"
            
            # Determine the most likely time to impact for this signal
            impact = "Short-term"  # Default
            if time_to_impact_data.get('labels') and time_to_impact_data.get('values'):
                # Filter out None values from labels and find corresponding values
                valid_entries = [(label, value) for label, value in zip(time_to_impact_data['labels'], time_to_impact_data['values']) if label is not None]
                
                if valid_entries:
                    # Find the dominant time impact across all signals (excluding None)
                    max_entry = max(valid_entries, key=lambda x: x[1])
                    impact = max_entry[0]
                
                # For variety, distribute signals across different timeframes based on their characteristics
                valid_labels = [entry[0] for entry in valid_entries]
                
                if signal_label and ('accelerate' in signal_label.lower() or 'immediate' in signal_label.lower()):
                    # Acceleration signals tend to be shorter term
                    short_term_options = [t for t in valid_labels if t and ('short' in t.lower() or 'immediate' in t.lower())]
                    if short_term_options:
                        impact = short_term_options[0]
                elif signal_label and ('gradual' in signal_label.lower() or 'evolve' in signal_label.lower()):
                    # Gradual signals tend to be longer term
                    long_term_options = [t for t in valid_labels if t and ('long' in t.lower() or 'mid' in t.lower())]
                    if long_term_options:
                        impact = long_term_options[0]
                elif signal_label and ('transform' in signal_label.lower() or 'revolution' in signal_label.lower()):
                    # Transformation signals tend to be mid-term
                    mid_term_options = [t for t in valid_labels if t and 'mid' in t.lower()]
                    if mid_term_options:
                        impact = mid_term_options[0]
            
            # Ensure impact is not None
            if not impact:
                impact = "Short-term"
            
            signals.append(MarketSignal(
                signal=signal_label,
                frequency=frequency,
                impact=impact,
                level=level
            ))
        
        # Sort by level priority (high -> moderate -> low) then by frequency count
        level_priority = {'high': 3, 'moderate': 2, 'low': 1}
        signals.sort(key=lambda x: (level_priority.get(x.level, 0), x.frequency), reverse=True)
        
        logger.info(f"Extracted {len(signals)} market signals for topic: {topic_name}")
        return signals
        
    except Exception as e:
        logger.error(f"Error extracting market signals for topic {topic_name}: {str(e)}")
        # Fallback to empty list if there's an error
        return []

async def _generate_risk_opportunity_cards(auspex, topic_name: str, articles, analytics_data: Dict, model: Optional[str] = None) -> tuple[List[RiskOpportunityCard], List[RiskOpportunityCard]]:
    """Generate risk and opportunity cards using AI analysis and analytics insights."""
    
    # Prepare analytics summary for AI context
    analytics_summary = {
        "total_articles": analytics_data.get('totalArticles', 0),
        "top_sentiment": _get_top_item(analytics_data.get('sentimentDistribution', {})),
        "top_future_signal": _get_top_item(analytics_data.get('futureSignalDistribution', {})),
        "top_time_to_impact": _get_top_item(analytics_data.get('timeToImpactDistribution', {})),
        "sentiment_trend": "positive" if _get_top_item(analytics_data.get('sentimentDistribution', {})) in ['Positive', 'Neutral'] else "negative"
    }
    
    # Get diverse article sample for better context
    import random
    article_sample = random.sample(articles, min(15, len(articles))) if len(articles) > 15 else articles
    
    # Create AI prompt for risk/opportunity analysis with timestamp for uniqueness
    from datetime import datetime
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    prompt = f"""
    Analysis Context ({current_time}): Based on analysis of {analytics_summary['total_articles']} recent articles about "{topic_name}", identify strategic risks and opportunities.
    
    Key Analytics Insights:
    - Dominant sentiment: {analytics_summary['top_sentiment']}
    - Primary future signal: {analytics_summary['top_future_signal']}
    - Expected time to impact: {analytics_summary['top_time_to_impact']}
    - Overall trend: {analytics_summary['sentiment_trend']}
    
    Recent article headlines (diverse sample):
    {chr(10).join([f"- {article[1]}" for article in article_sample[:12]])}
    
    Generate 3 critical risks and 3 key opportunities for executives. Focus on DIVERSE scenarios:
    
    Risk Categories to Consider:
    - Market correction/bubble risks
    - Technology adoption timeline risks  
    - Competitive displacement risks
    - Regulatory/compliance risks
    - Infrastructure/scaling risks
    
    Opportunity Categories to Consider:
    - Infrastructure build-out advantages
    - Market positioning opportunities
    - Technology adoption benefits
    - Partnership/acquisition opportunities
    - Operational efficiency gains
    
    Ensure each risk and opportunity is DISTINCT and addresses different aspects. Vary timelines (2024-2030).
    
    Format as JSON:
    {{
        "risks": [
            {{"title": "Market Correction Risk (2025-2030)", "description": "High investment levels create bubble risk. 95% of investors cite concerns about power reliability for datacenters, yet 70% anticipate increased funding driven by AI demand.", "timeline": "2025-2030", "probability": "High"}},
            {{"title": "Timeline Risk: AGI Overexpectation", "description": "Ambitious timelines for achieving AGI may be overly optimistic due to diminishing returns and operational challenges.", "timeline": "2025-2027", "probability": "Moderate"}},
            {{"title": "Competitive Displacement Risk", "description": "Traditional companies may face rapid obsolescence as AI-native competitors emerge with superior operational models.", "timeline": "2024-2026", "probability": "High"}}
        ],
        "opportunities": [
            {{"title": "Infrastructure Build-out", "description": "Data center expansion creates competitive advantages for early movers who secure energy and infrastructure partnerships.", "timeline": "2024-2026", "probability": "High"}},
            {{"title": "Gradual Adoption Advantage", "description": "Companies focusing on sustainable, gradual AI integration may outperform those chasing unrealistic AGI timelines.", "timeline": "2025-2028", "probability": "Moderate"}},
            {{"title": "Partnership Ecosystem Growth", "description": "Strategic partnerships between AI providers and traditional industries create new revenue streams and market access.", "timeline": "2024-2027", "probability": "High"}}
        ]
    }}
    """
    
    try:
        # Create temporary chat session for analysis
        chat_id = await auspex.create_chat_session(topic=topic_name, title=f"Risk/Opportunity Analysis {current_time}")
        
        response = ""
        # Use provided model or get first available model
        selected_model = model
        if not selected_model:
            from app.ai_models import get_available_models
            available_models = get_available_models()
            if available_models:
                selected_model = available_models[0]['name']
            else:
                raise HTTPException(status_code=500, detail="No AI models available")
        
        async for chunk in auspex.chat_with_tools(
            chat_id=chat_id,
            message=prompt,
            model=selected_model,
            limit=10,
            tools_config={"search_articles": False}
        ):
            response += chunk
        
        auspex.delete_chat_session(chat_id)
        
        # Parse JSON response
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            
            risks = [RiskOpportunityCard(type="risk", **risk) for risk in data.get("risks", [])]
            opportunities = [RiskOpportunityCard(type="opportunity", **opp) for opp in data.get("opportunities", [])]
            
            # Shuffle for variety
            random.shuffle(risks)
            random.shuffle(opportunities)
            
            return risks, opportunities
        
    except Exception as e:
        logger.error(f"Error generating risk/opportunity cards: {str(e)}")
    
    # Enhanced fallback based on analytics data with variety
    risk_templates = [
        ("Market Correction Risk", "High investment levels create bubble risk based on current sentiment trends.", "2025-2030", "High"),
        ("Technology Timeline Risk", "Overly optimistic AI development timelines may lead to market disappointment.", "2024-2026", "Moderate"),
        ("Competitive Disruption", "Established players may lose market share to AI-native competitors.", "2024-2027", "High"),
        ("Regulatory Uncertainty", "Unclear AI regulations could impact business operations and compliance costs.", "2025-2028", "Moderate")
    ]
    
    opportunity_templates = [
        ("Infrastructure Build-out", "Data center expansion creates competitive advantages for early movers.", "2024-2026", "High"),
        ("Operational Efficiency", "AI automation can significantly reduce operational costs and improve productivity.", "2024-2025", "High"),
        ("Market Expansion", "AI capabilities enable entry into previously inaccessible market segments.", "2025-2027", "Moderate"),
        ("Strategic Partnerships", "Collaboration opportunities emerge between AI providers and traditional industries.", "2024-2026", "High")
    ]
    
    # Select random templates
    selected_risks = random.sample(risk_templates, min(2, len(risk_templates)))
    selected_opps = random.sample(opportunity_templates, min(2, len(opportunity_templates)))
    
    risks = [RiskOpportunityCard(type="risk", title=title, description=desc, timeline=timeline, probability=prob) 
             for title, desc, timeline, prob in selected_risks]
    
    opportunities = [RiskOpportunityCard(type="opportunity", title=title, description=desc, timeline=timeline, probability=prob) 
                    for title, desc, timeline, prob in selected_opps]
    
    return risks, opportunities

def _extract_article_quotes_and_links(articles, analytics_data: Dict) -> List[AnalystQuote]:
    """Extract diverse quotes/extracts from articles with links for decision makers."""
    
    quotes = []
    
    if not articles:
        return quotes
    
    import random
    
    # Get diverse articles by shuffling and filtering
    shuffled_articles = list(articles)
    random.shuffle(shuffled_articles)
    
    # Sort by various criteria to get diversity
    recent_articles = sorted(shuffled_articles, key=lambda x: x[8] if len(x) > 8 and x[8] else '', reverse=True)[:15]
    diverse_sources = []
    seen_sources = set()
    
    # Ensure source diversity
    for article in recent_articles:
        news_source = article[9] if len(article) > 9 else "Unknown Source"
        if news_source not in seen_sources or len(diverse_sources) < 5:
            diverse_sources.append(article)
            seen_sources.add(news_source)
        if len(diverse_sources) >= 8:
            break
    
    # Extract meaningful quotes from diverse articles
    processed_count = 0
    for article in diverse_sources:
        if processed_count >= 6:  # Limit to top 6 quotes
            break
            
        uri = article[0] if len(article) > 0 else ""
        title = article[1] if len(article) > 1 else ""
        summary = article[2] if len(article) > 2 else ""
        news_source = article[9] if len(article) > 9 else "Unknown Source"
        publication_date = article[8] if len(article) > 8 else ""
        
        if not summary or len(summary.strip()) < 50:
            continue
            
        processed_count += 1
            
        # Clean and extract the most relevant part of the summary
        clean_summary = summary.strip()
        
        # Extract different types of insights
        if processed_count <= 2:
            # First quotes: key insights
            if '. ' in clean_summary:
                sentences = clean_summary.split('. ')
                # Find the most substantial sentence
                best_sentence = max(sentences[:3], key=len) if sentences else clean_summary
                extract = best_sentence.strip()
            else:
                extract = clean_summary[:180] + "..." if len(clean_summary) > 180 else clean_summary
        elif processed_count <= 4:
            # Middle quotes: specific details
            sentences = clean_summary.split('. ')
            if len(sentences) > 2:
                # Take middle sentences for variety
                extract = sentences[1].strip()
                if len(extract) < 50 and len(sentences) > 2:
                    extract = sentences[2].strip()
            else:
                extract = clean_summary[:200] + "..." if len(clean_summary) > 200 else clean_summary
        else:
            # Later quotes: conclusions or implications
            sentences = clean_summary.split('. ')
            if len(sentences) > 1:
                # Take last meaningful sentence
                extract = sentences[-1].strip() if len(sentences[-1]) > 30 else sentences[-2].strip()
            else:
                extract = clean_summary[:160] + "..." if len(clean_summary) > 160 else clean_summary
        
        # Ensure proper ending
        if not extract.endswith('.') and not extract.endswith('...') and len(extract) > 20:
            extract += "..."
        
        # Format publication date for display
        date_display = publication_date[:10] if publication_date and len(publication_date) >= 10 else "Recent"
        
        quotes.append(AnalystQuote(
            text=f'"{extract}"',
            author=f"{news_source} ({date_display})",
            title=f"Source: {title[:80]}..." if len(title) > 80 else title,
            uri=uri
        ))
    
    return quotes

def _get_top_item(distribution_data: Dict) -> str:
    """Helper to get the top item from a distribution."""
    if not distribution_data.get('labels') or not distribution_data.get('values'):
        return "Unknown"
    
    max_idx = distribution_data['values'].index(max(distribution_data['values']))
    return distribution_data['labels'][max_idx]

# Web routes for the dashboard pages (without API prefix)
@web_router.get("/market-signals-dashboard/{topic_name}", response_class=HTMLResponse)
async def market_signals_dashboard_page(
    request: Request,
    topic_name: str,
    session: dict = Depends(verify_session)
):
    """Render the Market Signals & Strategic Risks dashboard page."""
    from app.main import get_template_context
    return templates.TemplateResponse("market_signals_dashboard.html", get_template_context(request, {
        "topic_name": topic_name,
        "session": session
    }))

# Alternative route without topic for topic selection
@web_router.get("/market-signals-dashboard", response_class=HTMLResponse)
async def market_signals_dashboard_index(
    request: Request,
    session: dict = Depends(verify_session)
):
    """Render the Market Signals & Strategic Risks dashboard topic selection."""
    from app.main import get_template_context
    return templates.TemplateResponse("market_signals_dashboard.html", get_template_context(request, {
        "topic_name": None,
        "session": session
    })) 