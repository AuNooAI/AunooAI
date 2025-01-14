import sqlite3
from datetime import datetime, timedelta
import logging

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

class AnalyzeDB:
    def __init__(self, db):
        self.db = db

    def get_sentiment_distribution(self, timeframe, category, topic):
        """Get sentiment distribution with topic support."""
        query_conditions = []
        params = []
        
        if timeframe != 'all':
            days = int(timeframe)
            query_conditions.append("submission_date >= date('now', ?)")
            params.append(f'-{days} days')
        
        if category:
            query_conditions.append("category = ?")
            params.append(category)
            
        if topic:
            query_conditions.append("topic = ?")
            params.append(topic)

        where_clause = " AND ".join(query_conditions) if query_conditions else "1=1"
        
        query = f"""
            SELECT sentiment, COUNT(*) as count
            FROM articles
            WHERE {where_clause}
            GROUP BY sentiment
        """
        
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            results = cursor.fetchall()
            
        labels = [row[0] for row in results]
        values = [row[1] for row in results]
        
        return {"labels": labels, "values": values}

    def get_time_to_impact_distribution(self, timeframe, category, topic):
        """Get time to impact distribution with topic support."""
        query_conditions = []
        params = []
        
        if timeframe != 'all':
            days = int(timeframe)
            query_conditions.append("submission_date >= date('now', ?)")
            params.append(f'-{days} days')
        
        if category:
            query_conditions.append("category = ?")
            params.append(category)
            
        if topic:
            query_conditions.append("topic = ?")
            params.append(topic)

        where_clause = " AND ".join(query_conditions) if query_conditions else "1=1"
        
        query = f"""
            SELECT time_to_impact, COUNT(*) as count
            FROM articles
            WHERE {where_clause}
            GROUP BY time_to_impact
        """
        
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            results = cursor.fetchall()
            
        labels = [row[0] for row in results]
        values = [row[1] for row in results]
        
        return {"labels": labels, "values": values}

    def get_future_signal_distribution(self, timeframe, category, topic):
        """Get future signal distribution with topic support."""
        query_conditions = []
        params = []
        
        if timeframe != 'all':
            days = int(timeframe)
            query_conditions.append("submission_date >= date('now', ?)")
            params.append(f'-{days} days')
        
        if category:
            query_conditions.append("category = ?")
            params.append(category)
            
        if topic:
            query_conditions.append("topic = ?")
            params.append(topic)

        where_clause = " AND ".join(query_conditions) if query_conditions else "1=1"
        
        query = f"""
            SELECT future_signal, COUNT(*) as count
            FROM articles
            WHERE {where_clause}
            GROUP BY future_signal
        """
        
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            results = cursor.fetchall()
            
        labels = [row[0] for row in results]
        values = [row[1] for row in results]
        
        return {"labels": labels, "values": values}

    def get_sentiment_by_category(self, timeframe, topic):
        """Get sentiment distribution by category with topic support."""
        query_conditions = []
        params = []
        
        if timeframe != 'all':
            days = int(timeframe)
            query_conditions.append("submission_date >= date('now', ?)")
            params.append(f'-{days} days')
            
        if topic:
            query_conditions.append("topic = ?")
            params.append(topic)

        where_clause = " AND ".join(query_conditions) if query_conditions else "1=1"
        
        query = f"""
            SELECT category, sentiment, COUNT(*) as count
            FROM articles
            WHERE {where_clause}
            GROUP BY category, sentiment
        """
        
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            results = cursor.fetchall()
            
        categories = list(set(row[0] for row in results))
        sentiments = list(set(row[1] for row in results))
        
        data = {category: {sentiment: 0 for sentiment in sentiments} for category in categories}
        for row in results:
            data[row[0]][row[1]] = row[2]
            
        return {
            "categories": categories,
            "sentiments": sentiments,
            "data": data
        }

    def get_future_signal_by_category(self, timeframe, topic):
        """Get future signal distribution by category with topic support."""
        query_conditions = []
        params = []
        
        if timeframe != 'all':
            days = int(timeframe)
            query_conditions.append("submission_date >= date('now', ?)")
            params.append(f'-{days} days')
            
        if topic:
            query_conditions.append("topic = ?")
            params.append(topic)

        where_clause = " AND ".join(query_conditions) if query_conditions else "1=1"
        
        query = f"""
            SELECT category, future_signal, COUNT(*) as count
            FROM articles
            WHERE {where_clause}
            GROUP BY category, future_signal
        """
        
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            results = cursor.fetchall()
            
        categories = list(set(row[0] for row in results))
        future_signals = list(set(row[1] for row in results))
        
        data = {category: {signal: 0 for signal in future_signals} for category in categories}
        for row in results:
            data[row[0]][row[1]] = row[2]
            
        return {
            "categories": categories,
            "future_signals": future_signals,
            "data": data
        }

    def get_radar_chart_data(self, timeframe, category, topic):
        """Get data for radar chart with topic support."""
        query_conditions = []
        params = []
        
        if timeframe != 'all':
            days = int(timeframe)
            query_conditions.append("submission_date >= date('now', ?)")
            params.append(f'-{days} days')
        
        if category:
            query_conditions.append("category = ?")
            params.append(category)
            
        if topic:
            query_conditions.append("topic = ?")
            params.append(topic)

        where_clause = " AND ".join(query_conditions) if query_conditions else "1=1"
        
        query = f"""
            SELECT future_signal, sentiment, time_to_impact, COUNT(*) as count
            FROM articles
            WHERE {where_clause}
            GROUP BY future_signal, sentiment, time_to_impact
        """
        
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            results = cursor.fetchall()
            
        return [{"future_signal": row[0], "sentiment": row[1], "time_to_impact": row[2], "count": row[3]} for row in results]

    def get_integrated_analysis(self, timeframe, category, topic=None):
        """Get integrated analysis data with topic support."""
        query = """
        SELECT COALESCE(driver_type, 'Unknown') as driver_type, 
               time_to_impact, sentiment, future_signal, COUNT(*) as count
        FROM articles
        WHERE 1=1
        """
        params = []

        if timeframe != 'all':
            days = int(timeframe)
            query += " AND submission_date >= date('now', ?)"
            params.append(f'-{days} days')

        if category:
            query += " AND category = ?"
            params.append(category)

        if topic:
            query += " AND topic = ?"
            params.append(topic)

        query += " GROUP BY driver_type, time_to_impact, sentiment, future_signal"

        logger.info(f"Executing query: {query} with params: {params}")
        
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            results = cursor.fetchall()

        data = [
            {
                'driver_type': row[0],
                'time_to_impact': row[1],
                'sentiment': row[2],
                'future_signal': row[3],
                'count': row[4]
            } for row in results
        ]
        
        logger.info(f"Processed data: {data}")
        return data

    def _add_timeframe_filter(self, query, params, timeframe, date_field='submission_date'):
        if timeframe != 'all':
            days = int(timeframe)
            query += f" AND {date_field} >= ?"
            params.append((datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d'))
        return query, params

    def _add_timeframe_and_category_filters(self, query, params, timeframe, category, date_field='submission_date'):
        query, params = self._add_timeframe_filter(query, params, timeframe, date_field)
        if category and category != 'all':
            query += " AND category = ?"
            params.append(category)
        return query, params

    def get_articles_by_future_signal_and_sentiment(self, timeframe, category, topic=None):
        """Get articles grouped by future signal and sentiment with topic support."""
        query = """
        SELECT future_signal, sentiment, COUNT(*) as count
        FROM articles
        WHERE 1=1
        """
        params = []

        if timeframe != 'all':
            days = int(timeframe)
            query += " AND submission_date >= date('now', ?)"
            params.append(f'-{days} days')

        if category:
            query += " AND category = ?"
            params.append(category)

        if topic:
            query += " AND topic = ?"
            params.append(topic)

        query += " GROUP BY future_signal, sentiment"

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            results = cursor.fetchall()
        
        data = [
            {
                'future_signal': row[0],
                'sentiment': row[1],
                'count': row[2]
            } for row in results
        ]

        return data

    def get_articles_by_future_signal_and_time_to_impact(self, timeframe, category, topic=None):
        """Get articles grouped by future signal and time to impact with topic support."""
        query = """
        SELECT future_signal, time_to_impact, COUNT(*) as count
        FROM articles
        WHERE 1=1
        """
        params = []

        if timeframe != 'all':
            days = int(timeframe)
            query += " AND submission_date >= date('now', ?)"
            params.append(f'-{days} days')

        if category:
            query += " AND category = ?"
            params.append(category)

        if topic:
            query += " AND topic = ?"
            params.append(topic)

        query += " GROUP BY future_signal, time_to_impact"

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            results = cursor.fetchall()
        
        data = [
            {
                'future_signal': row[0],
                'time_to_impact': row[1],
                'count': row[2]
            } for row in results
        ]

        return data
