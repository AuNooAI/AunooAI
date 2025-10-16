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

    def get_sentiment_distribution(self, timeframe, category, topic, *, sentiment=None,
                                   time_to_impact=None, driver_type=None, curated=True):
        """Get sentiment distribution with optional filters."""
        where_clause, params = self._build_filters(timeframe, category, topic, sentiment,
                                                   time_to_impact, driver_type, curated)

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

    def get_time_to_impact_distribution(self, timeframe, category, topic, *, sentiment=None,
                                        time_to_impact=None, driver_type=None, curated=True):
        """Get time-to-impact distribution with optional filters."""
        where_clause, params = self._build_filters(timeframe, category, topic, sentiment,
                                                   time_to_impact, driver_type, curated)

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

    def get_future_signal_distribution(self, timeframe, category, topic, *, sentiment=None,
                                        time_to_impact=None, driver_type=None, curated=True):
        """Get future-signal distribution with optional filters."""
        where_clause, params = self._build_filters(timeframe, category, topic, sentiment,
                                                   time_to_impact, driver_type, curated)

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

    def get_sentiment_by_category(self, timeframe, topic, *, sentiment=None,
                                   time_to_impact=None, driver_type=None, curated=True):
        """Get sentiment distribution by category with optional filters."""
        where_clause, params = self._build_filters(timeframe, None, topic, sentiment,
                                                   time_to_impact, driver_type, curated)

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

    def get_future_signal_by_category(self, timeframe, topic, *, sentiment=None,
                                       time_to_impact=None, driver_type=None, curated=True):
        """Get future-signal distribution by category with optional filters."""
        where_clause, params = self._build_filters(timeframe, None, topic, sentiment,
                                                   time_to_impact, driver_type, curated)

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

    def get_radar_chart_data(self, timeframe, category, topic, *, sentiment=None,
                              time_to_impact=None, driver_type=None, curated=True):
        """Get data for radar chart with optional filters."""
        where_clause, params = self._build_filters(timeframe, category, topic, sentiment,
                                                   time_to_impact, driver_type, curated)

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
        if category and isinstance(category, str):
            query += " AND category = ?"
            params.append(category)
        elif category and isinstance(category, list) and category:
            placeholders = ', '.join(['?' for _ in category])
            query += f" AND category IN ({placeholders})"
            params.extend(category)
        return query, params

    def get_articles_by_future_signal_and_sentiment(self, timeframe, category, topic=None,
                                                    *, sentiment=None, time_to_impact=None,
                                                    driver_type=None, curated=True):
        """Get aggregated counts grouped by future signal and sentiment."""
        where_clause, params = self._build_filters(timeframe, category, topic, sentiment,
                                                   time_to_impact, driver_type, curated)

        query = f"""
            SELECT future_signal, sentiment, COUNT(*) as count
            FROM articles
            WHERE {where_clause}
            GROUP BY future_signal, sentiment
        """

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            results = cursor.fetchall()

        return [{
            'future_signal': row[0],
            'sentiment': row[1],
            'count': row[2]
        } for row in results]

    def get_articles_by_future_signal_and_time_to_impact(self, timeframe, category, topic=None,
                                                         *, sentiment=None, time_to_impact=None,
                                                         driver_type=None, curated=True):
        """Get aggregated counts grouped by future signal and time to impact."""
        where_clause, params = self._build_filters(timeframe, category, topic, sentiment,
                                                   time_to_impact, driver_type, curated)

        query = f"""
            SELECT future_signal, time_to_impact, COUNT(*) as count
            FROM articles
            WHERE {where_clause}
            GROUP BY future_signal, time_to_impact
        """

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            results = cursor.fetchall()

        return [{
            'future_signal': row[0],
            'time_to_impact': row[1],
            'count': row[2]
        } for row in results]

    # ----------------------
    # Helper utilities
    # ----------------------
    def _build_filters(self, timeframe: str, category: str = None, topic: str = None,
                       sentiment: str = None, time_to_impact: str = None,
                       driver_type: str = None, curated: bool = True):
        """Build SQL WHERE clause and params list based on provided filters."""
        conditions: list[str] = []
        params: list[str] = []

        # Timeframe filter
        if timeframe and timeframe != 'all':
            days = int(timeframe)
            conditions.append("submission_date >= date('now', ?)")
            params.append(f'-{days} days')

        # Category filter (support list or single value)
        if category and isinstance(category, str):
            conditions.append("category = ?")
            params.append(category)
        elif category and isinstance(category, list) and category:
            placeholders = ', '.join(['?' for _ in category])
            conditions.append(f"category IN ({placeholders})")
            params.extend(category)

        # Topic filter
        if topic:
            conditions.append("topic = ?")
            params.append(topic)

        # Additional optional filters
        if sentiment and isinstance(sentiment, str):
            conditions.append("sentiment = ?")
            params.append(sentiment)
        elif sentiment and isinstance(sentiment, list) and sentiment:
            placeholders = ', '.join(['?' for _ in sentiment])
            conditions.append(f"sentiment IN ({placeholders})")
            params.extend(sentiment)

        if time_to_impact and isinstance(time_to_impact, str):
            conditions.append("time_to_impact = ?")
            params.append(time_to_impact)
        elif time_to_impact and isinstance(time_to_impact, list) and time_to_impact:
            placeholders = ', '.join(['?' for _ in time_to_impact])
            conditions.append(f"time_to_impact IN ({placeholders})")
            params.extend(time_to_impact)

        if driver_type and isinstance(driver_type, str):
            conditions.append("driver_type = ?")
            params.append(driver_type)
        elif driver_type and isinstance(driver_type, list) and driver_type:
            placeholders = ', '.join(['?' for _ in driver_type])
            conditions.append(f"driver_type IN ({placeholders})")
            params.extend(driver_type)

        # Curated filter – ensure articles have a category defined
        if curated:
            conditions.append("category IS NOT NULL AND category != ''")

        # Construct WHERE clause
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        return where_clause, params

    # ----------------------
    # Time-series helpers
    # ----------------------

    def get_sentiment_timeseries(self, timeframe, category, topic, *, sentiment=None,
                                 time_to_impact=None, driver_type=None, curated=True):
        """Sentiment counts grouped by date."""
        where_clause, params = self._build_filters(timeframe, category, topic, sentiment,
                                                   time_to_impact, driver_type, curated)

        query = f"""
            SELECT DATE(submission_date) as date, sentiment, COUNT(*) as count
            FROM articles
            WHERE {where_clause}
            GROUP BY DATE(submission_date), sentiment
            ORDER BY DATE(submission_date)
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            results = cursor.fetchall()

        return [{
            'date': row[0],
            'sentiment': row[1],
            'count': row[2]
        } for row in results]

    def get_category_timeseries(self, timeframe, category, topic, *, sentiment=None,
                                time_to_impact=None, driver_type=None, curated=True):
        """Category counts grouped by date."""
        where_clause, params = self._build_filters(timeframe, category, topic, sentiment,
                                                   time_to_impact, driver_type, curated)

        query = f"""
            SELECT DATE(submission_date) as date, category, COUNT(*) as count
            FROM articles
            WHERE {where_clause}
            GROUP BY DATE(submission_date), category
            ORDER BY DATE(submission_date)
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            results = cursor.fetchall()

        return [{
            'date': row[0],
            'category': row[1],
            'count': row[2]
        } for row in results]

    # ----------------------
    # Topic Options Helper
    # ----------------------

    def get_topic_options(self, topic: str):
        """Return distinct lists of categories, future signals, sentiments, time-to-impact, and driver types available for a given topic."""
        from sqlalchemy import text

        query = text("""
        SELECT DISTINCT
            category,
            future_signal,
            sentiment,
            time_to_impact,
            driver_type
        FROM articles
        WHERE topic = :topic
        """)

        conn = self.db._temp_get_connection()
        result = conn.execute(query, {"topic": topic})
        results = result.fetchall()

        categories = sorted({row[0] for row in results if row[0]})
        future_signals = sorted({row[1] for row in results if row[1]})
        sentiments = sorted({row[2] for row in results if row[2]})
        time_to_impacts = sorted({row[3] for row in results if row[3]})
        driver_types = sorted({row[4] for row in results if row[4]})

        return {
            "categories": categories,
            "futureSignals": future_signals,
            "sentiments": sentiments,
            "timeToImpacts": time_to_impacts,
            "driverTypes": driver_types
        }
