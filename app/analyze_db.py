import sqlite3
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class AnalyzeDB:
    def __init__(self, db):
        self.db = db

    def get_sentiment_distribution(self, timeframe, category):
        query = """
        SELECT sentiment, COUNT(*) as count
        FROM articles
        WHERE 1=1
        """
        params = []


        query, params = self._add_timeframe_and_category_filters(query, params, timeframe, category)

        query += " GROUP BY sentiment"

        results = self.db.fetch_all(query, params)
        labels = [row['sentiment'] for row in results]
        values = [row['count'] for row in results]

        return {"labels": labels, "values": values}

    def _add_timeframe_filter(self, query, params, timeframe):
        if timeframe != 'all':
            days = int(timeframe)
            query += " AND publication_date >= ?"
            params.append((datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d'))
        return query, params

    def _add_timeframe_and_category_filters(self, query, params, timeframe, category):
        query, params = self._add_timeframe_filter(query, params, timeframe)
        if category != 'all':
            query += " AND category = ?"
            params.append(category)
        return query, params

    def get_time_to_impact_distribution(self, timeframe, category):
        query = """
        SELECT time_to_impact, COUNT(*) as count
        FROM articles
        WHERE 1=1
        """
        params = []

        query, params = self._add_timeframe_and_category_filters(query, params, timeframe, category)

        query += " GROUP BY time_to_impact"

        logger.info(f"Executing query: {query} with params: {params}")
        results = self.db.fetch_all(query, params)
        logger.info(f"Query results: {results}")

        labels = [row['time_to_impact'] for row in results]
        values = [row['count'] for row in results]

        logger.info(f"Time to Impact Distribution: labels={labels}, values={values}")

        return {"labels": labels, "values": values}

    def get_future_signal_distribution(self, timeframe, category):
        query = """
        SELECT future_signal, COUNT(*) as count
        FROM articles
        WHERE 1=1
        """
        params = []

        query, params = self._add_timeframe_and_category_filters(query, params, timeframe, category)

        query += " GROUP BY future_signal"

        results = self.db.fetch_all(query, params)
        labels = [row['future_signal'] for row in results]
        values = [row['count'] for row in results]

        return {"labels": labels, "values": values}

    def get_sentiment_by_category(self, timeframe):
        query = """
        SELECT category, sentiment, COUNT(*) as count
        FROM articles
        WHERE 1=1
        """
        params = []

        query, params = self._add_timeframe_filter(query, params, timeframe)

        query += " GROUP BY category, sentiment"

        results = self.db.fetch_all(query, params)
        categories = list(set(row['category'] for row in results))
        sentiments = ['Positive', 'Neutral', 'Negative', 'Critical']
        
        data = {category: {sentiment: 0 for sentiment in sentiments} for category in categories}
        for row in results:
            data[row['category']][row['sentiment']] = row['count']

        return {"categories": categories, "sentiments": sentiments, "data": data}

    def get_future_signal_by_category(self, timeframe):
        query = """
        SELECT category, future_signal, COUNT(*) as count
        FROM articles
        WHERE 1=1
        """
        params = []

        query, params = self._add_timeframe_filter(query, params, timeframe)

        query += " GROUP BY category, future_signal"

        results = self.db.fetch_all(query, params)
        categories = list(set(row['category'] for row in results))
        future_signals = ['AI will accelerate', 'AI will evolve gradually', 'AI is hype', 'AI has plateaued']
        
        data = {category: {signal: 0 for signal in future_signals} for category in categories}
        for row in results:
            data[row['category']][row['future_signal']] = row['count']

        return {"categories": categories, "future_signals": future_signals, "data": data}

    def get_articles_by_future_signal_and_sentiment(self, timeframe, category):
        query = """
        SELECT future_signal, sentiment, COUNT(*) as count
        FROM articles
        WHERE 1=1
        """
        params = []

        query, params = self._add_timeframe_and_category_filters(query, params, timeframe, category)

        query += " GROUP BY future_signal, sentiment"

        results = self.db.fetch_all(query, params)
        
        data = [
            {
                'future_signal': row['future_signal'],
                'sentiment': row['sentiment'],
                'count': row['count']
            } for row in results
        ]

        return data

    def get_articles_by_future_signal_and_time_to_impact(self, timeframe, category):
        query = """
        SELECT future_signal, time_to_impact, COUNT(*) as count
        FROM articles
        WHERE 1=1
        """
        params = []

        query, params = self._add_timeframe_and_category_filters(query, params, timeframe, category)

        query += " GROUP BY future_signal, time_to_impact"

        results = self.db.fetch_all(query, params)
        
        data = [
            {
                'future_signal': row['future_signal'],
                'time_to_impact': row['time_to_impact'],
                'count': row['count']
            } for row in results
        ]

        return data

    def get_radar_chart_data(self, timeframe, category):
        query = """
        SELECT future_signal, sentiment, time_to_impact, COUNT(*) as count
        FROM articles
        WHERE 1=1
        """
        params = []

        query, params = self._add_timeframe_and_category_filters(query, params, timeframe, category)

        query += " GROUP BY future_signal, sentiment, time_to_impact"

        results = self.db.fetch_all(query, params)
        
        data = [
            {
                'future_signal': row['future_signal'],
                'sentiment': row['sentiment'],
                'time_to_impact': row['time_to_impact'],
                'count': row['count']
            } for row in results
        ]

        return data

    def get_integrated_analysis(self, timeframe, category):
        query = """
        SELECT COALESCE(driver_type, 'Unknown') as driver_type, 
               time_to_impact, sentiment, future_signal, COUNT(*) as count
        FROM articles
        WHERE 1=1
        """
        params = []

        if timeframe != 'all':
            days = int(timeframe)
            query += " AND submission_date >= date('now', ?);"
            params.append(f'-{days} days')

        if category and category != 'all':
            query += " AND category = ?"
            params.append(category)

        query += " GROUP BY driver_type, time_to_impact, sentiment, future_signal"

        logger.info(f"Executing query: {query} with params: {params}")
        results = self.db.fetch_all(query, params)
        logger.info(f"Query results: {results}")

        data = [
            {
                'driver_type': row['driver_type'],
                'time_to_impact': row['time_to_impact'],
                'sentiment': row['sentiment'],
                'future_signal': row['future_signal'],
                'count': row['count']
            } for row in results
        ]

        logger.info(f"Processed data: {data}")
        return data