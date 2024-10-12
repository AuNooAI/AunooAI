import logging

logger = logging.getLogger(__name__)

from analyze_db import AnalyzeDB

class Analytics:
    def __init__(self, db):
        self.db = AnalyzeDB(db)

    def get_analytics_data(self, timeframe, category):
        sentiment_distribution = self.db.get_sentiment_distribution(timeframe, category)
        time_to_impact_distribution = self.db.get_time_to_impact_distribution(timeframe, category)
        future_signal_distribution = self.db.get_future_signal_distribution(timeframe, category)
        sentiment_by_category = self.db.get_sentiment_by_category(timeframe)
        future_signal_by_category = self.db.get_future_signal_by_category(timeframe)
        
        # Calculate total article count
        total_articles = sum(sentiment_distribution['values'])
        
        articles_bubble_chart = self.db.get_articles_by_future_signal_and_sentiment(timeframe, category)
        articles_future_time_bubble_chart = self.db.get_articles_by_future_signal_and_time_to_impact(timeframe, category)
        
        radar_chart_data = self.db.get_radar_chart_data(timeframe, category)
        
        return {
            "sentimentDistribution": sentiment_distribution,
            "timeToImpactDistribution": time_to_impact_distribution,
            "futureSignalDistribution": future_signal_distribution,
            "sentimentByCategory": sentiment_by_category,
            "futureSignalByCategory": future_signal_by_category,
            "totalArticles": total_articles,
            "articlesBubbleChart": articles_bubble_chart,
            "articlesFutureTimeBubbleChart": articles_future_time_bubble_chart,
            "radarChartData": radar_chart_data
        }
