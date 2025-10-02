from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.database import Database, get_database_instance
from app.database_query_facade import DatabaseQueryFacade
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
    count: int  # Add actual article count

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
            curated=False
        )
        
        if analytics_data['totalArticles'] == 0:
            raise HTTPException(status_code=404, detail=f"No analyzed articles found for topic: {topic_name}")
        
        # Analyze signals from the analytics data using topic-filtered future signals
        signals = await _extract_market_signals_from_analytics(analytics_data, topic_name, research)
        
        # Get recent articles for AI analysis
        articles = (DatabaseQueryFacade(db, logger)).get_articles_for_market_signal_analysis(timeframe_days, topic_name)
        
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
        # Use the database from analytics_data context or get a new connection
        from app.database import Database
        db = Database()
        future_signals_data = (DatabaseQueryFacade(db, logger)).get_topic_filtered_future_signals_with_counts_for_market_signal_analysis(topic_name)
        
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
            
            # Dynamic frequency determination based on data distribution
            # Use relative thresholds that adapt to the actual signal distribution
            num_signals = len(future_signals_data)
            avg_count = total_signals / num_signals if num_signals > 0 else 0
            
            # More stringent and adaptive thresholds
            if num_signals <= 3:
                # Few signals: use percentage-based thresholds
                if percentage >= 40:
                    frequency = "High"
                    level = "high"
                elif percentage >= 20:
                    frequency = "Moderate"
                    level = "moderate"
                else:
                    frequency = "Low"
                    level = "low"
            elif num_signals <= 6:
                # Medium number of signals: balanced approach
                if percentage >= 25 or signal_count >= (avg_count * 1.5):
                    frequency = "High"
                    level = "high"
                elif percentage >= 12 or signal_count >= avg_count:
                    frequency = "Moderate"
                    level = "moderate"
                else:
                    frequency = "Low"
                    level = "low"
            else:
                # Many signals: focus on relative distribution
                high_threshold = max(15, avg_count * 1.8)  # Significantly above average
                moderate_threshold = max(8, avg_count * 1.2)  # Above average
                
                if percentage >= 20 or signal_count >= high_threshold:
                    frequency = "High"
                    level = "high"
                elif percentage >= 8 or signal_count >= moderate_threshold:
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
                level=level,
                count=signal_count
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

@web_router.get("/ai-impact-timeline", response_class=HTMLResponse)
async def ai_impact_timeline_page(
    request: Request,
    session: dict = Depends(verify_session)
):
    """Render the AI Impact Timeline page."""
    from app.main import get_template_context
    return templates.TemplateResponse("ai_timeline_html.html", get_template_context(request, {
        "session": session
    }))

