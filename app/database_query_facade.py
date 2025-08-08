from datetime import datetime, timedelta
import sqlite3

class DatabaseQueryFacade:
    def __init__(self, db, logger):
        self.db = db
        self.logger = logger

    #### KEYWORD MONITOR QUERIES ####
    def get_or_create_keyword_monitor_settings(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Check if table exists and get its columns
            cursor.execute("PRAGMA table_info(keyword_monitor_settings)")
            columns = {col[1] for col in cursor.fetchall()}

            if not columns:
                # Create table if it doesn't exist
                cursor.execute("""
                               CREATE TABLE keyword_monitor_settings
                               (
                                   id                  INTEGER PRIMARY KEY,
                                   check_interval      INTEGER NOT NULL DEFAULT 15,
                                   interval_unit       INTEGER NOT NULL DEFAULT 60,
                                   search_fields       TEXT    NOT NULL DEFAULT 'title,description,content',
                                   language            TEXT    NOT NULL DEFAULT 'en',
                                   sort_by             TEXT    NOT NULL DEFAULT 'publishedAt',
                                   page_size           INTEGER NOT NULL DEFAULT 10,
                                   is_enabled          BOOLEAN NOT NULL DEFAULT 1,
                                   daily_request_limit INTEGER NOT NULL DEFAULT 100,
                                   search_date_range   INTEGER NOT NULL DEFAULT 7,
                                   provider            TEXT    NOT NULL DEFAULT 'newsapi'
                               )
                               """)
                # Insert default settings
                cursor.execute("""
                               INSERT INTO keyword_monitor_settings (id)
                               VALUES (1)
                               """)
                conn.commit()
            else:
                # Add any missing columns
                if 'is_enabled' not in columns:
                    cursor.execute("""
                                   ALTER TABLE keyword_monitor_settings
                                       ADD COLUMN is_enabled BOOLEAN NOT NULL DEFAULT 1
                                   """)
                if 'daily_request_limit' not in columns:
                    cursor.execute("""
                                   ALTER TABLE keyword_monitor_settings
                                       ADD COLUMN daily_request_limit INTEGER NOT NULL DEFAULT 100
                                   """)
                if 'search_date_range' not in columns:
                    cursor.execute("""
                                   ALTER TABLE keyword_monitor_settings
                                       ADD COLUMN search_date_range INTEGER NOT NULL DEFAULT 7
                                   """)
                if 'provider' not in columns:
                    cursor.execute("""
                                   ALTER TABLE keyword_monitor_settings
                                       ADD COLUMN provider TEXT NOT NULL DEFAULT 'newsapi'
                                   """)
                conn.commit()

            # Load settings
            cursor.execute("""
                           SELECT check_interval,
                                  interval_unit,
                                  search_fields, language, sort_by, page_size, is_enabled, daily_request_limit, search_date_range, provider
                           FROM keyword_monitor_settings
                           WHERE id = 1
                           """)
            settings = cursor.fetchone()
            return settings

    def create_keyword_monitor_status_tables(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Check if table exists and get its columns
            cursor.execute("PRAGMA table_info(keyword_monitor_status)")
            columns = {col[1] for col in cursor.fetchall()}

            if not columns:
                # Table doesn't exist, create it with all columns
                cursor.execute("""
                               CREATE TABLE keyword_monitor_status
                               (
                                   id              INTEGER PRIMARY KEY,
                                   last_check_time TEXT,
                                   last_error      TEXT,
                                   requests_today  INTEGER DEFAULT 0,
                                   last_reset_date TEXT
                               )
                               """)
            elif 'last_reset_date' not in columns:
                # Add last_reset_date column if it doesn't exist
                cursor.execute("""
                               ALTER TABLE keyword_monitor_status
                                   ADD COLUMN last_reset_date TEXT
                               """)

            # Create initial status record if it doesn't exist
            cursor.execute("""
                           INSERT
                           OR IGNORE INTO keyword_monitor_status (
                    id, last_check_time, last_error, requests_today, last_reset_date
                ) VALUES (1, NULL, NULL, 0, NULL)
                           """)

            conn.commit()

            # Check if we need to reset the counter
            cursor.execute("""
                           SELECT requests_today, last_reset_date
                           FROM keyword_monitor_status
                           WHERE id = 1
                           """)
            row = cursor.fetchone()
            if row:
                last_reset = row[1]
                today = datetime.now().date().isoformat()

                if not last_reset or last_reset < today:
                    # Reset counter for new day
                    cursor.execute("""
                                   UPDATE keyword_monitor_status
                                   SET requests_today  = 0,
                                       last_reset_date = ?
                                   WHERE id = 1
                                   """, (today,))
                    conn.commit()

    def get_keyword_monitoring_provider(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                           SELECT provider
                           FROM keyword_monitor_settings
                           WHERE id = 1
                           """)
            row = cursor.fetchone()
            provider = row[0] if row else 'newsapi'

            return provider

    def get_keyword_monitoring_counter(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                           SELECT requests_today, last_reset_date
                           FROM keyword_monitor_status
                           WHERE id = 1
                           """)

            row = cursor.fetchone()
            return row

    def reset_keyword_monitoring_counter(self, params):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           UPDATE keyword_monitor_status
                           SET requests_today  = 0,
                               last_reset_date = ?
                           WHERE id = 1
                           """, params)

            conn.commit()

    def create_or_update_keyword_monitor_last_check(self, params):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Store check start time and reset error
            cursor.execute("""
                INSERT INTO keyword_monitor_status (
                    id, last_check_time, last_error, requests_today
                ) VALUES (1, ?, NULL, ?)
                ON CONFLICT(id) DO UPDATE SET
                    last_check_time = excluded.last_check_time,
                    last_error = excluded.last_error,
                    requests_today = excluded.requests_today
            """, params)
            conn.commit()

    def get_monitored_keywords(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Ensure foreign keys are enabled
            cursor.execute("PRAGMA foreign_keys = ON")

            cursor.execute("""
                           SELECT mk.id, mk.keyword, mk.last_checked, kg.topic
                           FROM monitored_keywords mk
                                    JOIN keyword_groups kg ON mk.group_id = kg.id
                           """)
            keywords = cursor.fetchall()
            return keywords
        return []

    def get_monitored_keywords_for_topic(self, params):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Ensure foreign keys are enabled
            cursor.execute("PRAGMA foreign_keys = ON")

            # Get keywords for this topic
            cursor.execute("""
                           SELECT mk.keyword
                           FROM monitored_keywords mk
                                    JOIN keyword_groups kg ON mk.group_id = kg.id
                           WHERE kg.topic = ?
                           """, params)

            topic_keywords = [row[0] for row in cursor.fetchall()]
            return topic_keywords
        return []

    def article_exists(self, params):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                "SELECT uri FROM articles WHERE uri = ?",
                params
            )
            article_exists = cursor.fetchone()
            return article_exists

    def create_article(self, article_exists, article_url, article, topic, keyword_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            conn.execute("BEGIN IMMEDIATE")

            try:
                inserted_new_article = False
                if not article_exists:
                    # Save new article
                    cursor.execute("""
                                   INSERT INTO articles (uri, title, news_source, publication_date,
                                                         summary, topic, analyzed)
                                   VALUES (?, ?, ?, ?, ?, ?, ?)
                                   """, (
                                       article_url,
                                       article['title'],
                                       article['source'],
                                       article['published_date'],
                                       article.get('summary', ''),  # Use get() with default
                                       topic,
                                       False  # Explicitly mark as not analyzed
                                   ))
                    inserted_new_article = True
                    self.logger.info(f"Inserted new article: {article_url}")

                # Create alert
                cursor.execute("""
                               INSERT INTO keyword_alerts (keyword_id, article_uri)
                               VALUES (?, ?) ON CONFLICT DO NOTHING
                               """, (keyword_id, article_url))

                alert_inserted = cursor.rowcount > 0

                # Get the group_id for this keyword
                cursor.execute("""
                               SELECT group_id
                               FROM monitored_keywords
                               WHERE id = ?
                               """, (keyword_id,))
                group_id = cursor.fetchone()[0]

                # Check if we already have a match for this article in this group
                cursor.execute("""
                               SELECT id, keyword_ids
                               FROM keyword_article_matches
                               WHERE article_uri = ?
                                 AND group_id = ?
                               """, (article_url, group_id))

                existing_match = cursor.fetchone()
                match_updated = False

                if existing_match:
                    # Update the existing match with the new keyword
                    match_id, keyword_ids = existing_match
                    keyword_id_list = keyword_ids.split(',')
                    if str(keyword_id) not in keyword_id_list:
                        keyword_id_list.append(str(keyword_id))
                        updated_keyword_ids = ','.join(keyword_id_list)

                        cursor.execute("""
                                       UPDATE keyword_article_matches
                                       SET keyword_ids = ?
                                       WHERE id = ?
                                       """, (updated_keyword_ids, match_id))
                        match_updated = True
                else:
                    # Create a new match
                    cursor.execute("""
                                   INSERT INTO keyword_article_matches (article_uri, keyword_ids, group_id)
                                   VALUES (?, ?, ?)
                                   """, (article_url, str(keyword_id), group_id))
                    match_updated = True

                # Commit transaction
                conn.commit()

                return inserted_new_article, alert_inserted, match_updated
            except Exception as e:
                conn.rollback()
                raise e

    def update_monitored_keyword_last_checked(self, params):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Update last checked timestamp
            cursor.execute(
                "UPDATE monitored_keywords SET last_checked = ? WHERE id = ?",
                params
            )
            conn.commit()

    def update_keyword_monitor_counter(self, params):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           UPDATE keyword_monitor_status
                           SET requests_today = ?
                           WHERE id = 1
                           """, params)
            conn.commit()

    def create_keyword_monitor_log_entry(self, params):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO keyword_monitor_status (
                    id, last_check_time, last_error, requests_today
                ) VALUES (1, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    last_check_time = excluded.last_check_time,
                    last_error = excluded.last_error,
                    requests_today = excluded.requests_today
            """, params)
            conn.commit()

    def get_keyword_monitor_polling_enabled(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_enabled FROM keyword_monitor_settings WHERE id = 1")
            row = cursor.fetchone()
            is_enabled = row[0] if row and row[0] is not None else True

            return is_enabled

    def get_keyword_monitor_interval(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT check_interval, interval_unit FROM keyword_monitor_settings WHERE id = 1"
            )
            settings = cursor.fetchone()

            return settings

    #### RESEARCH QUERIES ####
    def get_article_by_url(self, url):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM articles WHERE uri = ?",
                (url,)
            )

            return cursor.fetchone()

    def create_article_with_extracted_content(self, params):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           INSERT INTO articles
                               (uri, title, news_source, submission_date, topic, analyzed, summary)
                           VALUES (?, ?, ?, datetime('now'), ?, ?, ?)
                           """, params)

    async def move_alert_to_articles(self, url: str) -> None:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            # First get the alert article
            cursor.execute("""
                           SELECT *
                           FROM keyword_alert_articles
                           WHERE url = ?
                             AND moved_to_articles = FALSE
                           """, (url,))
            alert = cursor.fetchone()

            if alert:
                # Insert into articles table with analyzed flag
                cursor.execute("""
                               INSERT INTO articles (url, title, summary, source, topic, analyzed)
                               VALUES (?, ?, ?, ?, ?, FALSE)
                               """, (alert['url'], alert['title'], alert['summary'],
                                     alert['source'], alert['topic']))

                # Mark as moved
                cursor.execute("""
                               UPDATE keyword_alert_articles
                               SET moved_to_articles = TRUE
                               WHERE url = ?
                               """, (url,))

    #### REINDEX CHROMA DB QUERIES ####
    def get_iter_articles(self, limit: int | None = None):
        with self.db.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            query = (
                """
                SELECT a.*, r.raw_markdown AS raw
                FROM articles a
                         LEFT JOIN raw_articles r ON a.uri = r.uri
                ORDER BY a.rowid
                """
            )
            if limit:
                query += " LIMIT ?"
                params = (limit,)
            else:
                params = ()

            cursor.execute(query, params)
            for row in cursor.fetchall():
                yield dict(row)

    #### ROUTES QUERIES ####
    def enriched_articles(self, limit):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            # Query for articles that have a non-null and non-empty category
            query = """
                    SELECT *
                    FROM articles
                    WHERE category IS NOT NULL \
                      AND category != ''
                    ORDER BY submission_date DESC
                        LIMIT ? \
                    """

            cursor.execute(query, (limit,))
            articles = []

            for row in cursor.fetchall():
                # Convert row to dictionary
                article_dict = {}
                for idx, col in enumerate(cursor.description):
                    article_dict[col[0]] = row[idx]

                # Process tags
                if article_dict.get('tags'):
                    article_dict['tags'] = article_dict['tags'].split(',')
                else:
                    article_dict['tags'] = []

                articles.append(article_dict)

            return articles

    def get_topics_with_article_counts(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    topic, 
                    COUNT(DISTINCT uri) as article_count,
                    MAX(publication_date) as last_article_date
                FROM articles 
                WHERE topic IS NOT NULL AND topic != ''
                GROUP BY topic
            """)
            db_topics = {row[0]: {"article_count": row[1], "last_article_date": row[2]}
                        for row in cursor.fetchall()}
            return db_topics

    def debug_articles(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM articles")
            articles = cursor.fetchall()
            return articles

    def get_rate_limit_status(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                           SELECT requests_today, last_error
                           FROM keyword_monitor_status
                           WHERE id = 1
                           """)
            row = cursor.fetchone()

            return row

    def get_monitor_page_keywords(self):
        with self.db.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Get keyword groups and their keywords
            cursor.execute("""
                SELECT kg.id, kg.name, kg.topic, 
                       mk.id as keyword_id, 
                       mk.keyword
                FROM keyword_groups kg
                LEFT JOIN monitored_keywords mk ON kg.id = mk.group_id
                ORDER BY kg.name, mk.keyword
            """)
            return cursor.fetchall()

    def get_monitored_keywords_for_keyword_alerts_page(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT MAX(last_checked)                                                  as last_check_time,
                                  (SELECT check_interval FROM keyword_monitor_settings WHERE id = 1) as check_interval,
                                  (SELECT interval_unit FROM keyword_monitor_settings WHERE id = 1)  as interval_unit,
                                  (SELECT last_error FROM keyword_monitor_status WHERE id = 1)       as last_error,
                                  (SELECT is_enabled FROM keyword_monitor_settings WHERE id = 1)     as is_enabled
                           FROM monitored_keywords
                           """)

            return cursor.fetchone()

    def get_all_groups_with_their_alerts_and_status(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           WITH alert_counts AS (SELECT kg.id                 as group_id,
                                                        COUNT(DISTINCT ka.id) as unread_count
                                                 FROM keyword_groups kg
                                                          LEFT JOIN monitored_keywords mk ON kg.id = mk.group_id
                                                          LEFT JOIN keyword_alerts ka ON mk.id = ka.keyword_id AND ka.is_read = 0
                                                 GROUP BY kg.id)
                           SELECT kg.id,
                                  kg.name,
                                  kg.topic,
                                  ac.unread_count,
                                  (SELECT GROUP_CONCAT(keyword, '||')
                                   FROM monitored_keywords
                                   WHERE group_id = kg.id) as keywords
                           FROM keyword_groups kg
                                    LEFT JOIN alert_counts ac ON kg.id = ac.group_id
                           ORDER BY ac.unread_count DESC, kg.name
                           """)

            return cursor.fetchall()

    def check_if_keyword_article_matches_table_exists(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='keyword_article_matches'
            """)

            return cursor.fetchone() is not None

    def get_keywords_and_articles_for_keywords_alert_page_using_new_structure(self, group_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT kam.id,
                                  kam.detected_at,
                                  kam.article_uri,
                                  a.title,
                                  a.uri                                                                            as url,
                                  a.news_source,
                                  a.publication_date,
                                  a.summary,
                                  kam.keyword_ids,
                                  (SELECT GROUP_CONCAT(keyword, '||')
                                   FROM monitored_keywords
                                   WHERE id IN (SELECT value
                                                FROM json_each('[' || REPLACE(kam.keyword_ids, ',', ',') || ']'))) as matched_keywords
                           FROM keyword_article_matches kam
                                    JOIN articles a ON kam.article_uri = a.uri
                           WHERE kam.group_id = ?
                             AND kam.is_read = 0
                           ORDER BY kam.detected_at DESC
                           """, (group_id,))

            return cursor.fetchall()

    def get_keywords_and_articles_for_keywords_alert_page_using_old_structure(self, group_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT ka.id,
                                  ka.detected_at,
                                  ka.article_uri,
                                  a.title,
                                  a.uri      as url,
                                  a.news_source,
                                  a.publication_date,
                                  a.summary,
                                  mk.keyword as matched_keyword
                           FROM keyword_alerts ka
                                    JOIN monitored_keywords mk ON ka.keyword_id = mk.id
                                    JOIN articles a ON ka.article_uri = a.uri
                           WHERE mk.group_id = ?
                             AND ka.is_read = 0
                           ORDER BY ka.detected_at DESC
                           """, (group_id,))

            return cursor.fetchall()

    def check_if_table_podcasts_exists(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT name
                           FROM sqlite_master
                           WHERE type = 'table'
                             AND name = 'podcasts'
                           """)

            return cursor.fetchone()

    def create_table_podcasts(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS podcasts (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    audio_url TEXT,
                    transcript TEXT,
                    status TEXT DEFAULT 'pending',
                    config JSON
                )
            """)
            conn.commit()

    def get_all_completed_podcasts(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT id, title, created_at, audio_url, transcript
                           FROM podcasts
                           WHERE status = 'completed'
                           ORDER BY created_at DESC LIMIT 50
                           """)

            return cursor.fetchall()

    def create_podcast(self, params):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           INSERT INTO podcasts (id, title, created_at, status, config, article_uris)
                           VALUES (?, ?, CURRENT_TIMESTAMP, 'processing', ?, ?)
                           """, params)
            conn.commit()

    def update_podcast_status(self, params):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           UPDATE podcasts
                           SET status     = ?,
                               audio_url  = ?,
                               transcript = ?
                           WHERE id = ?
                           """, params)
            conn.commit()

    def get_flow_data(self, topic, timeframe, limit):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            query = (
                "SELECT COALESCE(news_source, 'Unknown') AS source, "
                "COALESCE(category, 'Unknown') AS category, "
                "COALESCE(sentiment, 'Unknown') AS sentiment, "
                "COALESCE(driver_type, 'Unknown') AS driver_type, "
                "submission_date "
                "FROM articles WHERE 1=1"
            )
            params = []

            if topic:
                query += " AND topic = ?"
                params.append(topic)

            if timeframe != "all":
                try:
                    days = int(timeframe)
                    query += " AND submission_date >= date('now', ?)"
                    params.append(f'-{days} days')
                except ValueError:
                    logger.warning("Invalid timeframe value provided: %s", timeframe)

            query += " ORDER BY submission_date DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            return cursor.fetchall()

