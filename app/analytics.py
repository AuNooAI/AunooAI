from typing import List, Dict, Optional
from datetime import datetime, timedelta
import logging
from app.database import Database, get_database_instance
from app.analyze_db import AnalyzeDB

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

class Analytics:
    def __init__(self, db: Database):
        self.db = AnalyzeDB(db)

    def get_analytics_data(self, timeframe: str, category: str = None, topic: str = None):
        """Get analytics data filtered by timeframe, category, and topic."""
        try:
            # Get data with topic support
            sentiment_distribution = self.db.get_sentiment_distribution(timeframe, category, topic)
            time_to_impact_distribution = self.db.get_time_to_impact_distribution(timeframe, category, topic)
            future_signal_distribution = self.db.get_future_signal_distribution(timeframe, category, topic)
            sentiment_by_category = self.db.get_sentiment_by_category(timeframe, topic)  # Add topic parameter
            future_signal_by_category = self.db.get_future_signal_by_category(timeframe, topic)  # Add topic parameter
            
            # Calculate total article count
            total_articles = sum(sentiment_distribution['values'])
            
            articles_bubble_chart = self.db.get_articles_by_future_signal_and_sentiment(timeframe, category, topic)
            articles_future_time_bubble_chart = self.db.get_articles_by_future_signal_and_time_to_impact(timeframe, category, topic)
            
            radar_chart_data = self.db.get_radar_chart_data(timeframe, category, topic)  # Add topic parameter
            integrated_analysis = self.db.get_integrated_analysis(timeframe, category, topic)  # Add integrated analysis
            
            logger.info(f"Analytics data for timeframe={timeframe}, category={category}, topic={topic}:")
            logger.info(f"Total articles: {total_articles}")
            logger.info(f"Sentiment distribution: {sentiment_distribution}")
            logger.info(f"Time to impact distribution: {time_to_impact_distribution}")
            logger.info(f"Future signal distribution: {future_signal_distribution}")
            logger.info(f"Integrated analysis data: {integrated_analysis}")
            
            return {
                "sentimentDistribution": sentiment_distribution,
                "timeToImpactDistribution": time_to_impact_distribution,
                "futureSignalDistribution": future_signal_distribution,
                "sentimentByCategory": sentiment_by_category,
                "futureSignalByCategory": future_signal_by_category,
                "totalArticles": total_articles,
                "articlesBubbleChart": articles_bubble_chart,
                "articlesFutureTimeBubbleChart": articles_future_time_bubble_chart,
                "radarChartData": radar_chart_data,
                "integratedAnalysis": integrated_analysis
            }
        except Exception as e:
            logger.error(f"Error in get_analytics_data: {str(e)}", exc_info=True)
            raise
