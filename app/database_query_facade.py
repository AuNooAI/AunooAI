from datetime import datetime, timedelta
import sqlite3
import json

# TODO SQLAlchemy: Replace all references to sqlite.
# TODO SQLAlchemy:
from sqlalchemy import (select,
                        insert,
                        update,
                        delete,
                        asc,
                        desc,
                        or_,
                        and_,
                        literal,
                        func)

from database_models import (t_keyword_monitor_settings as keyword_monitor_settings,
                             t_keyword_monitor_status as keyword_monitor_status,
                             t_keyword_article_matches as keyword_article_matches,
                             t_articles as articles,
                             t_monitored_keywords as monitored_keywords,
                             t_keyword_groups as keyword_groups,
                             t_analysis_versions as analysis_versions,
                             t_organizational_profiles as organizational_profiles,
                             t_keyword_alerts as keyword_alerts,
                             t_oauth_allowlist as oauth_allowlist,
                             t_oauth_users as oauth_users)


class DatabaseQueryFacade:
    def __init__(self, db, logger):
        self.db = db
        self.logger = logger

        # TODO: Reduce verbosity by "caching" the connection variable here.
        self.connection = self.db._temp_get_connection()

    #### KEYWORD MONITOR QUERIES ####
    def get_keyword_monitor_settings_by_id(self, id):
        return self.connection.execute(
            select(
                keyword_monitor_settings
            ).where(
                keyword_monitor_settings.c.id == id
            )
        ).mappings().fetchone()

    def get_keyword_monitor_status_by_id(self, id):
        return self.connection.execute(
            select(
                keyword_monitor_status
            ).where(
                keyword_monitor_status.c.id == id
            )
        ).mappings().fetchone()

    def update_keyword_monitor_status_by_id(self, id, params):
        self.connection.execute(
            update(
                keyword_monitor_status
            ).where(
                keyword_monitor_status.c.id == id
            ).values(
                **params
            ))

        self.connection.commit()

    # TODO: Deprecate in favour of the function it augments.
    # TODO: Add back creation as part of a migration? Investigate best approach.
    # TODO: Remove _create from name once creation is moved to migrations.
    def get_or_create_keyword_monitor_settings(self):
        return self.get_keyword_monitor_settings_by_id(1)

    def get_keyword_monitoring_provider(self):
        row = self.get_keyword_monitor_settings_by_id(1)
        # TODO: Make this default configurable?
        provider = row['provider'] if row else 'newsapi'
        return provider

    def get_keyword_monitoring_counter(self):
        return self.get_keyword_monitor_status_by_id(1)

    # TODO: Should be a named parameter instead of a tuple.
    def reset_keyword_monitoring_counter(self, params):
        self.update_keyword_monitor_status_by_id(
            1,
            {
                "last_reset_date": params[0],
                "requests_today": 0
            })

    def create_keyword_monitor_status(self, params):
        self.connection.execute(insert(keyword_monitor_status).values(**params))
        self.connection.commit()

    def create_or_update_keyword_monitor_last_check(self, params):
        # Check if keyword monitor status record exists.
        # TODO: This will be potentially inefficient, however, there is no ON CONFLICT SQL standard, and as such we emulate it.
        keyword_monitor_status_record = self.get_keyword_monitor_status_by_id(1)

        # If it exists, update it.
        if keyword_monitor_status_record:
            self.update_keyword_monitor_status_by_id(
                1,
                {
                    "last_check_time": params[0],
                    "requests_today": params[1]
                }
            )
        # If not, then just create it.
        else:
            self.create_keyword_monitor_status({
                    "id": 1,
                    "last_check_time": params[0],
                    "requests_today": params[1]
                })


    def get_monitored_keywords(self):
        statement = select(
                monitored_keywords.c.id,
                monitored_keywords.c.keyword,
                monitored_keywords.c.last_checked,
                keyword_groups.c.topic
            ).select_from(
                monitored_keywords
                .join(keyword_groups, monitored_keywords.c.group_id == keyword_groups.c.id)
            )
        return self.connection.execute(statement).fetchall()

    def get_monitored_keywords_for_topic(self, params):
        statement = select(
            monitored_keywords.c.keyword
            ).select_from(
                monitored_keywords
                .join(keyword_groups, monitored_keywords.c.group_id == keyword_groups.c.id)
            ).where(
                keyword_groups.c.topic == params[0]
            )
        rows = self.connection.execute(statement).fetchall()
        topic_keywords = [row[0] for row in rows]
        return topic_keywords

    def article_exists(self, params):
        article_exists =  self.connection.execute(
            select(articles.c.uri).where(articles.c.uri == params[0])
        ).fetchone()
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
        statement = update(monitored_keywords).where(monitored_keywords.c.id == params[1]).values(last_checked = params[0])
        self.connection.execute(statement)
        self.connection.commit() 

    def update_keyword_monitor_counter(self, params):
        statement = update(keyword_monitor_status).where(keyword_monitor_status.c.id == 1).values(requests_today = params[0])
        self.connection.execute(statement)
        self.connection.commit() 


    def create_keyword_monitor_log_entry(self, params):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           INSERT INTO keyword_monitor_status (id, last_check_time, last_error, requests_today)
                           VALUES (1, ?, ?, ?) ON CONFLICT(id) DO
                           UPDATE SET
                               last_check_time = excluded.last_check_time,
                               last_error = excluded.last_error,
                               requests_today = excluded.requests_today
                           """, params)
            conn.commit()

    def get_keyword_monitor_polling_enabled(self):
        statement = select(
            keyword_monitor_settings.c.is_enabled
        ).where(
            keyword_monitor_settings.c.id == 1
        )
        row = self.connection.execute(statement).fetchone()
        is_enabled = row[0] if row and row[0] is not None else True
        return is_enabled

    def get_keyword_monitor_interval(self):
        statement = select(
            keyword_monitor_settings.c.check_interval,
            keyword_monitor_settings.c.interval_unit
        ).where(
            keyword_monitor_settings.c.id == 1
        )
        return self.connection.execute(statement).fetchone()

    #### RESEARCH QUERIES ####
    def get_article_by_url(self, url):
        statement = select(
            [1]
        ).where(
            articles.c.uri == url
        )
        return self.connection.execute(statement).fetchone()

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

    def save_analysis_version(self, params):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            insert_query = """
                           INSERT INTO analysis_versions (topic, version_data, model_used, analysis_depth)
                           VALUES (?, ?, ?, ?) \
                           """
            cursor.execute(insert_query, params)

            conn.commit()

    def get_latest_analysis_version(self, topic):
        statement = select(
            analysis_versions.c.version_data
        ).where(
            analysis_versions.c.topic == topic
        ).order_by(
            analysis_versions.c.created_at.desc()
        ).limit(1)
        return self.connection.execute(statement).fetchone()

    def get_articles_with_dynamic_limit(
            self,
            consistency_mode,
            topic,
            start_date,
            end_date,
            optimal_sample_size
    ):
        # Hacky.
        from enum import Enum
        class ConsistencyMode(str, Enum):
            DETERMINISTIC = "deterministic"  # Maximum consistency, temp=0.0
            LOW_VARIANCE = "low_variance"  # High consistency, temp=0.2
            BALANCED = "balanced"  # Good balance, temp=0.4
            CREATIVE = "creative"  # Current behavior, temp=0.7

        # Fetch more articles for deterministic selection to ensure good diversity
        fetch_multiplier = 2 if consistency_mode in [ConsistencyMode.DETERMINISTIC, ConsistencyMode.LOW_VARIANCE] else 1

        statement = select(
            articles.c.title,
            articles.c.summary,
            articles.c.uri,
            articles.c.publication_date,
            articles.c.sentiment,
            articles.c.category,
            articles.c.future_signal,
            articles.c.driver_type,
            articles.c.time_to_impact
        ).where(
            and_(
                articles.c.topic == topic,
                articles.c.publication_date >= start_date.isoformat(),
                articles.c.publication_date <= end_date.isoformat(),
                articles.c.summary != '',
                articles.c.summary != None,
            )
        )
        if consistency_mode in [ConsistencyMode.DETERMINISTIC, ConsistencyMode.LOW_VARIANCE]:
            statement = statement.order_by(articles.c.publication_date.desc(), articles.c.title.asc())
        else:
            statement = statement.order_by(articles.c.publication_date.desc())

        statement = statement.limit(optimal_sample_size * fetch_multiplier)

        return self.connection.execute(statement).fetchall() 

    def get_organisational_profile(self, profile_id):
        statement = select(
            organizational_profiles.c.id,
            organizational_profiles.c.name,
            organizational_profiles.c.description,
            organizational_profiles.c.industry,
            organizational_profiles.c.organization_type,
            organizational_profiles.c.region,
            organizational_profiles.c.key_concerns,
            organizational_profiles.c.strategic_priorities,
            organizational_profiles.c.risk_tolerance,
            organizational_profiles.c.innovation_appetite,
            organizational_profiles.c.decision_making_style,
            organizational_profiles.c.stakeholder_focus,
            organizational_profiles.c.competitive_landscape,
            organizational_profiles.c.regulatory_environment,
            organizational_profiles.c.custom_context
        ).where(
            organizational_profiles.c.id == profile_id
        )
        return self.connection.execute(statement).fetchone() 

    def get_organisational_profiles(self):
        statement = select(
            organizational_profiles.c.id,
            organizational_profiles.c.name,
            organizational_profiles.c.description,
            organizational_profiles.c.industry,
            organizational_profiles.c.organization_type,
            organizational_profiles.c.region,
            organizational_profiles.c.key_concerns,
            organizational_profiles.c.strategic_priorities,
            organizational_profiles.c.risk_tolerance,
            organizational_profiles.c.innovation_appetite,
            organizational_profiles.c.decision_making_style,
            organizational_profiles.c.stakeholder_focus,
            organizational_profiles.c.competitive_landscape,
            organizational_profiles.c.regulatory_environment,
            organizational_profiles.c.custom_context,
            organizational_profiles.c.is_default,
            organizational_profiles.c.created_at,
            organizational_profiles.c.updated_at
        ).order_by(
            organizational_profiles.c.is_default.desc(),
            organizational_profiles.c.name.asc()
        )
        return self.connection.execute(statement).fetchall() 

    def create_organisational_profile(self, params):
        insert_query = """
                       INSERT INTO organizational_profiles (name, description, industry, organization_type, region, \
                                                            key_concerns, \
                                                            strategic_priorities, risk_tolerance, innovation_appetite, \
                                                            decision_making_style, stakeholder_focus, \
                                                            competitive_landscape, \
                                                            regulatory_environment, custom_context) \
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) \
                       """

        return self.db.execute_query(insert_query, params)

    def delete_organisational_profile(self, profile_id):
        statement = delete(organizational_profiles).where(organizational_profiles.c.id == profile_id)
        self.connection.execute(statement)
        self.connection.commit() 

    def get_organisational_profile_by_name(self, name):
        statement = select(
            organizational_profiles.c.id
        ).where(
            organizational_profiles.c.name == name
        )
        return self.connection.execute(statement).fetchone()

    def get_organisational_profile_by_id(self, profile_id):
        statement = select(
            organizational_profiles.c.id
        ).where(
            organizational_profiles.c.id == profile_id
        )
        return self.connection.execute(statement).fetchone()

    def get_organizational_profile_for_ui(self, profile_id):
        statement = select(
            organizational_profiles.c.id,
            organizational_profiles.c.name,
            organizational_profiles.c.description,
            organizational_profiles.c.industry,
            organizational_profiles.c.organization_type,
            organizational_profiles.c.region,
            organizational_profiles.c.key_concerns,
            organizational_profiles.c.strategic_priorities,
            organizational_profiles.c.risk_tolerance,
            organizational_profiles.c.innovation_appetite,
            organizational_profiles.c.decision_making_style,
            organizational_profiles.c.stakeholder_focus,
            organizational_profiles.c.competitive_landscape,
            organizational_profiles.c.regulatory_environment,
            organizational_profiles.c.custom_context,
            organizational_profiles.c.is_default,
            organizational_profiles.c.created_at,
            organizational_profiles.c.updated_at
        ).where(
            organizational_profiles.c.id == profile_id
        )
        return self.connection.execute(statement).fetchone()

    def check_organisational_profile_name_conflict(self, name, profile_id):
        statement = select(
            organizational_profiles.c.id
        ).where(
            and_(
                organizational_profiles.c.name == name,
                organizational_profiles.c.id != profile_id
            )
        )
        return self.connection.execute(statement).fetchone()

    def update_organisational_profile(self, params):
        statement = update(
            organizational_profiles
        ).where(
            organizational_profiles.c.id == params[14]
        ).values(
            name = params[0],
            description = params[1],
            industry = params[2],
            organization_type = params[3],
            region = params[4],
            key_concerns = params[5],
            strategic_priorities = params[6],
            risk_tolerance = params[7],
            innovation_appetite = params[8],
            decision_making_style = params[9],
            stakeholder_focus = params[10],
            competitive_landscape = params[11],
            regulatory_environment = params[12],
            custom_context = params[13],
            updated_at = func.current_timestamp()
        )
        self.connection.execute(statement)
        self.connection.commit() 


    def check_if_profile_exists_and_is_not_default(self, profile_id):
        statement = select(
            organizational_profiles.c.is_default
        ).where(
            organizational_profiles.c.id == profile_id
        )
        return self.connection.execute(statement).fetchone()

    #### AUTOMATED INGEST SERVICE ####
    def get_configured_llm_model(self):
        statement = select(
            keyword_monitor_settings.c.default_llm_model,
            keyword_monitor_settings.c.llm_temperature,
            keyword_monitor_settings.c.llm_max_tokens
        ).where(
            keyword_monitor_settings.c.id == 1
        )
        settings = self.connection.execute(statement).fetchone()
        if settings: 
            return settings[0] or "gpt-4o-mini"

    def get_llm_parameters(self):
        statement = select(
            keyword_monitor_settings.c.llm_temperature,
            keyword_monitor_settings.c.llm_max_tokens
        ).where(
            keyword_monitor_settings.c.id == 1
        )
        return self.connection.execute(statement).fetchone()

    def save_approved_article(self, params):
        statement = update(
            articles
        ).where(
            articles.c.uri == params[16]
        ).values(
            title = func.coalesce(params[0], articles.c.title),
            summary = func.coalesce(params[1], articles.c.summary),
            auto_ingested = 1,
            ingest_status = params[2],
            quality_score = params[3],
            quality_issues = params[4],
            category = params[5],
            sentiment = params[6],
            bias = params[7],
            factual_reporting = params[8],
            mbfc_credibility_rating = params[9],
            bias_source = params[10],
            bias_country = params[11],
            press_freedom = params[12],
            media_type = params[13],
            popularity = params[14],
            topic_alignment_score = params[15],
            keyword_relevance_score = params[16],
            future_signal = params[17],
            future_signal_explanation = params[18],
            sentiment_explanation = params[19],
            time_to_impact = params[20],
            driver_type = params[21],
            tags = params[22],
            analyzed = 1,
            confidence_score = params[23],
            overall_match_explanation = params[24]
        )
        self.connection.execute(statement)
        self.connection.commit() 

    def get_min_relevance_threshold(self):
        statement = select(
            keyword_monitor_settings.c.min_relevance_threshold
        ).where(
            keyword_monitor_settings.c.id == 1
        )
        settings = self.connection.execute(statement).fetchone()
        if settings and settings[0] is not None:
            return float(settings[0])

    def get_auto_ingest_settings(self):
        statement = select(
            keyword_article_matches.c.auto_ingest_enabled,
            keyword_article_matches.c.min_relevance_threshold,
            keyword_article_matches.c.quality_control_enabled,
            keyword_article_matches.c.auto_save_approved_only,
            keyword_article_matches.c.default_llm_model,
            keyword_article_matches.c.llm_temperature,
            keyword_article_matches.c.llm_max_tokens
        ).where(
            keyword_article_matches.c.id == 1
        )
        return self.connection.execute(statement).fetchone()

    def update_ingested_article(self, params):
        statement = update(
            articles
        ).where(
            articles.c.uri == params[3]
        ).values(
            auto_ingested = 1,
            ingest_status = params[0],
            quality_score = params[1],
            quality_issues = params[2]
        )
        self.connection.execute(statement)
        self.connection.commit() 

    def get_topic_articles_to_ingest_using_new_table_structure(self, topic_id):
        statement = select(
            articles.c.uri,
            articles.c.title,
            articles.c.summary,
            articles.c.news_source,
            keyword_groups.c.topic
        ).select_from(
            articles
            .join(keyword_article_matches, articles.c.uri == keyword_article_matches.c.article_uri)
            .join(keyword_groups, keyword_article_matches.c.group_id == keyword_groups.c.id)
        ).where(
            keyword_groups.c.topic == topic_id
        ).order_by(
            keyword_article_matches.c.detected_at.desc()
        )
        return self.connection.execute(statement).fetchall()

    def get_topic_articles_to_ingest_using_old_table_structure(self, topic_id):
        statement = select(
            articles.c.uri,
            articles.c.title,
            articles.c.summary,
            articles.c.news_source,
            keyword_groups.c.topic
        ).select_from(
            articles
            .join(keyword_alerts, articles.c.uri == keyword_alerts.c.article_uri)
            .join(monitored_keywords, keyword_alerts.c.keyword_id == monitored_keywords.c.id)
            .join(keyword_groups, monitored_keywords.c.group_id == keyword_groups.c.id)
        ).where(
            keyword_groups.c.topic == topic_id
        ).order_by(
            keyword_alerts.c.detected_at.desc()
        )
        return self.connection.execute(statement).fetchall()

    def get_topic_unprocessed_and_unread_articles_using_new_table_structure(self, topic_id):
        statement = select(
            articles.c.uri,
            articles.c.title,
            articles.c.summary,
            articles.c.news_source,
            keyword_groups.c.topic
        ).select_from(
            articles
            .join(keyword_article_matches, articles.c.uri == keyword_article_matches.c.article_uri)
            .join(keyword_groups, keyword_article_matches.c.group_id == keyword_groups.c.id)
        ).where(
            and_(
                keyword_groups.c.topic == topic_id,
                keyword_article_matches.c.is_read == 0,
                or_(
                    keyword_article_matches.c.auto_ingested == 0,
                    keyword_article_matches.c.auto_ingested == None
                )
            )
        ).distinct().order_by(
            desc(keyword_article_matches.c.detected_at)
        )
        return self.connection.execute(statement).fetchall()

    def get_topic_unprocessed_and_unread_articles_using_old_table_structure(self, topic_id):
        statement = select(
            articles.c.uri,
            articles.c.title,
            articles.c.summary,
            articles.c.news_source,
            keyword_groups.c.topic
        ).select_from(
            articles
            .join(keyword_alerts, articles.c.uri == keyword_alerts.c.article_uri)
            .join(monitored_keywords, keyword_alerts.c.keyword_id == monitored_keywords.c.id)
            .join(keyword_groups, monitored_keywords.c.group_id == keyword_groups.c.id)
        ).where(
            and_(
                keyword_groups.c.topic == topic_id,
                keyword_alerts.c.is_read == 0,
                or_(
                    keyword_alerts.c.auto_ingested == 0,
                    keyword_alerts.c.auto_ingested == None
                )
            )
        ).distinct().order_by(
            desc(keyword_alerts.c.detected_at)
        )
        return self.connection.execute(statement).fetchall()

    def get_topic_keywords(self, topic_id):
        statement = select(
            monitored_keywords.c.keyword
        ).select_from(
            monitored_keywords
            .join(keyword_groups, monitored_keywords.c.group_id == keyword_groups.c.id)
        ).where(
            keyword_groups.c.topic == topic_id
        )
        rows = self.connection.execute(statement).fetchall()
        topic_keywords = [row[0] for row in rows]
        return topic_keywords

    #### EXECUTIVE SUMMARY ROUTES ####
    def get_articles_for_market_signal_analysis(self, timeframe_days, topic_name):
        #caluclate the date 'now' - timeframe_days days
        start_date = datetime.utcnow() - timedelta(days=timeframe_days)

        statement = select(
            articles.c.uri,
            articles.c.title,
            articles.c.summary,
            articles.c.future_signal,
            articles.c.sentiment,
            articles.c.time_to_impact,
            articles.c.driver_type,
            articles.c.category,
            articles.c.publication_date,
            articles.c.news_source
        ).where(
            and_(
                articles.c.topic == topic_name,
                articles.c.publication_date >= start_date,
                articles.c.analyzed == 1
            )
        ).order_by(
            desc(articles.c.publication_date)
        ).limit(50)
        return self.connection.execute(statement).fetchall()

    def get_recent_articles_for_market_signal_analysis(self, timeframe_days, topic_name, optimal_sample_size):
        start_date = datetime.utcnow() - timedelta(days=timeframe_days)
        
        statement = select(
            articles.c.uri,
            articles.c.title,
            articles.c.summary,
            articles.c.future_signal,
            articles.c.sentiment,
            articles.c.time_to_impact,
            articles.c.driver_type,
            articles.c.category,
            articles.c.publication_date,
            articles.c.news_source
        ).where(
            and_(
                articles.c.topic == topic_name,
                articles.c.publication_date >= start_date,
                articles.c.analyzed == 1,
                articles.c.summary != None,
                articles.c.summary != ''
            )
        ).order_by(
            desc(articles.c.publication_date)
        ).limit(optimal_sample_size)
        return self.connection.execute(statement).fetchall()

    def get_topic_filtered_future_signals_with_counts_for_market_signal_analysis(self, topic_name):
        # We need actual counts, not just the config list
        query = """
                SELECT future_signal, COUNT(*) as count
                FROM articles
                WHERE topic = ?
                  AND future_signal IS NOT NULL
                  AND future_signal != ''
                  AND analyzed = 1
                GROUP BY future_signal
                ORDER BY count DESC \
                """

        return self.db.fetch_all(query, (topic_name,))

    #### TOPIC MAP ROUTES ####
    def get_unique_topics(self):
        statement = select(
            articles.c.topic
        ).where(
            and_(
                articles.c.topic != None,
                articles.c.topic != '',
                articles.c.analyzed == 1)
        ).distinct().order_by(
            articles.c.topic.asc()
        )
        rows = self.connection.execute(statement).fetchall()

        return [row[0] for row in rows] 


    def get_unique_categories(self):
        statement = select(
            articles.c.category
        ).where(
            and_(
                articles.c.category != None,
                articles.c.category != '',
                articles.c.analyzed == 1)
        ).distinct().order_by(
            articles.c.category.asc()
        )
        rows = self.connection.execute(statement).fetchall()
        return [row[0] for row in rows] 


    #### OAUTH USERS ####
    def count_oauth_allowlist_active_users(self):
        statement = select(func.count()).where(oauth_allowlist.c.is_active == 1)
        return self.connection.execute(statement).fetchone()[0] 

    def get_oauth_allowlist_user_by_email_and_provider(self, email, provider):
        statement = select(
            oauth_users
        ).where(
            and_(
                oauth_users.c.email == email,
                oauth_users.c.provider == provider
            )
        )
        return self.connection.execute(statement).fetchone() 

    def get_oauth_allowlist_user_by_id(self, user_id):
        statement = select(
            oauth_users
        ).where(
            oauth_users.c.id == user_id
        )
        return self.connection.execute(statement).fetchone() 


    def get_oauth_active_users_by_provider(self, provider):
        statement = select(
            oauth_users
        ).where(
            and_(
                oauth_users.c.provider == provider,
                oauth_users.c.is_active == 1
            )
        ).order_by(
            oauth_users.c.created_at.desc()
        )
        return self.connection.execute(statement).fetchall() 

    def is_oauth_user_allowed(self, email):
        statement = select(func.count()).where(oauth_allowlist.c.email == email, oauth_allowlist.c.is_active == 1)
        count = self.connection.execute(statement).fetchone()[0]
        return count > 0 

    def add_oauth_user_to_allowlist(self, email, added_by):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO oauth_allowlist (email, added_by) VALUES (?, ?)",
                (email.lower(), added_by)
            )
            conn.commit()

    def remove_oauth_user_from_allowlist(self, email):
        statement = update(
            oauth_allowlist
        ).where(
            oauth_allowlist.c.email == email
        ).values(
            is_active = 0
        )
        result = self.connection.execute(statement)
        self.connection.commit()
        return result.rowcount 
    
    def get_oauth_active_users(self, provider):
        statement = select(
            oauth_users
        ).where(
            and_(
                oauth_users.c.provider == provider,
                oauth_users.c.is_active == 1
            )
        ).order_by(
            oauth_users.c.created_at.desc()
        )
        return self.connection.execute(statement).fetchall() 

    def deactivate_user(self, email, provider):
        statement = update(
            oauth_users
        ).where(
            and_(
                oauth_users.c.email == email,
                oauth_users.c.provider == provider
            )
        ).values(
            is_active = 0
        )
        result = self.connection.execute(statement)
        self.connection.commit()

        return result.rowcount 

    def get_active_oauth_allowlist_user_by_id(self, user_id):
        statement = select(
            oauth_users
        ).where(
            and_(
                oauth_users.c.id == user_id,
                oauth_users.c.is_active == 1
            )
        )
        return self.connection.execute(statement).fetchone() 

    def get_active_oauth_allowlist_user_by_email_and_provider(self, email, provider):
        statement = select(
            oauth_users
        ).where(
            and_(
                oauth_users.c.email == email,
                oauth_users.c.provider == provider,
                oauth_users.c.is_active == 1
            )
        )
        return self.connection.execute(statement).fetchone() 
    def update_oauth_allowlist_user(self, params):
        statement = update(
            oauth_users
        ).where(
            and_(
                oauth_users.c.email == params[3],
                oauth_users.c.provider == params[4]
            )
        ).values(
            name = params[0],
            provider_id = params[1],
            avatar_url = params[2],
            last_login = func.current_timestamp()
        )
        self.connection.execute(statement)
        self.connection.commit() 

    def create_oauth_allowlist_user(self, params):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           INSERT INTO oauth_users (email, name, provider, provider_id, avatar_url)
                           VALUES (?, ?, ?, ?, ?)
                           """, params)

            conn.commit()

            return cursor.lastrowid

    #### ENDPOINT QUERIES ####
    def get_oauth_allow_list(self):
        with self.db.get_connection() as conn:
            statement = select(
                oauth_allowlist.c.email,
                oauth_allowlist.c.added_by,
                oauth_allowlist.c.added_at,
                oauth_allowlist.c.is_active
            ).order_by(
                oauth_allowlist.c.added_at.desc()
            )
            return self.connection.execute(statement).fetchall() 

    def get_oauth_system_status_and_settings(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Count allowlist entries
            cursor.execute("SELECT COUNT(*) FROM oauth_allowlist WHERE is_active = 1")
            allowlist_count = cursor.fetchone()[0]

            # Count OAuth users
            cursor.execute("SELECT COUNT(*) FROM oauth_users WHERE is_active = 1")
            oauth_users_count = cursor.fetchone()[0]

            # Get recent logins
            cursor.execute("""
                           SELECT provider, COUNT(*) as count
                           FROM oauth_users
                           WHERE is_active = 1
                           GROUP BY provider
                           """)
            provider_stats = {row[0]: row[1] for row in cursor.fetchall()}

            return allowlist_count, oauth_users_count, provider_stats

    def get_feed_item_tags(self, item_id):
        statement = select(
            feed_items.c.tags
        ).where(
            feed_items.c.id == item_id
        )
        return self.connection.execute(statement).fetchone() 

    def get_feed_item_url(self, item_id):
        statement = select(
            feed_items.c.url
        ).where(
            feed_items.c.id == item_id
        )
        return self.connection.execute(statement).fetchone() 

    def get_enrichment_data_for_article(self, item_url):
        statement = select(
            articles.c.category,
            articles.c.sentiment,
            articles.c.driver_type,
            articles.c.time_to_impact,
            articles.c.topic_alignment_score,
            articles.c.keyword_relevance_score,
            articles.c.confidence_score,
            articles.c.overall_match_explanation,
            articles.c.extracted_article_topics,
            articles.c.extracted_article_keywords,
            articles.c.auto_ingested,
            articles.c.ingest_status,
            articles.c.quality_score,
            articles.c.quality_issues,
            articles.c.sentiment_explanation,
            articles.c.future_signal,
            articles.c.future_signal_explanation,
            articles.c.driver_type_explanation,
            articles.c.time_to_impact_explanation,
            articles.c.summary,
            articles.c.tags,
            articles.c.submission_date,
            articles.c.analyzed
        ).where(
            articles.c.uri == item_url
        )
        return self.connection.execute(statement).fetchone() 

    def get_enrichment_data_for_article_with_extra_fields(self, item_url):
        statement = select(
            articles.c.category,
            articles.c.sentiment,
            articles.c.driver_type,
            articles.c.time_to_impact,
            articles.c.topic_alignment_score,
            articles.c.keyword_relevance_score,
            articles.c.confidence_score,
            articles.c.overall_match_explanation,
            articles.c.extracted_article_topics,
            articles.c.extracted_article_keywords,
            articles.c.auto_ingested,
            articles.c.ingest_status,
            articles.c.quality_score,
            articles.c.quality_issues,
            articles.c.sentiment_explanation,
            articles.c.future_signal,
            articles.c.future_signal_explanation,
            articles.c.driver_type_explanation,
            articles.c.time_to_impact_explanation,
            articles.c.summary,
            articles.c.tags,
            articles.c.topic
        ).where(
            articles.c.uri == item_url
        )
        return self.connection.execute(statement).fetchone() 

    def update_feed_article_data(self, params):
        statement = update(
            articles
        ).where(
            articles.c.uri == params[4]
        ).values(
            analyzed = 1,
            title = func.coalesce(articles.c.title, params[0]),
            summary = func.coalesce(articles.c.summary, params[1]),
            news_source = func.coalesce(articles.c.news_source, params[2]),
            publication_date = func.coalesce(articles.c.publication_date, params[3]),
            topic = func.coalesce(articles.c.topic, 'General')
        )
        self.connection.execute(statement)
        self.connection.commit() 

    def extract_topics_from_article(self, topic_filter, category_filter, limit):
        statement = select(
            articles.c.uri,
            articles.c.title,
            articles.c.summary,
            articles.c.topic,
            articles.c.category,
            articles.c.tags,
            articles.c.sentiment,
            articles.c.future_signal,
            articles.c.driver_type,
            articles.c.time_to_impact,
            articles.c.submission_date
        ).where(
            articles.c.analyzed == 1,
            articles.c.summary != None,
            articles.c.summary != '',
            articles.c.summary.length() > 50
        )
        if topic_filter:
            statement = statement.where(
                articles.c.topic == topic_filter
            )
        if category_filter:
            statement = statement.where(
                articles.c.category == category_filter
            )
        statement = statement.order_by(
            articles.c.submission_date.desc()
        )
        if limit:
            statement = statement.limit(limit)
        return self.connection.execute(statement).fetchall() 

    def create_feed_group(self, params):
        statement = insert(
            feed_keyword_groups
        ).values(
            name = params[0],
            description = params[1],
            color = params[2],
            created_at = params[3],
            updated_at = params[4]
        )
        result = self.connection.execute(statement)
        self.connection.commit()
        return result.lastrowid 

    def get_feed_groups_including_inactive(self):
        statement = select(
            feed_keyword_groups
        ).order_by(
            feed_keyword_groups.c.name
        )
        return self.connection.execute(statement).fetchall() 



    def get_feed_groups_excluding_inactive(self):
        statement = select(
            feed_keyword_groups
        ).where(
            feed_keyword_groups.c.is_active == 1
        ).order_by(
            feed_keyword_groups.c.name
        )
        return self.connection.execute(statement).fetchall() 

    def get_feed_group_sources(self, group_id):
        statement = select(
            feed_group_sources.c.id,
            feed_group_sources.c.source_type,
            feed_group_sources.c.keywords,
            feed_group_sources.c.enabled,
            feed_group_sources.c.last_checked,
            feed_group_sources.c.created_at
        ).where(
            feed_group_sources.c.group_id == group_id
        ).order_by(
            feed_group_sources.c.source_type.asc()
        )
        return self.connection.execute(statement).fetchall() 

    def get_feed_group_by_id(self, group_id):
        statement = select(
            feed_keyword_groups
        ).where(
            feed_keyword_groups.c.id == group_id
        )
        return self.connection.execute(statement).fetchone() 

    def update_feed_group(self, name, description, color, is_active, group_id):
        statement = update(
            feed_keyword_groups
        ).where(
            feed_keyword_groups.c.id == group_id
        )
        if name is not None:
            statement = statement.values(
                name = name
            )
        if description is not None:
            statement = statement.values(
                description = description
            )
        if color is not None:
            statement = statement.values(
                color = color
            )
        if is_active is not None:
            statement = statement.values(
                is_active = is_active
            )
        statement = statement.values(
            updated_at = datetime.now().isoformat()
        )
        self.connection.execute(statement)
        self.connection.commit() 

    def delete_feed_group(self, group_id):
        statement = delete(
            feed_keyword_groups
        ).where(
            feed_keyword_groups.c.id == group_id
        )
        self.connection.execute(statement)
        self.connection.commit() 

    def create_default_feed_subscription(self, group_id):
        statement = insert(
            user_feed_subscriptions
        ).values(
            group_id = group_id
        )
        self.connection.execute(statement)
        self.connection.commit() 

    def update_group_source(self, source_id, keywords, enabled, date_range_days, custom_start_date, custom_end_date):
        statement = update(
            feed_group_sources
        ).where(
            feed_group_sources.c.id == source_id
        )
        if keywords is not None:
            statement = statement.values(
                keywords = json.dumps(keywords)
            )
        if enabled is not None:
            statement = statement.values(
                enabled = enabled
            )
        if date_range_days is not None:
            statement = statement.values(
                date_range_days = date_range_days
            )
        if custom_start_date is not None:
            statement = statement.values(
                custom_start_date = custom_start_date
            )
        if custom_end_date is not None:
            statement = statement.values(
                custom_end_date = custom_end_date
            )
        self.connection.execute(statement)
        self.connection.commit() 


    def get_source_by_id(self, source_id):
        statement = select(
            feed_group_sources
        ).where(
            feed_group_sources.c.id == source_id
        )
        return self.connection.execute(statement).fetchone() 

    def get_group_source(self, group_id, source_type):
        statement = select(
            feed_group_sources.c.id
        ).where(
            feed_group_sources.c.group_id == group_id,
            feed_group_sources.c.source_type == source_type
        )
        return self.connection.execute(statement).fetchone() 

    def delete_group_source(self, source_id):
        statement = delete(
            feed_group_sources
        ).where(
            feed_group_sources.c.id == source_id
        )
        self.connection.execute(statement)
        self.connection.commit() 

    def add_source_to_group(self, params):
        statement = insert(
            feed_group_sources
        ).values(
            group_id = params[0],
            source_type = params[1],
            keywords = params[2],
            enabled = params[3],
            date_range_days = params[4],
            custom_start_date = params[5],
            custom_end_date = params[6],
            created_at = params[7]
        )
        result = self.connection.execute(statement)
        self.connection.commit() 
        return result.lastrowid 

    def get_feed_group_by_name(self, name):
        statement = select(
            feed_keyword_groups.c.id
        ).where(
            feed_keyword_groups.c.name == name
        )
        return self.connection.execute(statement).fetchone() 

    def get_keyword_groups_count(self):
        statement = select(
            func.count()
        ).select_from(
            feed_keyword_groups
        )
        return self.connection.execute(statement).fetchone()[0] 

    def get_feed_item_count(self):
        statement = select(
            func.count()
        ).select_from(
            feed_items
        )
        return self.connection.execute(statement).fetchone()[0] 

    def get_article_id_by_url(self, url):
        statement = select(
            articles.c.id
        ).where(
            articles.c.uri == url
        )
        article_result = self.connection.execute(statement).fetchone()

        return article_result[0] if article_result else None 

    def check_if_article_exists_with_enrichment(self, url):
        statement = select(
            articles.c.id
        ).where(
            articles.c.uri == url,
            articles.c.analyzed == 1
        )
        return self.connection.execute(statement).fetchone()

    def create_article_without_enrichment(self, params):
        statement = insert(
            articles
        ).values(
            uri = params[0],
            title = params[1],
            summary = params[2],
            news_source = params[3],
            publication_date = params[4],
            submission_date = func.now(),
            analyzed = 0,
            topic = 'General'
        )
        result = self.connection.execute(statement)
        self.connection.commit()
        return result.lastrowid 


    def get_feed_item_details(self, item_id):
        statement = select(
            feed_items.c.url,
            feed_items.c.title,
            feed_items.c.content,
            feed_items.c.author,
            feed_items.c.publication_date,
            feed_items.c.source_type,
            feed_items.c.group_id
        ).where(
            feed_items.c.id == item_id
        )
        return self.connection.execute(statement).fetchone() 

    def update_feed_tags(self, params):
        statement = update(
            feed_items
        ).where(
            feed_items.c.id == params[1]
        ).values(
            tags = params[0],
            updated_at = func.now()
        )
        self.connection.execute(statement)
        self.connection.commit() 

    def get_feed_keywords_by_source_type(self, source_type):
        statement = select(
            feed_keyword_groups.c.id,
            feed_keyword_groups.c.name
        ).select_from(
            feed_keyword_groups.join(
                feed_group_sources,
                feed_keyword_groups.c.id == feed_group_sources.c.group_id
            ).where(
                feed_keyword_groups.c.is_active == 1,
                feed_group_sources.c.source_type == source_type,
                feed_group_sources.c.enabled == 1
            )
        ).distinct()

        return self.connection.execute(statement).fetchall() 

    def get_statistics_for_specific_feed_group(self, group_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Get total items count
            cursor.execute("""
                           SELECT COUNT(*)
                           FROM feed_items
                           WHERE group_id = ?
                           """, (group_id,))
            total_items = cursor.fetchone()[0]

            # Get counts by source type
            cursor.execute("""
                           SELECT source_type, COUNT(*)
                           FROM feed_items
                           WHERE group_id = ?
                           GROUP BY source_type
                           """, (group_id,))
            source_counts = dict(cursor.fetchall())

            # Get recent items count (last 7 days)
            cursor.execute("""
                           SELECT COUNT(*)
                           FROM feed_items
                           WHERE group_id = ?
                             AND publication_date >= datetime('now', '-7 days')
                           """, (group_id,))
            recent_items = cursor.fetchone()[0]

            return total_items, source_counts, recent_items

    def get_is_keyword_monitor_enabled(self):
        settings = self.get_keyword_monitor_settings_by_id(1)
        return bool(settings['is_enabled']) if settings and settings['is_enabled'] else False

    def get_keyword_monitor_last_check_time(self):
        statement = select(
            func.max(keyword_monitor_checks.c.check_time)
        )

        return self.connection.execute(statement).fetchone().scalar() 

    def get_unread_alerts(self):
        statement = select(
            keyword_alerts.c.id,
            keyword_alerts.c.group_id,
            keyword_alerts.c.detected_at,
            keyword_alerts.c.matched_keyword,
            articles.c.uri,
            articles.c.title,
            articles.c.url,
            articles.c.source,
            articles.c.publication_date,
            articles.c.summary,
            articles.c.category,
            articles.c.sentiment,
            articles.c.driver_type,
            articles.c.time_to_impact,
            articles.c.future_signal,
            articles.c.bias,
            articles.c.factual_reporting,
            articles.c.mbfc_credibility_rating,
            articles.c.bias_country,
            articles.c.press_freedom,
            articles.c.media_type,
            articles.c.popularity
        ).select_from(
            keyword_alerts.join(
                articles,
                keyword_alerts.c.article_uri == articles.c.uri
            ).where(
                keyword_alerts.c.is_read == 0
            )
        ).order_by(
            keyword_alerts.c.detected_at.desc()
        )
        return self.connection.execute(statement).fetchall() 

    def delete_keyword_alerts_by_article_url(self, url):
        statement = delete(
            keyword_alerts
        ).where(
            keyword_alerts.c.article_uri == url
        )
        self.connection.execute(statement)
        self.connection.commit() 

    def delete_keyword_alerts_by_article_url_from_new_table(self, url):
        statement = delete(
            keyword_article_matches
        ).where(
            keyword_article_matches.c.article_uri == url
        )
        self.connection.execute(statement)
        self.connection.commit() 

    def get_total_articles_and_sample_categories_for_topic(self, topic: str):
        statement = select(
            func.count()
        ).select_from(
            articles
        ).where(
            func.lower(articles.c.topic) == func.lower(topic)
        )
        total_topic_articles = self.connection.execute(statement).fetchone().scalar()

        statement = select(
            func.count()
        ).select_from(
            articles
        ).where(
            func.lower(articles.c.topic) == func.lower(topic),
            articles.c.category != None,
            articles.c.category != ''
        )
        articles_with_categories = self.connection.execute(statement).fetchone().scalar()

        statement = select(
            articles.c.category
        ).where(
            func.lower(articles.c.topic) == func.lower(topic),
            articles.c.category != None,
            articles.c.category != ''
        ).distinct()
        sample_categories = [row[0] for row in self.connection.execute(statement).fetchall()]

        return total_topic_articles, articles_with_categories, sample_categories 

    def get_topic(self, topic):
        statement = select(
            articles.c.topic
        ).where(
            func.lower(articles.c.topic) == func.lower(topic)
        ).distinct()
        return self.connection.execute(statement).fetchone() 

    def get_articles_count_from_topic_and_categories(self, placeholders, params):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                f"SELECT COUNT(*) FROM articles WHERE LOWER(topic) = LOWER(?) AND category IN ({placeholders})", params)

            return cursor.fetchone()[0]

    def get_article_count_for_topic(self, topic):
        statement = select(
            func.count()
        ).select_from(
            articles
        ).where(
            func.lower(articles.c.topic) == func.lower(topic)
        )
        return self.connection.execute(statement).fetchone().scalar() 

    def get_recent_articles_for_topic_and_category(self, params):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT title,
                                  news_source,
                                  uri,
                                  sentiment,
                                  future_signal,
                                  time_to_impact,
                                  publication_date
                           FROM articles
                           WHERE LOWER(topic) = LOWER(?)
                             AND LOWER(category) = LOWER(?)
                             AND date (publication_date) >= date ('now'
                               , '-' || ? || ' days')
                           ORDER BY publication_date DESC
                               LIMIT 5
                           """, params)

            return cursor.fetchall()

    def get_categories_for_topic(self, topic):
        statement = select(
            articles.c.category
        ).where(
            func.lower(articles.c.topic) == func.lower(topic),
            articles.c.category != None,
            articles.c.category != ''
        ).distinct()

        return [row[0] for row in self.connection.execute(statement).fetchall()] 

    def get_podcasts_columns(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("PRAGMA table_info(podcasts)")

            table_info = cursor.fetchall()

            return [col[1] for col in table_info]

    def generate_latest_podcasts(self, topic, column_names, has_transcript, has_topic, has_audio_url):
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
        statement = select(
            articles
        ).where(
            articles.c.topic == topic,
            articles.c.publication_date.between(start_date, end_date)
        ).order_by(
            articles.c.publication_date.desc()
        )
        if limit:
            statement = statement.limit(limit)

        articles_list = self.connection.execute(statement).fetchall()
        column_names = [col.name for col in articles.columns]

        return column_names, articles_list 

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
                           params)

            return cursor.lastrowid

    def store_evaluation_results(self, params):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           INSERT INTO model_bias_arena_results
                           (run_id, article_uri, model_name, response_text, bias_score,
                            confidence_score, response_time_ms, error_message)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                           """, params)
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
                           """, params)
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
                           SELECT topic,
                                  COUNT(DISTINCT uri)   as article_count,
                                  MAX(publication_date) as last_article_date
                           FROM articles
                           WHERE topic IS NOT NULL
                             AND topic != ''
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
                           SELECT kg.id,
                                  kg.name,
                                  kg.topic,
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
                           SELECT name
                           FROM sqlite_master
                           WHERE type = 'table'
                             AND name = 'keyword_article_matches'
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
                    self.logger.warning("Invalid timeframe value provided: %s", timeframe)

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

    def delete_keyword_group(self, group_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM keyword_groups WHERE id = ?", (group_id,))
            conn.commit()

    def delete_group_keywords(self, group_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                "DELETE FROM monitored_keywords WHERE group_id = ?",
                (group_id,)
            )

            conn.commit()

    def create_group(self, group_name, group_topic):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                "INSERT INTO keyword_groups (name, topic) VALUES (?, ?)",
                (group_name, group_topic)
            )

            conn.commit()

            return cursor.lastrowid

    def add_keywords_to_group(self, group_id, keyword):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                "INSERT INTO monitored_keywords (group_id, keyword) "
                "VALUES (?, ?)",
                (group_id, keyword)
            )

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
            # TODO: Move to migrations.
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
                           WHERE EXISTS (SELECT 1
                                         FROM keyword_groups kg
                                         WHERE kg.id = mk.group_id)
                           """)

            return cursor.fetchone()[0]

    def get_settings_and_status_together(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT s.check_interval,
                                  s.interval_unit,
                                  s.search_fields,
                                  s.language,
                                  s.sort_by,
                                  s.page_size,
                                  s.daily_request_limit,
                                  s.is_enabled,
                                  s.provider,
                                  COALESCE(s.auto_ingest_enabled, FALSE)       as auto_ingest_enabled,
                                  COALESCE(s.min_relevance_threshold, 0.0)     as min_relevance_threshold,
                                  COALESCE(s.quality_control_enabled, TRUE)    as quality_control_enabled,
                                  COALESCE(s.auto_save_approved_only, FALSE)   as auto_save_approved_only,
                                  COALESCE(s.default_llm_model, 'gpt-4o-mini') as default_llm_model,
                                  COALESCE(s.llm_temperature, 0.1)             as llm_temperature,
                                  COALESCE(s.llm_max_tokens, 1000)             as llm_max_tokens,
                                  COALESCE(kms.requests_today, 0)              as requests_today,
                                  kms.last_error
                           FROM keyword_monitor_settings s
                                    LEFT JOIN (SELECT id, requests_today, last_error
                                               FROM keyword_monitor_status
                                               WHERE id = 1
                                                 AND last_reset_date = date ('now') ) kms
                           ON kms.id = 1
                           WHERE s.id = 1
                           """)

            return cursor.fetchone()

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
                           WITH RECURSIVE dates(date) AS (SELECT date ('now', '-6 days')
                           UNION ALL
                           SELECT date (date, '+1 day')
                           FROM dates
                           WHERE date
                               < date ('now')
                               )
                               , daily_counts AS (
                           SELECT
                               kg.id as group_id, kg.name as group_name, date (ka.detected_at) as detection_date, COUNT (*) as article_count
                           FROM keyword_alerts ka
                               JOIN monitored_keywords mk
                           ON ka.keyword_id = mk.id
                               JOIN keyword_groups kg ON mk.group_id = kg.id
                           WHERE ka.detected_at >= date ('now', '-6 days')
                           GROUP BY kg.id, kg.name, date (ka.detected_at)
                               )
                           SELECT kg.id,
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

    def topic_exists(self, topic):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                "SELECT 1 FROM articles WHERE topic = ? LIMIT 1",
                (topic,)
            )

            return cursor.fetchone() is not None

    def get_keyword_group_id_by_name_and_topic(self, group_name, topic_name):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                "SELECT id FROM keyword_groups WHERE name = ? AND topic = ?",
                (group_name, topic_name)
            )

            return cursor.fetchone()

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

    def get_alerts_by_group_id_from_new_table_structure(self, status, show_read, group_id, page_size, offset):
        # Create base statement.
        statement = select(
            keyword_article_matches.c.id,
            keyword_article_matches.c.article_uri,
            keyword_article_matches.c.keyword_ids,
            literal(None).label("matched_keyword"),
            keyword_article_matches.c.is_read,
            keyword_article_matches.c.detected_at,
            articles.c.title,
            articles.c.summary,
            articles.c.uri,
            articles.c.news_source,
            articles.c.publication_date,
            articles.c.topic_alignment_score,
            articles.c.keyword_relevance_score,
            articles.c.confidence_score,
            articles.c.overall_match_explanation,
            articles.c.extracted_article_topics,
            articles.c.extracted_article_keywords,
            articles.c.category,
            articles.c.sentiment,
            articles.c.driver_type,
            articles.c.time_to_impact,
            articles.c.future_signal,
            articles.c.bias,
            articles.c.factual_reporting,
            articles.c.mbfc_credibility_rating,
            articles.c.bias_country,
            articles.c.press_freedom,
            articles.c.media_type,
            articles.c.popularity,
            articles.c.auto_ingested,
            articles.c.ingest_status,
            articles.c.quality_score,
            articles.c.quality_issues
        ).select_from(
            keyword_article_matches.join(
                articles,
                # TODO: This where statement will be SLOW due to TEXT where clauses!!
                keyword_article_matches.c.article_uri == articles.c.uri
            )
        ).where(
            keyword_article_matches.c.group_id == group_id
        )

        # Add read filter condition
        if not show_read:
            statement = statement.where(
                keyword_article_matches.c.is_read == 0
            )

        # Add status filter condition
        status_condition = ""
        if status == "new":
            statement = statement.where(
                or_(
                    articles.c.category.is_(None),
                    articles.c.category == ''
                )
            )
        elif status == "added":
            statement = statement.where(
                or_(
                    articles.c.category.is_not(None),
                    articles.c.category != ''
                )
            )

        # Add pagination and sorting.
        statement = statement.order_by(
            desc(keyword_article_matches.c.detected_at)
        ).limit(page_size).offset(offset)

        return self.connection.execute(statement).fetchall()

    def get_alerts_by_group_id_from_old_table_structure(self, status, show_read, group_id, page_size, offset):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            read_condition = "" if show_read else "AND ka.is_read = 0"

            # Add status filter condition
            status_condition = ""
            if status == "new":
                status_condition = "AND (a.category IS NULL OR a.category = '')"
            elif status == "added":
                status_condition = "AND (a.category IS NOT NULL AND a.category != '')"

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
                WHERE mk.group_id = ? {read_condition} {status_condition}
                ORDER BY ka.detected_at DESC
                LIMIT ? OFFSET ?
            """, (group_id, page_size, offset))

            return cursor.fetchall()

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

    def update_media_bias(self, source):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE mediabias SET enabled = 1 WHERE source = ?",
                source
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
                           SELECT article_uri
                           FROM news_search_results
                           WHERE topic = ?
                           """, (topic_name,))

            return cursor.fetchall()

    def get_article_urls_from_paper_search_results_by_topic(self, topic_name):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT article_uri
                           FROM paper_search_results
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
                           SELECT check_interval,
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

            cursor.execute("SELECT raw_markdown FROM raw_articles WHERE uri = ?", (url,))

            return cursor.fetchone()

    def get_podcasts_for_newsletter_inclusion(self, column_names):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Build a query that works with the available columns
            # Base columns we need
            select_columns = ["id", "title", "created_at"]
            if "audio_url" in column_names:
                select_columns.append("audio_url")
            if "topic" in column_names:
                select_columns.append("topic")

            # Execute query to get recent podcasts
            cursor.execute(
                f"""
                SELECT {', '.join(select_columns)}
                FROM podcasts
                ORDER BY created_at DESC
                LIMIT 20
                """
            )

            podcasts = cursor.fetchall()

            # Format results
            result = []
            for podcast in podcasts:
                podcast_dict = {}
                for i, col in enumerate(select_columns):
                    podcast_dict[col] = podcast[i]
                result.append(podcast_dict)

            return result

    def generate_tts_podcast(self, params):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO podcasts (id, title, status, created_at, transcript, metadata)
                VALUES (?, ?, 'processing', CURRENT_TIMESTAMP, ?, ?)
                """,
                params,
            )
            conn.commit()

    def mark_podcast_generation_as_complete(self, params):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE podcasts
                SET status       = 'completed',
                    audio_url    = ?,
                    completed_at = CURRENT_TIMESTAMP,
                    error        = NULL,
                    metadata     = ?
                WHERE id = ?
                """,
                params,
            )
            conn.commit()

    def log_error_generating_podcast(self, params):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE podcasts
                SET status       = 'error',
                    error        = ?,
                    completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                params,
            )
            conn.commit()

    def test_data_select(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT 1")

    def get_keyword_monitor_is_enabled_and_daily_request_limit(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT is_enabled, daily_request_limit
                           FROM keyword_monitor_settings
                           WHERE id = 1
                           """)

            return cursor.fetchone()

    def get_topic_statistics(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT topic,
                                  COUNT(*) as article_count,
                                  strftime('%Y-%m-%dT%H:%M:%S.000Z',
                                           MAX(COALESCE(submission_date, publication_date))
                                  )        as last_article_date
                           FROM articles
                           WHERE topic IS NOT NULL
                             AND topic != ''
                           GROUP BY topic
                           ORDER BY CASE
                               WHEN MAX (COALESCE (submission_date, publication_date)) IS NULL THEN 1
                               ELSE 0
                           END
                           ,
                last_article_date DESC
                           """)

            return cursor.fetchall()

    def get_last_check_time_using_timezone_format(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT strftime('%Y-%m-%dT%H:%M:%S.000Z', last_check_time)
                           FROM keyword_monitor_status
                           WHERE id = 1
                           """)
            result = cursor.fetchone()

            return result[0] if result else None

    def get_podcast_transcript(self, podcast_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                           SELECT title, transcript, metadata
                           FROM podcasts
                           WHERE id = ?
                           """, (podcast_id,))

            return cursor.fetchone()

    def get_all_podcasts(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT id,
                                  title,
                                  status,
                                  audio_url,
                                  created_at,
                                  completed_at,
                                  error,
                                  transcript,
                                  metadata
                           FROM podcasts
                           ORDER BY created_at DESC
                           """)

            return cursor.fetchall()

    def get_podcast_generation_status(self, podcast_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT id,
                                  title,
                                  status,
                                  audio_url,
                                  created_at,
                                  completed_at,
                                  error,
                                  transcript,
                                  metadata
                           FROM podcasts
                           WHERE id = ?
                           """, (podcast_id,))

            return cursor.fetchone()

    def get_podcast_audio_file(self, podcast_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT audio_url
                           FROM podcasts
                           WHERE id = ?
                           """, (podcast_id,))

            return cursor.fetchone()

    def delete_podcast(self, podcast_id):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Delete podcast record
            cursor.execute("""
                           DELETE
                           FROM podcasts
                           WHERE id = ?
                           """, (podcast_id,))
            conn.commit()

    def search_for_articles_based_on_query_date_range_and_topic(self, query, topic, start_date, end_date, limit):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Build search query
            search_conditions = []
            params = []

            if query:
                # Add fuzzy search on title and summary
                search_conditions.append("(title LIKE ? OR summary LIKE ?)")
                params.extend([f"%{query}%", f"%{query}%"])

            if topic:
                search_conditions.append("topic = ?")
                params.append(topic)

            if start_date:
                search_conditions.append("publication_date >= ?")
                params.append(start_date)

            if end_date:
                search_conditions.append("publication_date <= ?")
                params.append(end_date)

            # Construct the WHERE clause
            where_clause = " AND ".join(search_conditions) if search_conditions else "1=1"

            query = f"""
                SELECT * FROM articles 
                WHERE {where_clause}
                ORDER BY publication_date DESC
                LIMIT {limit}
            """

            cursor.execute(query, params)
            articles = cursor.fetchall()

            # Convert to list of dictionaries with column names
            column_names = [description[0] for description in cursor.description]
            result = []

            for row in articles:
                article_dict = dict(zip(column_names, row))
                result.append(article_dict)

            return result

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

    def enable_or_disable_auto_ingest(self, enabled):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                           UPDATE keyword_monitor_settings
                           SET auto_ingest_enabled = ?
                           WHERE id = 1
                           """, (enabled,))

            conn.commit()

    def get_auto_ingest_settings(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                           SELECT auto_ingest_enabled,
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
                           VALUES (1, ?, datetime('now'), ?) ON CONFLICT(id) DO
                           UPDATE SET
                               requests_today = excluded.requests_today,
                               last_check_time = excluded.last_check_time,
                               last_reset_date = excluded.last_reset_date
                           """, params)
            conn.commit()

    def get_keyword_monitor_status_daily_request_limit(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT daily_request_limit FROM keyword_monitor_settings WHERE id = 1")

            return cursor.fetchone()

    #### AUTOMATED INGEST SERVICE ####

    #### MEDIA BIAS ####

    def check_if_media_bias_has_updated_at_column(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("PRAGMA table_info(mediabias)")

            return [column[1] for column in cursor.fetchall()]

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

            return cursor.rowcount

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
