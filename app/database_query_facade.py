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

    #### ENDPOINTS QUERIES ####
    def get_podcasts_columns(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("PRAGMA table_info(podcasts)")

            table_info = cursor.fetchall()

            return [col[1] for col in table_info]

    def generate_latest_podcasts(self, column_names, has_transcript, has_topic, has_audio_url):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Build list of columns to select based on what's available
            select_columns = ['id']
            if 'title' in column_names:
                select_columns.append('title')
            else:
                select_columns.append("'Untitled Podcast' as title")

            if 'created_at' in column_names:
                select_columns.append('created_at')
            else:
                select_columns.append('NULL as created_at')

            if has_audio_url:
                select_columns.append('audio_url')

            if has_transcript:
                select_columns.append('transcript_text')

            # Build query
            query = f"SELECT {', '.join(select_columns)} FROM podcasts "

            # Add WHERE clause if we can filter by topic
            params = []
            if has_topic:
                query += "WHERE topic = ? OR topic IS NULL OR topic = 'General' "
                params.append(topic)

            # Add ORDER BY and LIMIT
            query += "ORDER BY created_at DESC LIMIT 1"

            # Execute query

            cursor.execute(query, params)

            return cursor.fetchone()

    def get_articles_for_date_range(self, limit, topic, start_date, end_date):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # SQL limit clause
            limit_clause = f"LIMIT {limit}" if limit else ""

            cursor.execute(
                f"""
                SELECT * FROM articles 
                WHERE topic = ? 
                AND publication_date BETWEEN ? AND ?
                ORDER BY publication_date DESC
                {limit_clause}
                """,
                (topic, start_date, end_date)
            )
            articles = cursor.fetchall()

            # Convert to list of dictionaries with column names
            column_names = [description[0] for description in cursor.description]

            return column_names, articles

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

    def create_model_bias_arena_runs(self, params):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           INSERT INTO model_bias_arena_runs
                           (name, description, benchmark_model, selected_models, article_count, rounds, current_round,
                            status)
                           VALUES (?, ?, ?, ?, ?, ?, ?, 'running')
                           """,
                           (name, description, benchmark_model, json.dumps(selected_models), len(articles), rounds, 1))

            return cursor.lastrowid

    def store_evaluation_results(self, params):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           INSERT INTO model_bias_arena_results
                           (run_id, article_uri, model_name, response_text, bias_score,
                            confidence_score, response_time_ms, error_message)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                           """, (run_id, article_uri, model_name, response_text, bias_score,
                                 confidence_score, response_time_ms, error_message))
            conn.commit()

    def store_ontological_results(self, params):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           INSERT INTO model_bias_arena_results
                           (run_id, article_uri, model_name, response_text,
                            response_time_ms, sentiment, sentiment_explanation, future_signal,
                            future_signal_explanation, time_to_impact, time_to_impact_explanation,
                            driver_type, driver_type_explanation, category, category_explanation,
                            political_bias, political_bias_explanation, factuality, factuality_explanation,
                            round_number)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                           """, params)
            conn.commit()

    def update_run_status(self, params):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           UPDATE model_bias_arena_runs
                           SET status       = ?,
                               completed_at = CURRENT_TIMESTAMP
                           WHERE id = ?
                           """, params)
            conn.commit()

    def get_run_details(self, run_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT id,
                                  name,
                                  description,
                                  benchmark_model,
                                  selected_models,
                                  article_count,
                                  rounds,
                                  current_round,
                                  created_at,
                                  completed_at,
                                  status
                           FROM model_bias_arena_runs
                           WHERE id = ?
                           """, (run_id,))

            return cursor.fetchone()

    def get_ontological_results_with_article_info(self, run_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT r.model_name,
                                  r.article_uri,
                                  r.sentiment,
                                  r.sentiment_explanation,
                                  r.future_signal,
                                  r.future_signal_explanation,
                                  r.time_to_impact,
                                  r.time_to_impact_explanation,
                                  r.driver_type,
                                  r.driver_type_explanation,
                                  r.category,
                                  r.category_explanation,
                                  r.political_bias,
                                  r.political_bias_explanation,
                                  r.factuality,
                                  r.factuality_explanation,
                                  r.confidence_score,
                                  r.response_time_ms,
                                  r.error_message,
                                  r.response_text,
                                  r.round_number,
                                  maa.article_title,
                                  maa.article_summary
                           FROM model_bias_arena_results r
                                    JOIN model_bias_arena_articles maa ON r.article_uri = maa.article_uri
                               AND r.run_id = maa.run_id
                           WHERE r.run_id = ?
                           ORDER BY r.article_uri, r.model_name, r.round_number
                           """, (run_id,))

            return cursor.fetchall()

    def get_benchmark_data_including_media_bias_info(self, run_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT a.uri,
                                  a.title,
                                  a.sentiment,
                                  a.future_signal,
                                  a.time_to_impact,
                                  a.driver_type,
                                  a.category,
                                  a.sentiment_explanation,
                                  a.future_signal_explanation,
                                  a.time_to_impact_explanation,
                                  a.driver_type_explanation,
                                  a.bias,
                                  a.factual_reporting,
                                  a.mbfc_credibility_rating,
                                  a.bias_country,
                                  a.press_freedom,
                                  a.media_type,
                                  a.popularity,
                                  a.news_source
                           FROM model_bias_arena_articles maa
                                    JOIN articles a ON maa.article_uri = a.uri
                           WHERE maa.run_id = ?
                           ORDER BY a.uri
                           """, (run_id,))

            return cursor.fetchall()

    def delete_run(self, run_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("DELETE FROM model_bias_arena_runs WHERE id = ?", (run_id,))
            conn.commit()

            return cursor.rowcount

    def get_source_bias_validation_data(self, url):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT bias,
                                  factual_reporting,
                                  mbfc_credibility_rating,
                                  bias_country,
                                  press_freedom,
                                  media_type,
                                  popularity
                           FROM articles
                           WHERE uri = ?
                           """, (url,))

            return cursor.fetchone()

    def get_run_articles(self, run_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT article_uri, article_title, article_summary
                           FROM model_bias_arena_articles
                           WHERE run_id = ?
                           ORDER BY id
                           """, (run_id,))

            return cursor.fetchall()

    def get_all_bias_evaluation_runs(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT id,
                                  name,
                                  description,
                                  benchmark_model,
                                  selected_models,
                                  article_count,
                                  rounds,
                                  current_round,
                                  created_at,
                                  completed_at,
                                  status
                           FROM model_bias_arena_runs
                           ORDER BY created_at DESC
                           """)

            return cursor.fetchall()

    def update_run(self, params):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           UPDATE model_bias_arena_runs
                           SET current_round = ?
                           WHERE id = ?
                           """, (round_num, run_id))
            conn.commit()

    def get_topics_from_article(self, article_url):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT DISTINCT topic FROM articles WHERE uri = ?", (article_url,))

            return cursor.fetchone()

    def get_run_info(self, run_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT rounds, current_round
                           FROM model_bias_arena_runs
                           WHERE id = ?
                           """, (run_id,))

            return cursor.fetchone()

    def add_articles_to_run(self, params):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           INSERT INTO model_bias_arena_articles
                               (run_id, article_uri, article_title, article_summary)
                           VALUES (?, ?, ?, ?)
                           """, params)

            conn.commit()

    def sample_articles(self, count, topic):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Only select articles that have all required ontological fields populated (benchmark data)
            query = """
                    SELECT uri, \
                           title, \
                           summary, \
                           news_source, \
                           topic, \
                           category,
                           sentiment, \
                           future_signal, \
                           time_to_impact, \
                           driver_type,
                           bias, \
                           factual_reporting, \
                           mbfc_credibility_rating, \
                           bias_country
                    FROM articles
                    WHERE summary IS NOT NULL
                      AND LENGTH(summary) > 100
                      AND analyzed = 1
                      AND sentiment IS NOT NULL \
                      AND sentiment != ''
                AND future_signal IS NOT NULL AND future_signal != ''
                AND time_to_impact IS NOT NULL AND time_to_impact != ''
                AND driver_type IS NOT NULL AND driver_type != ''
                AND category IS NOT NULL AND category != ''
                AND (news_source IS NOT NULL AND news_source != '') \
                    """
            params = []

            if topic:
                query += " AND topic = ?"
                params.append(topic)

            query += " ORDER BY RANDOM() LIMIT ?"
            params.append(count)

            cursor.execute(query, params)

            return cursor.fetchall()

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

    def create_keyword_monitor_group(self, params):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO keyword_groups (name, topic) VALUES (?, ?)",
                params
            )
            conn.commit()

            return cursor.lastrowid

    def create_keyword(self, params):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO monitored_keywords (group_id, keyword) VALUES (?, ?)",
                params
            )
            conn.commit()

    def delete_keyword(self, keyword_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM monitored_keywords WHERE id = ?", (keyword_id,))
            conn.commit()

    def delete_keyword_group(self,group_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM keyword_groups WHERE id = ?", (group_id,))
            conn.commit()

    def get_all_group_ids_associated_to_topic(self, topic_name):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # First, get all group IDs associated with this topic
            cursor.execute("SELECT id FROM keyword_groups WHERE topic = ?", (topic_name,))
            groups = cursor.fetchall()
            return groups

    def get_keyword_ids_associated_to_group(self, group_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT id FROM monitored_keywords WHERE group_id = ?", (group_id,))
            return cursor.fetchall()

    def get_keywords_associated_to_group(self, group_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                "SELECT keyword FROM monitored_keywords WHERE group_id = ?",
                (group_id,)
            )
            return [keyword[0] for keyword in cursor.fetchall()]

    def get_keywords_associated_to_group_ordered_by_keyword(self, group_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT keyword
                           FROM monitored_keywords
                           WHERE group_id = ?
                           ORDER BY keyword
                           """, (group_id,))
            return [keyword[0] for keyword in cursor.fetchall()]

    def delete_keyword_article_matches_from_new_table_structure(self, group_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("DELETE FROM keyword_article_matches WHERE group_id = ?", (group_id,))
            conn.commit()

            return cursor.rowcount

    def delete_keyword_article_matches_from_old_table_structure(self, ids_str, keyword_ids):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(f"DELETE FROM keyword_alerts WHERE keyword_id IN ({ids_str})", keyword_ids)
            conn.commit()

            return cursor.rowcount

    def delete_groups_keywords(self, ids_str, group_ids):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(f"DELETE FROM monitored_keywords WHERE group_id IN ({ids_str})", group_ids)
            conn.commit()

            return cursor.rowcount

    def delete_all_keyword_groups(self, topic_name):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM keyword_groups WHERE topic = ?", (topic_name,))
            conn.commit()

            return cursor.rowcount

    def check_if_alert_id_exists_in_new_table_structure(self, alert_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT 1 FROM keyword_article_matches WHERE id = ?", (alert_id,))

            return cursor.fetchone()

    def mark_alert_as_read_or_unread_in_new_table(self, alert_id, read_or_unread):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                "UPDATE keyword_article_matches SET is_read = ? WHERE id = ?",
                (read_or_unread, alert_id,)
            )

            conn.commit()

    def mark_alert_as_read_or_unread_in_old_table(self, alert_id, read_or_unread):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                "UPDATE keyword_alerts SET is_read = ? WHERE id = ?",
                (read_or_unread, alert_id,)
            )

            conn.commit()

    def get_number_of_monitored_keywords_by_group_id(self, group_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM monitored_keywords WHERE group_id = ?", (group_id,))

            return cursor.fetchone()[0]

    def get_total_number_of_keywords(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM monitored_keywords")

            return cursor.fetchone()[0]

    def get_alerts(self, show_read):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Modify the query to optionally include read articles
            read_condition = "" if show_read else "AND ka.is_read = 0"

            cursor.execute(f"""
                SELECT ka.*, a.*, mk.keyword as matched_keyword
                FROM keyword_alerts ka
                JOIN articles a ON ka.article_uri = a.uri
                JOIN monitored_keywords mk ON ka.keyword_id = mk.id
                WHERE 1=1 {read_condition}
                ORDER BY ka.detected_at DESC
                LIMIT 100
            """)

            columns = [column[0] for column in cursor.description]

            return columns, cursor.fetchall()

    def get_article_enrichment(self, article_data):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT category,
                                  sentiment,
                                  driver_type,
                                  time_to_impact,
                                  topic_alignment_score,
                                  keyword_relevance_score,
                                  confidence_score,
                                  overall_match_explanation,
                                  extracted_article_topics,
                                  extracted_article_keywords,
                                  auto_ingested,
                                  ingest_status,
                                  quality_score,
                                  quality_issues
                           FROM articles
                           WHERE uri = ?
                           """, (article_data["uri"],))

            return cursor.fetchone()

    def get_all_groups_with_alerts_and_status_new_table_structure(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           WITH alert_counts AS (SELECT kg.id                                                      as group_id,
                                                        COUNT(DISTINCT CASE
                                                                           WHEN ka.is_read = 0 AND a.uri IS NOT NULL
                                                                               THEN ka.id END)                     as unread_count,
                                                        COUNT(DISTINCT CASE WHEN a.uri IS NOT NULL THEN ka.id END) as total_count
                                                 FROM keyword_groups kg
                                                          LEFT JOIN keyword_article_matches ka ON kg.id = ka.group_id
                                                          LEFT JOIN articles a ON ka.article_uri = a.uri
                                                 GROUP BY kg.id),
                                growth_data AS (SELECT kg.id as group_id,
                                                       CASE
                                                           WHEN COUNT(CASE WHEN a.uri IS NOT NULL THEN ka.id END) = 0
                                                               THEN 'No data'
                                                           WHEN MAX(ka.detected_at) < date ('now', '-7 days') THEN 'Inactive'
                               WHEN COUNT (DISTINCT CASE WHEN a.uri IS NOT NULL THEN ka.id END) > 20 THEN 'High growth'
                               WHEN COUNT (DISTINCT CASE WHEN a.uri IS NOT NULL THEN ka.id END) > 10 THEN 'Growing'
                               ELSE 'Stable'
                           END
                           as growth_status
                    FROM keyword_groups kg
                    LEFT JOIN keyword_article_matches ka ON kg.id = ka.group_id
                    LEFT JOIN articles a ON ka.article_uri = a.uri
                    GROUP BY kg.id
                )
                           SELECT kg.id,
                                  kg.name,
                                  kg.topic,
                                  COALESCE(ac.unread_count, 0)          as unread_count,
                                  COALESCE(ac.total_count, 0)           as total_count,
                                  COALESCE(gd.growth_status, 'No data') as growth_status
                           FROM keyword_groups kg
                                    LEFT JOIN alert_counts ac ON kg.id = ac.group_id
                                    LEFT JOIN growth_data gd ON kg.id = gd.group_id
                           ORDER BY ac.unread_count DESC, kg.name
                           """)

            return cursor.fetchall()

    def get_all_groups_with_alerts_and_status_old_table_structure(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           WITH alert_counts AS (SELECT kg.id                                                      as group_id,
                                                        COUNT(DISTINCT CASE
                                                                           WHEN ka.read = 0 AND a.uri IS NOT NULL
                                                                               THEN ka.id END)                     as unread_count,
                                                        COUNT(DISTINCT CASE WHEN a.uri IS NOT NULL THEN ka.id END) as total_count
                                                 FROM keyword_groups kg
                                                          LEFT JOIN monitored_keywords mk ON kg.id = mk.group_id
                                                          LEFT JOIN keyword_alerts ka ON mk.id = ka.keyword_id
                                                          LEFT JOIN articles a ON ka.article_uri = a.uri
                                                 GROUP BY kg.id),
                                growth_data AS (SELECT kg.id as group_id,
                                                       CASE
                                                           WHEN COUNT(CASE WHEN a.uri IS NOT NULL THEN ka.id END) = 0
                                                               THEN 'No data'
                                                           WHEN MAX(ka.detected_at) < date ('now', '-7 days') THEN 'Inactive'
                               WHEN COUNT (DISTINCT CASE WHEN a.uri IS NOT NULL THEN ka.id END) > 20 THEN 'High growth'
                               WHEN COUNT (DISTINCT CASE WHEN a.uri IS NOT NULL THEN ka.id END) > 10 THEN 'Growing'
                               ELSE 'Stable'
                           END
                           as growth_status
                                    FROM keyword_groups kg
                                    LEFT JOIN monitored_keywords mk ON kg.id = mk.group_id
                                    LEFT JOIN keyword_alerts ka ON mk.id = ka.keyword_id
                                    LEFT JOIN articles a ON ka.article_uri = a.uri
                                    GROUP BY kg.id
                                )
                           SELECT kg.id,
                                  kg.name,
                                  kg.topic,
                                  COALESCE(ac.unread_count, 0)          as unread_count,
                                  COALESCE(ac.total_count, 0)           as total_count,
                                  COALESCE(gd.growth_status, 'No data') as growth_status
                           FROM keyword_groups kg
                                    LEFT JOIN alert_counts ac ON kg.id = ac.group_id
                                    LEFT JOIN growth_data gd ON kg.id = gd.group_id
                           ORDER BY ac.unread_count DESC, kg.name
                           """)

            return cursor.fetchall()

    def get_most_recent_unread_alerts_for_group_id_new_table_structure(self, group_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT ka.id,
                                  ka.article_uri,
                                  ka.keyword_ids,
                                  NULL as matched_keyword,
                                  ka.is_read,
                                  ka.detected_at,
                                  a.title,
                                  a.summary,
                                  a.uri,
                                  a.news_source,
                                  a.publication_date,
                                  a.topic_alignment_score,
                                  a.keyword_relevance_score,
                                  a.confidence_score,
                                  a.overall_match_explanation,
                                  a.extracted_article_topics,
                                  a.extracted_article_keywords
                           FROM keyword_article_matches ka
                                    JOIN articles a ON ka.article_uri = a.uri
                           WHERE ka.group_id = ?
                             AND ka.is_read = 0
                           ORDER BY ka.detected_at DESC LIMIT 25
                           """, (group_id,))

            return cursor.fetchall()

    def get_most_recent_unread_alerts_for_group_id_old_table_structure(self, group_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT ka.id,
                                  ka.article_uri,
                                  ka.keyword_id,
                                  mk.keyword as matched_keyword,
                                  ka.read    as is_read,
                                  ka.detected_at,
                                  a.title,
                                  a.summary,
                                  a.uri,
                                  a.source   as news_source,
                                  a.publication_date,
                                  a.topic_alignment_score,
                                  a.keyword_relevance_score,
                                  a.confidence_score,
                                  a.overall_match_explanation,
                                  a.extracted_article_topics,
                                  a.extracted_article_keywords
                           FROM keyword_alerts ka
                                    JOIN articles a ON ka.article_uri = a.uri
                                    JOIN monitored_keywords mk ON ka.keyword_id = mk.id
                           WHERE mk.group_id = ?
                             AND ka.read = 0
                           ORDER BY ka.detected_at DESC LIMIT 25
                           """, (group_id,))

            return cursor.fetchall()

    def count_total_group_unread_articles_new_table_structure(self, group_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT COUNT(*)
                           FROM keyword_article_matches ka
                                    JOIN articles a ON ka.article_uri = a.uri
                           WHERE ka.group_id = ?
                             AND ka.is_read = 0
                           """, (group_id,))

            return cursor.fetchone()[0]

    def count_total_group_unread_articles_old_table_structure(self, group_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT COUNT(*)
                           FROM keyword_alerts ka
                                    JOIN articles a ON ka.article_uri = a.uri
                                    JOIN monitored_keywords mk ON ka.keyword_id = mk.id
                           WHERE mk.group_id = ?
                             AND ka.read = 0
                           """, (group_id,))

            return cursor.fetchone()[0]

    def get_all_matched_keywords_for_article_and_group(self, placeholders, keyword_id_list_and_group_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(f"""
                SELECT DISTINCT keyword
                FROM monitored_keywords
                WHERE id IN ({placeholders}) AND group_id = ?
            """, keyword_id_list_and_group_id)

            return [kw[0] for kw in cursor.fetchall()]

    def get_all_matched_keywords_for_article_and_group_by_article_url_and_group_id(self, article_url, group_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT DISTINCT mk.keyword
                           FROM keyword_alerts ka
                                    JOIN monitored_keywords mk ON ka.keyword_id = mk.id
                           WHERE ka.article_uri = ?
                             AND mk.group_id = ?
                           """, (article_url, group_id))

            return [kw[0] for kw in cursor.fetchall()]

    def get_article_enrichment_by_article_url(self, article_url):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT category,
                                  sentiment,
                                  driver_type,
                                  time_to_impact,
                                  topic_alignment_score,
                                  keyword_relevance_score,
                                  confidence_score,
                                  overall_match_explanation,
                                  extracted_article_topics,
                                  extracted_article_keywords
                           FROM articles
                           WHERE uri = ?
                           """, (article_url,))

            return cursor.fetchone()

    def create_keyword_monitor_table_if_not_exists_and_insert_default_value(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS keyword_monitor_status (
                    id INTEGER PRIMARY KEY,
                    requests_today INTEGER DEFAULT 0,
                    last_reset_date TEXT,
                    last_check_time TEXT,
                    last_error TEXT
                )
            """)

            cursor.execute("""
                           INSERT
                           OR IGNORE INTO keyword_monitor_status (id, requests_today)
                VALUES (1, 0)
                           """)
            conn.commit()

    def check_keyword_monitor_status_and_settings_tables(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM keyword_monitor_status WHERE id = 1")
            status_data = cursor.fetchone()

            cursor.execute("SELECT * FROM keyword_monitor_settings WHERE id = 1")
            settings_data = cursor.fetchone()

            return status_data, settings_data

    def get_count_of_monitored_keywords(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) 
                FROM monitored_keywords mk
                WHERE EXISTS (
                    SELECT 1 
                    FROM keyword_groups kg 
                    WHERE kg.id = mk.group_id
                )
            """)

            return cursor.fetchone()[0]

    def get_settings_and_status_together(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT 
                    s.check_interval,
                    s.interval_unit,
                    s.search_fields,
                    s.language,
                    s.sort_by,
                    s.page_size,
                    s.daily_request_limit,
                    s.is_enabled,
                    s.provider,
                    COALESCE(s.auto_ingest_enabled, FALSE) as auto_ingest_enabled,
                    COALESCE(s.min_relevance_threshold, 0.0) as min_relevance_threshold,
                    COALESCE(s.quality_control_enabled, TRUE) as quality_control_enabled,
                    COALESCE(s.auto_save_approved_only, FALSE) as auto_save_approved_only,
                    COALESCE(s.default_llm_model, 'gpt-4o-mini') as default_llm_model,
                    COALESCE(s.llm_temperature, 0.1) as llm_temperature,
                    COALESCE(s.llm_max_tokens, 1000) as llm_max_tokens,
                    COALESCE(kms.requests_today, 0) as requests_today,
                    kms.last_error
                FROM keyword_monitor_settings s
                LEFT JOIN (
                    SELECT id, requests_today, last_error 
                    FROM keyword_monitor_status 
                    WHERE id = 1 AND last_reset_date = date('now')
                ) kms ON kms.id = 1
                WHERE s.id = 1
            """)

            return cursor.fetchone()

    def create_table_keyword_monitor_settings_if_not_exists(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS keyword_monitor_settings (
                    id INTEGER PRIMARY KEY,
                    check_interval INTEGER NOT NULL,
                    interval_unit INTEGER NOT NULL,
                    search_fields TEXT NOT NULL,
                    language TEXT NOT NULL,
                    sort_by TEXT NOT NULL,
                    page_size INTEGER NOT NULL,
                    daily_request_limit INTEGER NOT NULL,
                    provider TEXT NOT NULL DEFAULT 'newsapi',
                    auto_ingest_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                    min_relevance_threshold REAL NOT NULL DEFAULT 0.0,
                    quality_control_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    auto_save_approved_only BOOLEAN NOT NULL DEFAULT FALSE,
                    default_llm_model TEXT NOT NULL DEFAULT 'gpt-4o-mini',
                    llm_temperature REAL NOT NULL DEFAULT 0.1,
                    llm_max_tokens INTEGER NOT NULL DEFAULT 1000
                )
            """)

            conn.commit()

    def update_or_insert_keyword_monitor_settings(self, params):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT OR REPLACE INTO keyword_monitor_settings (
                    id, check_interval, interval_unit, search_fields,
                    language, sort_by, page_size, daily_request_limit, provider,
                    auto_ingest_enabled, min_relevance_threshold, quality_control_enabled,
                    auto_save_approved_only, default_llm_model, llm_temperature, llm_max_tokens
                ) VALUES (
                    1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
            """, params)

            conn.commit()

    def get_trends(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                WITH RECURSIVE dates(date) AS (
                    SELECT date('now', '-6 days')
                    UNION ALL
                    SELECT date(date, '+1 day')
                    FROM dates
                    WHERE date < date('now')
                ),
                daily_counts AS (
                    SELECT 
                        kg.id as group_id,
                        kg.name as group_name,
                        date(ka.detected_at) as detection_date,
                        COUNT(*) as article_count
                    FROM keyword_alerts ka
                    JOIN monitored_keywords mk ON ka.keyword_id = mk.id
                    JOIN keyword_groups kg ON mk.group_id = kg.id
                    WHERE ka.detected_at >= date('now', '-6 days')
                    GROUP BY kg.id, kg.name, date(ka.detected_at)
                )
                SELECT 
                    kg.id,
                    kg.name,
                    dates.date,
                    COALESCE(dc.article_count, 0) as count
                FROM keyword_groups kg
                CROSS JOIN dates
                LEFT JOIN daily_counts dc 
                    ON dc.group_id = kg.id 
                    AND dc.detection_date = dates.date
                ORDER BY kg.id, dates.date
            """)

            return cursor.fetchall()

    def toggle_polling(self, toggle):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # First check if settings exist
            cursor.execute("SELECT 1 FROM keyword_monitor_settings WHERE id = 1")
            exists = cursor.fetchone() is not None

            if exists:
                # Just update is_enabled if settings exist
                cursor.execute("""
                               UPDATE keyword_monitor_settings
                               SET is_enabled = ?
                               WHERE id = 1
                               """, (toggle.enabled,))
            else:
                # Insert with defaults if no settings exist
                cursor.execute("""
                               INSERT INTO keyword_monitor_settings (id,
                                                                     check_interval,
                                                                     interval_unit,
                                                                     search_fields,
                                                                     language,
                                                                     sort_by,
                                                                     page_size,
                                                                     is_enabled)
                               VALUES (1,
                                       15,
                                       60,
                                       'title,description,content',
                                       'en',
                                       'publishedAt',
                                       10,
                                       ?)
                               """, (toggle.enabled,))

            conn.commit()

    def get_all_alerts_for_export_new_table_structure(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT kg.name                                                                          as group_name,
                                  kg.topic,
                                  a.title,
                                  a.news_source,
                                  a.uri,
                                  a.publication_date,
                                  (SELECT GROUP_CONCAT(keyword, ', ')
                                   FROM monitored_keywords
                                   WHERE id IN (SELECT value
                                                FROM json_each('[' || REPLACE(kam.keyword_ids, ',', ',') || ']'))) as matched_keywords,
                                  kam.detected_at
                           FROM keyword_article_matches kam
                                    JOIN keyword_groups kg ON kam.group_id = kg.id
                                    JOIN articles a ON kam.article_uri = a.uri
                           ORDER BY kam.detected_at DESC
                           """)

            return cursor.fetchall()


    def get_all_alerts_for_export_old_table_structure(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT kg.name    as group_name,
                                  kg.topic,
                                  a.title,
                                  a.news_source,
                                  a.uri,
                                  a.publication_date,
                                  mk.keyword as matched_keyword,
                                  ka.detected_at
                           FROM keyword_alerts ka
                                    JOIN monitored_keywords mk ON ka.keyword_id = mk.id
                                    JOIN keyword_groups kg ON mk.group_id = kg.id
                                    JOIN articles a ON ka.article_uri = a.uri
                           ORDER BY ka.detected_at DESC
                           """)

            return cursor.fetchall()

    def get_all_group_and_topic_alerts_for_export_new_table_structure(self, group_id, topic):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT kg.name                                                                          as group_name,
                                  kg.topic,
                                  a.title,
                                  a.news_source,
                                  a.uri,
                                  a.publication_date,
                                  (SELECT GROUP_CONCAT(keyword, ', ')
                                   FROM monitored_keywords
                                   WHERE id IN (SELECT value
                                                FROM json_each('[' || REPLACE(kam.keyword_ids, ',', ',') || ']'))) as matched_keywords,
                                  kam.detected_at,
                                  kam.is_read
                           FROM keyword_article_matches kam
                                    JOIN keyword_groups kg ON kam.group_id = kg.id
                                    JOIN articles a ON kam.article_uri = a.uri
                           WHERE kg.id = ?
                             AND kg.topic = ?
                           ORDER BY kam.detected_at DESC
                           """, (group_id, topic))

            return cursor.fetchall()

    def get_all_group_and_topic_alerts_for_export_old_table_structure(self, group_id, topic):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Use the original table structure
            cursor.execute("""
                           SELECT kg.name    as group_name,
                                  kg.topic,
                                  a.title,
                                  a.news_source,
                                  a.uri,
                                  a.publication_date,
                                  mk.keyword as matched_keyword,
                                  ka.detected_at,
                                  ka.is_read
                           FROM keyword_alerts ka
                                    JOIN monitored_keywords mk ON ka.keyword_id = mk.id
                                    JOIN keyword_groups kg ON mk.group_id = kg.id
                                    JOIN articles a ON ka.article_uri = a.uri
                           WHERE kg.id = ?
                             AND kg.topic = ?
                           ORDER BY ka.detected_at DESC
                           """, (group_id, topic))

            return cursor.fetchall()

    def save_keyword_alert(self, article_data):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           INSERT
                           OR IGNORE INTO keyword_alert_articles 
                (url, title, summary, source, topic, keywords)
                VALUES (?, ?, ?, ?, ?, ?)
                           """, (
                               article_data['url'],
                               article_data['title'],
                               article_data['summary'],
                               article_data['source'],
                               article_data['topic'],
                               ','.join(article_data['matched_keywords'])
                           ))

            conn.commit()

    def get_alerts_by_group_id_from_new_table_structure(self, show_read, group_id, page_size, offset):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            read_condition = "" if show_read else "AND ka.is_read = 0"

            cursor.execute(f"""
                SELECT 
                    ka.id, 
                    ka.article_uri,
                    ka.keyword_ids,
                    NULL as matched_keyword,
                    ka.is_read,
                    ka.detected_at,
                    a.title,
                    a.summary,
                    a.uri,
                    a.news_source,
                    a.publication_date,
                    a.topic_alignment_score,
                    a.keyword_relevance_score,
                    a.confidence_score,
                    a.overall_match_explanation,
                    a.extracted_article_topics,
                    a.extracted_article_keywords,
                    a.category,
                    a.sentiment,
                    a.driver_type,
                    a.time_to_impact,
                    a.future_signal,
                    a.bias,
                    a.factual_reporting,
                    a.mbfc_credibility_rating,
                    a.bias_country,
                    a.press_freedom,
                    a.media_type,
                    a.popularity,
                    a.auto_ingested,
                    a.ingest_status,
                    a.quality_score,
                    a.quality_issues
                FROM keyword_article_matches ka
                JOIN articles a ON ka.article_uri = a.uri
                WHERE ka.group_id = ? {read_condition}
                ORDER BY ka.detected_at DESC
                LIMIT ? OFFSET ?
            """, (group_id, page_size, offset))

            return cursor.fetchall()

    def get_alerts_by_group_id_from_old_table_structure(self, show_read, group_id, page_size, offset):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            read_condition = "" if show_read else "AND ka.is_read = 0"
            cursor.execute(f"""
                SELECT 
                    ka.id, 
                    ka.article_uri,
                    ka.keyword_id,
                    mk.keyword as matched_keyword,
                    ka.is_read,
                    ka.detected_at,
                    a.title,
                    a.summary,
                    a.uri,
                    a.news_source,
                    a.publication_date,
                    a.topic_alignment_score,
                    a.keyword_relevance_score,
                    a.confidence_score,
                    a.overall_match_explanation,
                    a.extracted_article_topics,
                    a.extracted_article_keywords,
                    a.category,
                    a.sentiment,
                    a.driver_type,
                    a.time_to_impact,
                    a.future_signal,
                    a.bias,
                    a.factual_reporting,
                    a.mbfc_credibility_rating,
                    a.bias_country,
                    a.press_freedom,
                    a.media_type,
                    a.popularity,
                    a.auto_ingested,
                    a.ingest_status,
                    a.quality_score,
                    a.quality_issues
                FROM keyword_alerts ka
                JOIN articles a ON ka.article_uri = a.uri
                JOIN monitored_keywords mk ON ka.keyword_id = mk.id
                WHERE mk.group_id = ? {read_condition}
                ORDER BY ka.detected_at DESC
                LIMIT ? OFFSET ?
            """, (group_id, page_size, offset))

            return  cursor.fetchall()

    def count_unread_articles_by_group_id_from_new_table_structure(self, group_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT COUNT(ka.id)
                           FROM keyword_article_matches ka
                           WHERE ka.group_id = ?
                             AND ka.is_read = 0
                           """, (group_id,))

            return cursor.fetchone()[0]

    def count_unread_articles_by_group_id_from_old_table_structure(self, group_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT COUNT(ka.id)
                           FROM keyword_alerts ka
                                    JOIN monitored_keywords mk ON ka.keyword_id = mk.id
                           WHERE mk.group_id = ?
                             AND ka.is_read = 0
                           """, (group_id,))

            return cursor.fetchone()[0]

    def count_total_articles_by_group_id_from_new_table_structure(self, group_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT COUNT(ka.id)
                           FROM keyword_article_matches ka
                           WHERE ka.group_id = ?
                           """, (group_id,))

            return cursor.fetchone()[0]

    def count_total_articles_by_group_id_from_old_table_structure(self, group_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT COUNT(ka.id)
                           FROM keyword_alerts ka
                                    JOIN monitored_keywords mk ON ka.keyword_id = mk.id
                           WHERE mk.group_id = ?
                           """, (group_id,))

            return cursor.fetchone()[0]

    def update_media_bias(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE mediabias SET enabled = 1 WHERE source = ?",
                (bias_data.get('source'),)
            )
            conn.commit()

    def get_group_name(self, group_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT name FROM keyword_groups WHERE id = ?", (group_id,))

            group_row = cursor.fetchone()

            return group_row[0] if group_row else "Unknown Group"

    def get_article_urls_from_news_search_results_by_topic(self, topic_name):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT article_uri FROM news_search_results 
                WHERE topic = ?
            """, (topic_name,))

            return cursor.fetchall()

    def get_article_urls_from_paper_search_results_by_topic(self, topic_name):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT article_uri FROM paper_search_results 
                WHERE topic = ?
            """, (topic_name,))

            return cursor.fetchall()

    def article_urls_by_topic(self, topic_name):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT uri FROM articles WHERE topic = ?", (topic_name,))

            return cursor.fetchall()

    def delete_article_matches_by_url(self, url):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("DELETE FROM keyword_article_matches WHERE article_uri = ?", (url,))

            return cursor.rowcount

    def delete_keyword_alerts_by_url(self, url):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("DELETE FROM keyword_alerts WHERE article_uri = ?", (url,))

            return cursor.rowcount

    def delete_news_search_results_by_topic(self, topic_name):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM news_search_results WHERE topic = ?", (topic_name,))

    def delete_paper_search_results_by_topic(self, topic_name):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM paper_search_results WHERE topic = ?", (topic_name,))

    def delete_article_by_url(self, url):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM articles WHERE uri = ?", (url,))
            return cursor.rowcount

    def check_if_keyword_groups_table_exists(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            return cursor.fetchone()

    def get_all_topics_referenced_in_keyword_groups(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT topic FROM keyword_groups")

            return set(row[0] for row in cursor.fetchall())

    def check_if_articles_table_exists(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='articles'")
            return cursor.fetchone()

    def get_urls_and_topics_from_articles(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT uri, topic
                           FROM articles
                           WHERE topic IS NOT NULL
                             AND topic != ''
                           """)

            return cursor.fetchall()

    def check_if_news_search_results_table_exists(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='news_search_results'")
            return cursor.fetchone()

    def get_urls_and_topics_from_news_search_results(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT nsr.article_uri, nsr.topic
                           FROM news_search_results nsr
                           GROUP BY nsr.article_uri, nsr.topic
                           """)

            cursor.fetchall()

    def get_urls_and_topics_from_paper_search_results(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT psr.article_uri, psr.topic
                           FROM paper_search_results psr
                           GROUP BY psr.article_uri, psr.topic
                           """)

            cursor.fetchall()

    def check_if_articles_table_has_topic_column(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("PRAGMA table_info(articles)")
            columns = cursor.fetchall()

            return any(col[1] == 'topic' for col in columns)

    def check_if_paper_search_results_table_exists(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='paper_search_results'")
            return cursor.fetchone() is not None

    def get_orphaned_urls_from_news_results_and_or_paper_results(self, has_news_results, has_paper_results):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            query = """
                    SELECT a.uri \
                    FROM articles a
                    WHERE 1 = 1 \
                    """

            if has_news_results:
                query += """ AND NOT EXISTS (
                    SELECT 1 FROM news_search_results nsr WHERE nsr.article_uri = a.uri
                )"""

            if has_paper_results:
                query += """ AND NOT EXISTS (
                    SELECT 1 FROM paper_search_results psr WHERE psr.article_uri = a.uri
                )"""

            cursor.execute(query)

            return (row[0] for row in cursor.fetchall())

    def delete_keyword_article_matches_from_new_table_structure_by_url(self, url):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("DELETE FROM keyword_article_matches WHERE article_uri = ?", (url,))
            conn.commit()

            return cursor.rowcount

    def delete_keyword_article_matches_from_old_table_structure_by_url(self, url):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("DELETE FROM keyword_alerts WHERE article_uri = ?", (url,))
            conn.commit()

            return cursor.rowcount

    def delete_news_search_results_by_article_urls(self, placeholders, batch):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(f"DELETE FROM news_search_results WHERE article_uri IN ({placeholders})", batch)
            conn.commit()

    def delete_paper_search_results_by_article_urls(self, placeholders, batch):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(f"DELETE FROM paper_search_results WHERE article_uri IN ({placeholders})", batch)
            conn.commit()

    def delete_articles_by_article_urls(self, placeholders, batch):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(f"DELETE FROM articles WHERE uri IN ({placeholders})", batch)
            conn.commit()

            return cursor.rowcount

    def get_monitor_settings(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT 
                    check_interval,
                    interval_unit,
                    is_enabled,
                    search_date_range,
                    daily_request_limit
                FROM keyword_monitor_settings 
                WHERE id = 1
            """)

            return cursor.fetchone()

    def get_request_count_for_today(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT requests_today, last_reset_date
                           FROM keyword_monitor_status
                           WHERE id = 1
                           """)

            return cursor.fetchone()

    def get_articles_by_url(self, url):
        with self.db.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM articles WHERE uri = ?", (url,))

            return cursor.fetchone()

    def get_raw_articles_markdown_by_url(self, url):
        with self.db.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("SELECT raw_markdown FROM raw_articles WHERE uri = ?", (uri,))

            return cursor.fetchone()

    def update_article_by_url(self, params):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           UPDATE articles
                           SET topic_alignment_score      = ?,
                               keyword_relevance_score    = ?,
                               confidence_score           = ?,
                               overall_match_explanation  = ?,
                               extracted_article_topics   = ?,
                               extracted_article_keywords = ?
                           WHERE uri = ?
                           """, params)

            conn.commit()
            return cursor.rowcount

    def enable_or_disable_auto_ingest(self, toggle):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                           UPDATE keyword_monitor_settings
                           SET auto_ingest_enabled = ?
                           WHERE id = 1
                           """, (toggle.enabled,))

            conn.commit()

    def get_auto_ingest_settings(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT 
                    auto_ingest_enabled,
                    min_relevance_threshold,
                    quality_control_enabled,
                    auto_save_approved_only,
                    default_llm_model,
                    llm_temperature,
                    llm_max_tokens
                FROM keyword_monitor_settings 
                WHERE id = 1
            """)

            return cursor.fetchone()

    def get_processing_statistics(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT COUNT(*)                                               as total_auto_ingested,
                                  COUNT(CASE WHEN ingest_status = 'approved' THEN 1 END) as approved_count,
                                  COUNT(CASE WHEN ingest_status = 'failed' THEN 1 END)   as failed_count,
                                  AVG(quality_score)                                     as avg_quality_score
                           FROM articles
                           WHERE auto_ingested = 1
                           """)

            return cursor.fetchone()

    def stamp_keyword_monitor_status_table_with_todays_date(self, params):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO keyword_monitor_status 
                (id, requests_today, last_check_time, last_reset_date)
                VALUES (1, ?, datetime('now'), ?)
                ON CONFLICT(id) DO UPDATE SET
                    requests_today = excluded.requests_today,
                    last_check_time = excluded.last_check_time,
                    last_reset_date = excluded.last_reset_date
            """, (self.requests_today, today))
            conn.commit()

    def get_keyword_monitor_status_daily_request_limit(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT daily_request_limit FROM keyword_monitor_settings WHERE id = 1")

            return cursor.fetchone()
        
    #### MEDIA BIAS ####
    def create_media_bias_table(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS mediabias (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL UNIQUE,
                    country TEXT,
                    bias TEXT,
                    factual_reporting TEXT,
                    press_freedom TEXT,
                    media_type TEXT,
                    popularity TEXT,
                    mbfc_credibility_rating TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    enabled INTEGER DEFAULT 1
                )
            """)

            conn.commit()

    def check_if_media_bias_has_updated_at_column(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("PRAGMA table_info(mediabias)")

            return [column[1] for column in cursor.fetchall()]

    def add_updated_at_column_to_media_bias_table(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           ALTER TABLE mediabias
                               ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                           """)

            conn.commit()
            
    def create_media_bias_settings_table_and_insert_default_values(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS mediabias_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    enabled BOOLEAN DEFAULT 0,
                    last_updated TIMESTAMP,
                    source_file TEXT
                )
            """)
            
            # Insert default settings if not exist
            cursor.execute("""
                INSERT OR IGNORE INTO mediabias_settings (id, enabled, last_updated, source_file)
                VALUES (1, 0, NULL, NULL)
            """)

            conn.commit()

    def insert_media_bias(self, params):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           INSERT INTO mediabias (source, country, bias, factual_reporting,
                                                  press_freedom, media_type, popularity,
                                                  mbfc_credibility_rating, updated_at, enabled)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 1) ON CONFLICT(source) DO
                           UPDATE SET
                               country = excluded.country,
                               bias = excluded.bias,
                               factual_reporting = excluded.factual_reporting,
                               press_freedom = excluded.press_freedom,
                               media_type = excluded.media_type,
                               popularity = excluded.popularity,
                               mbfc_credibility_rating = excluded.mbfc_credibility_rating,
                               updated_at = CURRENT_TIMESTAMP,
                               enabled = ?
                           """, params)

            conn.commit()

            return cursor.lastrowid

    def update_media_bias_source(self, params):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           UPDATE mediabias
                           SET source                  = ?,
                               country                 = ?,
                               bias                    = ?,
                               factual_reporting       = ?,
                               press_freedom           = ?,
                               media_type              = ?,
                               popularity              = ?,
                               mbfc_credibility_rating = ?,
                               updated_at              = CURRENT_TIMESTAMP,
                               enabled                 = ?
                           WHERE id = ?
                           """, params)

            conn.commit()

    def drop_media_bias_table(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DROP TABLE IF EXISTS mediabias")

    def update_media_bias_settings(self, file_path):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           UPDATE mediabias_settings
                           SET enabled      = 1,
                               source_file  = ?,
                               last_updated = CURRENT_TIMESTAMP
                           WHERE id = 1
                           """, (file_path,))

            conn.commit()

    def get_all_media_bias_sources(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT source,
                                  country,
                                  bias,
                                  factual_reporting,
                                  press_freedom,
                                  media_type,
                                  popularity,
                                  mbfc_credibility_rating
                           FROM mediabias
                           ORDER BY source ASC
                           """)

            return cursor.fetchall()

    def get_media_bias_status(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT enabled, last_updated, source_file
                           FROM mediabias_settings
                           WHERE id = 1
                           """)


            return cursor.fetchone()

    def get_media_bias_source(self, source_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT id FROM mediabias WHERE id = ?", (source_id,))

            return cursor.fetchone()

    def delete_media_bias_source(self, source_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("DELETE FROM mediabias WHERE id = ?", (source_id,))

            conn.commit()

    def get_total_media_bias_sources(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM mediabias")

            return cursor.fetchone()[0]

    def enable_media_bias_sources(self, enabled):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           UPDATE mediabias_settings
                           SET enabled      = ?,
                               last_updated = CURRENT_TIMESTAMP
                           WHERE id = 1
                           """, (1 if enabled else 0,))

            conn.commit()

    def update_media_bias_last_updated(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           UPDATE mediabias_settings
                           SET last_updated = CURRENT_TIMESTAMP
                           WHERE id = 1
                           """)

            conn.commit()

    def reset_media_bias_sources(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Delete all media bias data
            cursor.execute("DELETE FROM mediabias")

            # Reset settings but keep enabled state
            cursor.execute("""
                           UPDATE mediabias_settings
                           SET last_updated = NULL,
                               source_file  = NULL
                           WHERE id = 1
                           """)

            conn.commit()

    def enable_media_source(self, source):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE mediabias SET enabled = 1 WHERE source = ?",
                (source,)
            )
            conn.commit()

    def search_media_bias_sources(self, query, bias_filter, factual_filter, country_filter, page, per_page):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Build base query
            query_parts = ["SELECT * FROM mediabias WHERE 1=1"]
            params = []

            # Add filters
            if query:
                query_parts.append("AND source LIKE ?")
                params.append(f"%{query}%")

            if bias_filter:
                query_parts.append("AND bias LIKE ?")
                params.append(f"%{bias_filter}%")

            if factual_filter:
                query_parts.append("AND factual_reporting LIKE ?")
                params.append(f"%{factual_filter}%")

            if country_filter:
                query_parts.append("AND country LIKE ?")
                params.append(f"%{country_filter}%")

            # Get total count first
            count_query = f"SELECT COUNT(*) FROM ({' '.join(query_parts)})"
            cursor.execute(count_query, params)
            total_count = cursor.fetchone()[0]

            # Add pagination
            query_parts.append("ORDER BY source ASC LIMIT ? OFFSET ?")
            offset = (page - 1) * per_page
            params.extend([per_page, offset])

            # Get data
            cursor.execute(' '.join(query_parts), params)

            return total_count, cursor.fetchall()

    def delete_media_bias_source(self, source_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("DELETE FROM mediabias WHERE id = ?", (source_id,))

            conn.commit()

    def get_media_bias_source_by_id(self, source_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT id,
                                  source,
                                  country,
                                  bias,
                                  factual_reporting,
                                  press_freedom,
                                  media_type,
                                  popularity,
                                  mbfc_credibility_rating
                           FROM mediabias
                           WHERE id = ?
                           """, (source_id,))

            return cursor.fetchone()

    def get_media_bias_filter_options(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Get unique biases
            cursor.execute("SELECT DISTINCT bias FROM mediabias WHERE bias IS NOT NULL AND bias != ''")
            biases = [row[0] for row in cursor.fetchall()]

            # Get unique factual reporting levels
            cursor.execute(
                "SELECT DISTINCT factual_reporting FROM mediabias WHERE factual_reporting IS NOT NULL AND factual_reporting != ''")
            factual_levels = [row[0] for row in cursor.fetchall()]

            # Get unique countries
            cursor.execute("SELECT DISTINCT country FROM mediabias WHERE country IS NOT NULL AND country != ''")
            countries = [row[0] for row in cursor.fetchall()]

            return biases, factual_levels, countries

    def load_media_bias_sources_from_database(self):
        sources = []
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM mediabias")
            rows = cursor.fetchall()

            # Convert to dictionaries with column names
            cursor.execute("PRAGMA table_info(mediabias)")
            columns = [col[1] for col in cursor.fetchall()]

            for row in rows:
                source = {}
                for i, column in enumerate(columns):
                    source[column] = row[i]
                sources.append(source)

            return sources

