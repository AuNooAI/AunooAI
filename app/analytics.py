import logging
from app.database import Database
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

    def get_analytics_data(
        self,
        timeframe: str,
        category: str = None,
        topic: str = None,
        *,
        sentiment: str = None,
        time_to_impact: str = None,
        driver_type: str = None,
        curated: bool = True,
    ):
        """Get analytics data with extended filter support."""
        try:
            # Base filters dict for DRY
            filter_kwargs = {
                'sentiment': sentiment,
                'time_to_impact': time_to_impact,
                'driver_type': driver_type,
                'curated': curated,
            }

            # Get data with topic support and additional filters
            sentiment_distribution = self.db.get_sentiment_distribution(timeframe, category, topic, **filter_kwargs)
            time_to_impact_distribution = self.db.get_time_to_impact_distribution(timeframe, category, topic, **filter_kwargs)
            future_signal_distribution = self.db.get_future_signal_distribution(timeframe, category, topic, **filter_kwargs)
            sentiment_by_category = self.db.get_sentiment_by_category(timeframe, topic, **filter_kwargs)
            future_signal_by_category = self.db.get_future_signal_by_category(timeframe, topic, **filter_kwargs)
            
            # Calculate total article count
            total_articles = sum(sentiment_distribution['values'])
            
            articles_bubble_chart = self.db.get_articles_by_future_signal_and_sentiment(timeframe, category, topic, **filter_kwargs)
            articles_future_time_bubble_chart = self.db.get_articles_by_future_signal_and_time_to_impact(timeframe, category, topic, **filter_kwargs)
            
            radar_chart_data = self.db.get_radar_chart_data(timeframe, category, topic, **filter_kwargs)

            # Time-series data
            sentiment_timeseries = self.db.get_sentiment_timeseries(timeframe, category, topic, **filter_kwargs)
            category_timeseries = self.db.get_category_timeseries(timeframe, category, topic, **filter_kwargs)
            
            logger.info(f"Analytics data for timeframe={timeframe}, category={category}, topic={topic}:")
            logger.info(f"Total articles: {total_articles}")
            logger.info(f"Sentiment distribution: {sentiment_distribution}")
            logger.info(f"Time to impact distribution: {time_to_impact_distribution}")
            logger.info(f"Future signal distribution: {future_signal_distribution}")
            
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
                "sentimentTimeSeries": sentiment_timeseries,
                "categoryTimeSeries": category_timeseries
            }
        except Exception as e:
            logger.error(f"Error in get_analytics_data: {str(e)}", exc_info=True)
            raise
