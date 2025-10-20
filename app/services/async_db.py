import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import logging
from app.config.settings import DATABASE_DIR

logger = logging.getLogger(__name__)

class AsyncDatabase:
    """Async wrapper for database operations with connection pooling"""

    def __init__(self, db_name: str = None):
        self.db_type = os.getenv('DB_TYPE', 'sqlite').lower()

        if self.db_type == 'postgresql':
            # PostgreSQL setup
            from app.config.settings import db_settings
            # asyncpg uses 'postgresql://' not 'postgresql+asyncpg://'
            self.database_url = db_settings.get_database_url().replace('postgresql+asyncpg://', 'postgresql://')
            self._pool = None
            self._pool_size = 10
            logger.info(f"AsyncDatabase initialized for PostgreSQL: {db_settings.DB_NAME}")
        else:
            # SQLite setup (backward compatibility)
            import aiosqlite
            if db_name is None:
                # Get active database from config
                config_path = os.path.join(DATABASE_DIR, 'config.json')
                with open(config_path, 'r') as f:
                    config = json.load(f)
                db_name = config.get('active_database', 'fnaapp.db')

            self.db_path = os.path.join(DATABASE_DIR, db_name)
            self._connection_pool = asyncio.Queue(maxsize=10)
            self._pool_size = 5
            logger.info(f"AsyncDatabase initialized for SQLite: {db_name}")

        self._initialized = False

    def _convert_query_params(self, query: str, params: Tuple) -> Tuple[str, Any]:
        """Convert SQLite-style ? placeholders to PostgreSQL-style $1, $2, etc."""
        if self.db_type != 'postgresql' or '?' not in query:
            return query, params

        # Convert ? to $1, $2, etc.
        param_count = query.count('?')
        for i in range(1, param_count + 1):
            query = query.replace('?', f'${i}', 1)

        return query, params

    async def initialize_pool(self):
        """Initialize connection pool"""
        if self._initialized:
            return

        if self.db_type == 'postgresql':
            # PostgreSQL connection pool using asyncpg
            import asyncpg
            logger.info(f"Initializing PostgreSQL async pool with {self._pool_size} connections")

            self._pool = await asyncpg.create_pool(
                self.database_url,
                min_size=self._pool_size,
                max_size=self._pool_size * 2,
                command_timeout=60,
                timeout=30
            )
            logger.info("PostgreSQL async database pool initialized successfully")
        else:
            # SQLite connection pool
            import aiosqlite
            logger.info(f"Initializing SQLite async pool with {self._pool_size} connections")

            for i in range(self._pool_size):
                conn = await aiosqlite.connect(self.db_path)

                # Optimize SQLite for concurrent operations
                await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous=NORMAL")
                await conn.execute("PRAGMA cache_size=10000")
                await conn.execute("PRAGMA temp_store=MEMORY")
                await conn.execute("PRAGMA foreign_keys=ON")
                await conn.execute("PRAGMA busy_timeout=30000")

                await self._connection_pool.put(conn)
                logger.debug(f"Created async database connection {i+1}/{self._pool_size}")

            logger.info("SQLite async database pool initialized successfully")

        self._initialized = True
    
    @asynccontextmanager
    async def get_connection(self):
        """Get connection from pool with automatic return"""
        if not self._initialized:
            await self.initialize_pool()

        if self.db_type == 'postgresql':
            # PostgreSQL: acquire from pool
            async with self._pool.acquire() as conn:
                yield conn
        else:
            # SQLite: get from queue
            conn = await self._connection_pool.get()
            try:
                yield conn
            finally:
                await self._connection_pool.put(conn)
    
    async def execute_batch_updates(self, updates: List[Dict[str, Any]]) -> int:
        """Execute batch updates efficiently with transaction"""
        if not updates:
            return 0
            
        async with self.get_connection() as conn:
            updated_count = 0
            
            try:
                # Start transaction
                await conn.execute("BEGIN TRANSACTION")
                
                for update in updates:
                    cursor = await conn.execute(update['query'], update['params'])
                    updated_count += cursor.rowcount
                
                # Commit all updates
                await conn.commit()
                logger.debug(f"Batch updated {updated_count} records")
                
            except Exception as e:
                await conn.rollback()
                logger.error(f"Batch update failed, rolled back: {e}")
                raise
                
            return updated_count
    
    async def execute_single_update(self, query: str, params: Tuple = ()) -> int:
        """Execute a single update query"""
        query, params = self._convert_query_params(query, params)

        async with self.get_connection() as conn:
            try:
                if self.db_type == 'postgresql':
                    # PostgreSQL with asyncpg
                    result = await conn.execute(query, *params)
                    # Parse result like "UPDATE 1" to get row count
                    if result:
                        try:
                            # Log the result for debugging
                            logger.debug(f"PostgreSQL execute result: '{result}' (type: {type(result)})")
                            # Extract numeric value from result string
                            parts = result.split()
                            if parts:
                                # Get the last part and try to convert to int
                                last_part = parts[-1]
                                logger.debug(f"Parsed parts: {parts}, last_part: '{last_part}'")
                                return int(last_part)
                        except (ValueError, IndexError) as e:
                            logger.error(f"Could not parse row count from result '{result}': {e}")
                            logger.error(f"Result type: {type(result)}, Result repr: {repr(result)}")
                            # Return 1 to indicate success even if we can't parse the count
                            return 1
                    return 0
                else:
                    # SQLite with aiosqlite
                    cursor = await conn.execute(query, params)
                    await conn.commit()
                    return cursor.rowcount
            except Exception as e:
                logger.error(f"Single update failed: {e}")
                raise

    async def fetch_one(self, query: str, params: Tuple = ()) -> Optional[Dict[str, Any]]:
        """Fetch a single row as dictionary"""
        query, params = self._convert_query_params(query, params)

        async with self.get_connection() as conn:
            if self.db_type == 'postgresql':
                # PostgreSQL with asyncpg
                row = await conn.fetchrow(query, *params)
                return dict(row) if row else None
            else:
                # SQLite with aiosqlite
                import aiosqlite
                conn.row_factory = aiosqlite.Row
                cursor = await conn.execute(query, params)
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def fetch_all(self, query: str, params: Tuple = ()) -> List[Dict[str, Any]]:
        """Fetch all rows as list of dictionaries"""
        query, params = self._convert_query_params(query, params)

        async with self.get_connection() as conn:
            if self.db_type == 'postgresql':
                # PostgreSQL with asyncpg
                rows = await conn.fetch(query, *params)
                return [dict(row) for row in rows]
            else:
                # SQLite with aiosqlite
                import aiosqlite
                conn.row_factory = aiosqlite.Row
                cursor = await conn.execute(query, params)
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    async def update_article_with_enrichment(self, article_data: Dict[str, Any]) -> bool:
        """Update article with enrichment data efficiently"""

        # VALIDATION: Warn if placeholder title detected
        title = article_data.get("title")
        if title and title.startswith("Article from"):
            logger.warning(f"Placeholder title detected in enrichment data: {article_data.get('uri')}")
            logger.warning(f"Title: {title}")
            # Don't update with placeholder - let COALESCE keep existing
            article_data["title"] = None

        query = """
            UPDATE articles
            SET
                title = COALESCE(?, title),
                summary = COALESCE(?, summary),
                auto_ingested = 1,
                ingest_status = ?,
                quality_score = ?,
                quality_issues = ?,
                category = ?,
                sentiment = ?,
                bias = ?,
                factual_reporting = ?,
                mbfc_credibility_rating = ?,
                bias_source = ?,
                bias_country = ?,
                press_freedom = ?,
                media_type = ?,
                popularity = ?,
                topic_alignment_score = ?,
                keyword_relevance_score = ?,
                future_signal = ?,
                future_signal_explanation = ?,
                sentiment_explanation = ?,
                time_to_impact = ?,
                driver_type = ?,
                tags = ?,
                analyzed = ?,
                confidence_score = ?,
                overall_match_explanation = ?
            WHERE uri = ?
        """
        
        params = (
            article_data.get("title"),
            article_data.get("summary"),
            article_data.get("ingest_status"),
            article_data.get("quality_score"),
            article_data.get("quality_issues"),
            article_data.get("category"),
            article_data.get("sentiment"),
            article_data.get("bias"),
            article_data.get("factual_reporting"),
            article_data.get("mbfc_credibility_rating"),
            article_data.get("bias_source"),
            article_data.get("bias_country"),
            article_data.get("press_freedom"),
            article_data.get("media_type"),
            article_data.get("popularity"),
            article_data.get("topic_alignment_score"),
            article_data.get("keyword_relevance_score"),
            article_data.get("future_signal"),
            article_data.get("future_signal_explanation"),  
            article_data.get("sentiment_explanation"),
            article_data.get("time_to_impact"),
            article_data.get("driver_type"),
            article_data.get("tags"),
            article_data.get("analyzed", True),
            article_data.get("confidence_score"),
            article_data.get("overall_match_explanation"),
            article_data.get("uri")
        )
        
        try:
            rows_affected = await self.execute_single_update(query, params)
            return rows_affected > 0
        except Exception as e:
            logger.error(f"Failed to update article {article_data.get('uri')}: {e}")
            return False
    
    async def get_topic_articles(self, topic_id: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Get all articles and unprocessed articles for a topic"""
        
        # Check which table structure to use
        check_query = "SELECT name FROM sqlite_master WHERE type='table' AND name='keyword_article_matches'"
        table_exists = await self.fetch_one(check_query)
        use_new_table = table_exists is not None
        
        if use_new_table:
            # Use new table structure
            all_articles_query = """
                SELECT DISTINCT a.uri, a.title, a.summary, a.news_source, kg.topic
                FROM articles a
                JOIN keyword_article_matches ka ON a.uri = ka.article_uri
                JOIN keyword_groups kg ON ka.group_id = kg.id
                WHERE kg.topic = ?
                ORDER BY ka.detected_at DESC
            """
            
            unprocessed_query = """
                SELECT DISTINCT a.uri, a.title, a.summary, a.news_source, kg.topic
                FROM articles a
                JOIN keyword_article_matches ka ON a.uri = ka.article_uri
                JOIN keyword_groups kg ON ka.group_id = kg.id
                WHERE kg.topic = ?
                AND (a.auto_ingested IS NULL OR a.auto_ingested = 0)
                AND ka.is_read = 0
                ORDER BY ka.detected_at DESC
            """
        else:
            # Use old table structure
            all_articles_query = """
                SELECT DISTINCT a.uri, a.title, a.summary, a.news_source, kg.topic
                FROM articles a
                JOIN keyword_alerts ka ON a.uri = ka.article_uri
                JOIN monitored_keywords mk ON ka.keyword_id = mk.id
                JOIN keyword_groups kg ON mk.group_id = kg.id
                WHERE kg.topic = ?
                ORDER BY ka.detected_at DESC
            """
            
            unprocessed_query = """
                SELECT DISTINCT a.uri, a.title, a.summary, a.news_source, kg.topic
                FROM articles a
                JOIN keyword_alerts ka ON a.uri = ka.article_uri
                JOIN monitored_keywords mk ON ka.keyword_id = mk.id
                JOIN keyword_groups kg ON mk.group_id = kg.id
                WHERE kg.topic = ?
                AND (a.auto_ingested IS NULL OR a.auto_ingested = 0)
                AND ka.is_read = 0
                ORDER BY ka.detected_at DESC
            """
        
        # Execute both queries concurrently
        all_articles_task = self.fetch_all(all_articles_query, (topic_id,))
        unprocessed_articles_task = self.fetch_all(unprocessed_query, (topic_id,))
        
        all_articles, unprocessed_articles = await asyncio.gather(
            all_articles_task, unprocessed_articles_task
        )
        
        return all_articles, unprocessed_articles
    
    async def get_topic_keywords(self, topic_id: str) -> List[str]:
        """Get keywords for a topic"""
        query = """
            SELECT mk.keyword
            FROM monitored_keywords mk
            JOIN keyword_groups kg ON mk.group_id = kg.id
            WHERE kg.topic = ?
        """
        
        rows = await self.fetch_all(query, (topic_id,))
        return [row['keyword'] for row in rows]
    
    async def save_raw_article_async(self, uri: str, raw_markdown: str, topic: str):
        """Save raw article content asynchronously"""
        if self.db_type == 'postgresql':
            # PostgreSQL syntax with ON CONFLICT
            query = """
                INSERT INTO raw_articles (uri, raw_markdown, topic, last_updated)
                VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
                ON CONFLICT (uri) DO UPDATE SET
                    raw_markdown = $2,
                    topic = $3,
                    last_updated = CURRENT_TIMESTAMP
            """
        else:
            # SQLite syntax
            query = """
                INSERT OR REPLACE INTO raw_articles (uri, raw_markdown, topic, last_updated)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """

        await self.execute_single_update(query, (uri, raw_markdown, topic))
    
    async def get_raw_article_async(self, uri: str) -> Optional[Dict[str, Any]]:
        """Get raw article content asynchronously"""
        query = """
            SELECT uri, raw_markdown, topic, submission_date, last_updated
            FROM raw_articles
            WHERE uri = ?
        """

        return await self.fetch_one(query, (uri,))

    async def save_below_threshold_article(self, article_data: Dict[str, Any]) -> bool:
        """
        Save article that failed relevance threshold with its scores.
        This ensures the article exists in the articles table so it can be visible in the UI.
        """
        # Convert datetime to string if needed
        publication_date = article_data.get("publication_date")
        if publication_date and hasattr(publication_date, 'isoformat'):
            # It's a datetime object, convert to ISO string
            publication_date = publication_date.isoformat()

        if self.db_type == 'postgresql':
            # PostgreSQL syntax with ON CONFLICT
            query = """
                INSERT INTO articles (
                    uri, title, summary, news_source, publication_date, topic,
                    topic_alignment_score, keyword_relevance_score, confidence_score,
                    overall_match_explanation, analyzed, ingest_status
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                ON CONFLICT (uri) DO UPDATE SET
                    topic_alignment_score = $7,
                    keyword_relevance_score = $8,
                    confidence_score = $9,
                    overall_match_explanation = $10,
                    ingest_status = $12
            """
        else:
            # SQLite syntax
            query = """
                INSERT OR REPLACE INTO articles (
                    uri, title, summary, news_source, publication_date, topic,
                    topic_alignment_score, keyword_relevance_score, confidence_score,
                    overall_match_explanation, analyzed, ingest_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """

        params = (
            article_data.get("uri"),
            article_data.get("title"),
            article_data.get("summary"),
            article_data.get("news_source"),
            publication_date,  # Use converted string value
            article_data.get("topic"),
            article_data.get("topic_alignment_score"),
            article_data.get("keyword_relevance_score"),
            article_data.get("confidence_score"),
            article_data.get("overall_match_explanation"),
            False,  # analyzed = False for below-threshold articles
            "filtered_relevance"  # ingest_status to indicate why it was filtered
        )

        try:
            rows_affected = await self.execute_single_update(query, params)
            return rows_affected > 0
        except Exception as e:
            logger.error(f"Failed to save below-threshold article {article_data.get('uri')}: {e}")
            return False

    async def close_pool(self):
        """Close all connections in the pool"""
        if not self._initialized:
            return

        logger.info("Closing async database connection pool")

        if self.db_type == 'postgresql':
            # PostgreSQL: close asyncpg pool
            if self._pool:
                await self._pool.close()
                logger.info("PostgreSQL async pool closed")
        else:
            # SQLite: close all connections in queue
            while not self._connection_pool.empty():
                try:
                    conn = await asyncio.wait_for(self._connection_pool.get(), timeout=1.0)
                    await conn.close()
                except asyncio.TimeoutError:
                    break
                except Exception as e:
                    logger.error(f"Error closing connection: {e}")

        self._initialized = False
        logger.info("Async database pool closed")

# Global instance for dependency injection
_async_db_instance = None

def get_async_database_instance() -> AsyncDatabase:
    """Get the global async database instance"""
    global _async_db_instance
    if _async_db_instance is None:
        _async_db_instance = AsyncDatabase()
    return _async_db_instance

async def initialize_async_db():
    """Initialize the async database pool"""
    db = get_async_database_instance()
    await db.initialize_pool()

async def close_async_db():
    """Close the async database pool"""
    global _async_db_instance
    if _async_db_instance:
        await _async_db_instance.close_pool()
        _async_db_instance = None 