@router.get("/ai-impact-timeline/{topic_name}")
async def get_ai_impact_timeline_analysis(
    topic_name: str,
    timeframe_days: int = Query(365, description="Analysis timeframe in days"),
    model: Optional[str] = Query(None, description="AI model to use for analysis"),
    future_horizon: int = Query(10, description="Future horizon in years"),
    analysis_depth: str = Query("standard", description="Analysis depth"),
    sample_size_mode: str = Query("auto", description="Sample size mode"),
    custom_limit: Optional[int] = Query(None, description="Custom sample limit"),
    db: Database = Depends(get_database_instance),
    research: Research = Depends(get_research),
    session: dict = Depends(verify_session)
):
    """
    Generate AI impact timeline analysis for a topic using Auspex.
    """
    try:
        logger.info(f"Generating AI impact timeline analysis for topic: {topic_name}")
        
        # Calculate optimal sample size
        optimal_sample_size = _calculate_optimal_sample_size(model or 'gpt-4o', sample_size_mode, custom_limit)
        logger.info(f"Using sample size: {optimal_sample_size} articles for model: {model}")
        
        # Get recent articles for the topic
        articles = (DatabaseQueryFacade(db, logger)).get_recent_articles_for_market_signal_analysis(timeframe_days, topic_name, optimal_sample_size)
        
        if not articles:
            raise HTTPException(
                status_code=404, 
                detail=f"No analyzed articles found for topic: {topic_name}"
            )
        
        logger.info(f"Found {len(articles)} articles for timeline analysis")
        
        # Use Auspex to generate the timeline analysis
        auspex = get_auspex_service()
        
        # Prepare the prompt based on "Potential Timing of Major Impacts"
        timeline_prompt = f"""# AI Impact Timeline Analysis: Potential Timing of Major Impacts

Based on analysis of {len(articles)} recent articles about "{topic_name}", generate a comprehensive strategic planning timeline for major AI impacts following the detailed analysis format.

## Analysis Focus: "Potential Timing of Major Impacts"

**Your task:** Create a detailed timeline analysis with 6-8 impact categories, following the comprehensive structure with specific timing milestones, detailed analysis, and strategic insights.

**Article Data Summary:**
{_prepare_articles_summary(articles, topic_name)}

## Required Output Format:

```json
{{
  "topic": "{topic_name}",
  "summary": {{
    "total_articles": {len(articles)},
    "category_focus": [
      "[Generate category analysis based on your actual article data - do not copy these examples]"
    ],
    "sentiment_distribution": {{
      "[Generate based on actual article sentiment analysis]": "[Percentage]"
    }},
    "future_signal_distribution": {{
      "[Generate based on actual article future signals]": "[Percentage]"
    }},
    "time_to_impact": {{
      "[Generate based on actual article time to impact data]": "[Percentage]"
    }}
  }},
  "swimlanes": [
    "[Generate 6-8 swimlanes based on your analysis of the article data. Each swimlane must have: category, timeframe, color, description, detailed_analysis (immediate_short_term, mid_term, long_term), milestone_analysis (for each milestone year), and milestones array. Use the color scheme: bg-red-500, bg-orange-500, bg-blue-500, bg-green-500, bg-purple-500, bg-indigo-500, bg-pink-500, bg-teal-500]"
  ],
  "insights": [
    "[Generate 4 unique insights based on your analysis of the article data - not these examples]",
    "[Focus on immediate actions executives should take based on the evidence]",
    "[Address mid-term strategic investments and preparations needed]",
    "[Provide perspective on long-term implications and monitoring requirements]"
  ]
}}
```

## Detailed Guidelines:

### **Category Guidelines (6-8 swimlanes):**
Generate categories based on patterns you find in the article data. Consider areas like:
- Business and market impacts
- Employment and workforce changes
- Technology development and adoption
- Societal and cultural effects
- Governance and regulatory responses
- Sector-specific applications
- Risk and security considerations

### **Timeframe Structure (Analysis Horizon: {future_horizon} years):**
- **Immediate (now–12 months)**: Current developments and immediate impacts
- **Short-term (1–2 years)**: Next 1-2 years developments  
- **Mid-term (2–{int(future_horizon*0.6)} years)**: Mid-range transformation phase
- **Long-term ({int(future_horizon*0.6)}+ years)**: Long-term paradigm shifts within {future_horizon}-year horizon

### **Milestone Guidelines:**
- Position scale: 0-100 representing timeline progression from 2024 to 2035+
- Include specific years and concrete, measurable events
- Reference real developments when possible from the article data
- 3-4 milestones per category showing progression

### **Analysis Depth:**
- Include detailed_analysis for each category with immediate/mid/long-term breakdown
- Include milestone_analysis with specific analysis for each milestone year
- Reference specific examples, companies, statistics when available from articles
- Show progression and causality between timeframes
- Make each milestone analysis unique and evidence-based

### **Colors to Use:**
- bg-red-500 (Business/Market), bg-orange-500 (Employment), bg-blue-500 (Software Dev)
- bg-green-500 (Society), bg-purple-500 (AGI), bg-indigo-500 (Trust/Security) 
- bg-pink-500 (Ethics/Regulation), bg-teal-500 (Healthcare/Science)

### **Strategic Insights (4 key insights):**
CRITICAL REQUIREMENTS:
1. **No Placeholder Content**: The JSON template above contains placeholder text in brackets - DO NOT copy any of this placeholder text. Generate completely original content.
2. **Complete JSON Structure**: Generate a full, valid JSON response with all required fields populated with real analysis.
3. **Evidence-based Analysis**: Base all content on specific findings from the analyzed articles, not generic statements.
4. **Unique Content**: Every piece of text must be unique - no recycled or repeated analysis across different sections.
5. **Milestone-Specific Analysis**: Each milestone year requires its own specific analysis based on evidence.
6. **Topic-Relevant**: All analysis must be directly related to the specific topic being analyzed.

**STRUCTURE REQUIREMENTS**:
- Generate 6-8 swimlanes based on actual article analysis
- Each swimlane needs: category, timeframe, color (from the specified scheme), description, detailed_analysis, milestone_analysis, and milestones
- Create 4 original strategic insights based on your analysis
- Provide realistic data distributions based on actual article content

**FINAL INSTRUCTION**: Generate the comprehensive timeline analysis now as a complete, valid JSON response. If you cannot generate meaningful analysis from the article data, do not provide generic content - indicate the specific issue instead.

Your response must be a properly formatted JSON that matches the template structure exactly, with all placeholder text replaced by original analysis based on the article evidence:"""

        # Generate the analysis using Auspex
        # Create temporary chat session for analysis
        from datetime import datetime
        current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        chat_id = await auspex.create_chat_session(topic=topic_name, title=f"AI Impact Timeline Analysis {current_time}")
        
        result = ""
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
            message=timeline_prompt,
            model=selected_model,
            limit=10,
            tools_config={"search_articles": False}
        ):
            result += chunk
        
        auspex.delete_chat_session(chat_id)
        
        # Parse the result
        try:
            import json
            import re
            
            # Extract JSON from the response
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', result, re.DOTALL)
            if json_match:
                timeline_data = json.loads(json_match.group(1))
            else:
                # Try to find JSON without code blocks
                json_start = result.find('{')
                json_end = result.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    timeline_data = json.loads(result[json_start:json_end])
                else:
                    raise ValueError("No valid JSON found in response")
            
            # Add metadata
            timeline_data.update({
                'generated_at': datetime.now().isoformat(),
                'articles_analyzed': len(articles),
                'timeframe_days': timeframe_days,
                'model_used': model or 'gpt-4o'
            })
            
            logger.info(f"Successfully generated timeline with {len(timeline_data.get('swimlanes', []))} categories")
            return timeline_data
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse JSON response: {e}")
            raise HTTPException(status_code=500, detail=f"AI analysis failed to generate valid timeline data: {e}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating timeline analysis: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

def _calculate_optimal_sample_size(model: str, sample_size_mode: str = 'auto', custom_limit: int = None) -> int:
    """Calculate optimal sample size based on model capabilities and mode"""
    
    if sample_size_mode == 'custom' and custom_limit:
        return custom_limit
    
    # Context limits for different AI models
    context_limits = {
        'gpt-3.5-turbo': 16385,
        'gpt-4': 8192,
        'gpt-4-turbo': 128000,
        'gpt-4o': 128000,
        'gpt-4o-mini': 128000,
        'gpt-4.1': 1000000,
        'claude-3-opus': 200000,
        'claude-3-sonnet': 200000,
        'claude-3.5-sonnet': 200000,
        'default': 16385
    }
    
    context_limit = context_limits.get(model, context_limits['default'])
    is_mega_context = context_limit >= 1000000
    
    if sample_size_mode == 'focused':
        base_sample_size = 50 if is_mega_context else 25
    elif sample_size_mode == 'balanced':
        base_sample_size = 100 if is_mega_context else 50
    elif sample_size_mode == 'comprehensive':
        base_sample_size = 200 if is_mega_context else 100
    else:  # auto or default
        base_sample_size = 150 if is_mega_context else 75
    
    # Ensure reasonable limits
    max_limit = 1000 if is_mega_context else 400
    min_limit = 20
    
    return max(min_limit, min(base_sample_size, max_limit))

def _prepare_articles_summary(articles, topic_name: str) -> str:
    """Prepare a structured summary of article data for the timeline prompt"""
    
    if not articles:
        return "No articles available for analysis."
    
    # Group articles by categories and extract key information
    summary_parts = []
    
    # Sample of recent articles with key details
    sample_articles = articles[:20]  # Take top 20 for detailed context
    
    summary_parts.append(f"**Recent Article Examples for {topic_name}:**")
    
    for i, article in enumerate(sample_articles, 1):
        title = article[1] if len(article) > 1 else "No title"
        summary = article[2] if len(article) > 2 else "No summary"
        future_signal = article[3] if len(article) > 3 else "No signal"
        sentiment = article[4] if len(article) > 4 else "Neutral"
        time_to_impact = article[5] if len(article) > 5 else "Unknown"
        publication_date = article[8] if len(article) > 8 else "Unknown"
        news_source = article[9] if len(article) > 9 else "Unknown"
        
        # Extract first sentence or key point from summary
        key_point = summary.split('.')[0][:150] + "..." if summary and len(summary) > 150 else summary
        
        summary_parts.append(f"""
{i}. **{title[:80]}{'...' if len(title) > 80 else ''}**
   - Source: {news_source} ({publication_date[:10] if publication_date else 'Recent'})
   - Key Point: {key_point}
   - Future Signal: {future_signal}
   - Sentiment: {sentiment}
   - Time to Impact: {time_to_impact}
""")
        
        if i >= 15:  # Limit to prevent token overflow
            break
    
    # Add article statistics
    total_articles = len(articles)
    summary_parts.append(f"""
**Article Analysis Context:**
- Total articles analyzed: {total_articles}
- Sample shown above: {min(15, total_articles)} most recent articles
- Use these examples to ground your timeline analysis in real evidence
- Reference specific developments, companies, and trends mentioned in articles
- Ensure milestone timings reflect the evidence from these articles
""")
    
    return "\n".join(summary_parts)
    
    # Analyze patterns in the data
    sentiments = []
    categories = []
    drivers = []
    signals = []
    time_impacts = []
    
    sample_articles = []
    
    for article in articles[:30]:  # Limit to avoid token limits
        if article[4]:  # sentiment
            sentiments.append(article[4])
        if article[7]:  # category
            categories.append(article[7])
        if article[6]:  # driver_type
            drivers.append(article[6])
        if article[3]:  # future_signal
            signals.append(article[3])
        if article[5]:  # time_to_impact
            time_impacts.append(article[5])
        
        # Add article summary for context
        if article[2]:  # summary
            sample_articles.append(f"- {article[1]}: {article[2][:150]}...")
    
    # Count frequencies
    from collections import Counter
    sentiment_counts = Counter(sentiments)
    category_counts = Counter(categories)
    driver_counts = Counter(drivers)
    signal_counts = Counter(signals)
    time_impact_counts = Counter(time_impacts)
    
    # Build analysis summary
    summary = f"""**Data Overview:**
- Total articles: {len(articles)}
- Topic: {topic_name}
- Date range: {articles[-1][8][:10] if articles and articles[-1][8] else 'Unknown'} to {articles[0][8][:10] if articles and articles[0][8] else 'Unknown'}

**Key Patterns:**
- Sentiments: {', '.join([f"{s}: {c}" for s, c in sentiment_counts.most_common(3)])}
- Time to Impact: {', '.join([f"{t}: {c}" for t, c in time_impact_counts.most_common(3)])}
- Future Signals: {', '.join([f"{sig}: {c}" for sig, c in signal_counts.most_common(3)])}
- Categories: {', '.join([f"{cat}: {c}" for cat, c in category_counts.most_common(3)])}

**Recent Article Highlights:**
{chr(10).join(sample_articles[:8])}
"""
    
    return summary

 