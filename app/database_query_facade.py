from datetime import datetime, timedelta
from typing import Optional, List, Dict
from re import U
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
                        not_,
                        literal,
                        func,
                        distinct,
                        exists,
                        literal_column,
                        inspect,
                        case,
                        text,
                        Text)

from app.database_models import (t_keyword_monitor_settings as keyword_monitor_settings,
                                 t_keyword_monitor_status as keyword_monitor_status,
                                 t_keyword_article_matches as keyword_article_matches,
                                 t_articles as articles,
                                 t_monitored_keywords as monitored_keywords,
                                 t_keyword_groups as keyword_groups,
                                 t_analysis_versions as analysis_versions,
                                 t_analysis_versions_v2 as analysis_versions_v2,
                                 t_organizational_profiles as organizational_profiles,
                                 t_keyword_alerts as keyword_alerts,
                                 t_oauth_allowlist as oauth_allowlist,
                                 t_oauth_users as oauth_users,
                                 t_podcasts as podcasts,
                                 t_model_bias_arena_runs as model_bias_arena_runs,
                                 t_model_bias_arena_results as model_bias_arena_results,
                                 t_model_bias_arena_articles as model_bias_arena_articles,
                                 t_mediabias as mediabias,
                                 t_mediabias_settings as mediabias_settings,
                                 t_feed_items as feed_items,
                                 t_feed_keyword_groups as feed_keyword_groups,
                                 t_feed_group_sources as feed_group_sources,
                                 t_user_feed_subscriptions as user_feed_subscriptions,
                                 t_auspex_chats as auspex_chats,
                                 t_auspex_messages as auspex_messages,
                                 t_auspex_prompts as auspex_prompts,
                                 t_dashboard_cache as dashboard_cache,
                                 # t_keyword_monitor_checks as keyword_monitor_checks,  # Table doesn't exist
                                 t_raw_articles as raw_articles)
                                 # t_paper_search_results as paper_search_results,  # Table doesn't exist
                                 # t_news_search_results as news_search_results,  # Table doesn't exist
                             # t_keyword_alert_articles as keyword_alert_articles)  # Table doesn't exist

# TODO: These tables need to be added to database_models.py
# For now, set to None so imports work but methods using them will fail with clear error
paper_search_results = None
news_search_results = None
keyword_alert_articles = None
keyword_monitor_checks = None


class DatabaseQueryFacade:
    def __init__(self, db, logger):
        self.db = db
        self.logger = logger

    @property
    def connection(self):
        """Get a fresh connection from the database pool.

        CRITICAL: This is now a property that always returns a fresh connection
        instead of caching one. This prevents "This Connection is closed" errors
        when the pool recycles connections or they become stale.
        """
        return self.db._temp_get_connection()

    def _get_connection(self):
        """Get a fresh connection from the database pool.

        CRITICAL: We don't cache connections at the facade level anymore.
        This prevents "This Connection is closed" errors when the pool
        recycles connections or they become stale.
        """
        return self.db._temp_get_connection()

    def _execute_with_rollback(self, statement, params=None, operation_name="query"):
        """
        Execute a statement with automatic rollback on error and commit on success.
        This ensures PostgreSQL transactions don't stay in idle in transaction state.

        Args:
            statement: SQLAlchemy statement or text() object
            params: Optional parameters dict for text() queries
            operation_name: Description of the operation for logging
        """
        # CRITICAL FIX: Get fresh connection for each operation to avoid
        # "This Connection is closed" errors from stale cached connections
        connection = self._get_connection()

        try:
            if params is not None:
                result = connection.execute(statement, params)
            else:
                result = connection.execute(statement)
            # CRITICAL: Commit after successful operation to close transaction
            # This prevents "idle in transaction" state in PostgreSQL
            connection.commit()
            return result
        except Exception as e:
            self.logger.error(f"Error executing {operation_name}: {e}")
            try:
                connection.rollback()
            except Exception as rollback_error:
                self.logger.error(f"Error during rollback: {rollback_error}")
            raise

    #### KEYWORD MONITOR QUERIES ####
    def get_keyword_monitor_settings_by_id(self, id):
        return self._execute_with_rollback(
            select(
                keyword_monitor_settings
            ).where(
                keyword_monitor_settings.c.id == id
            )
        ).mappings().fetchone()

    def get_keyword_monitor_status_by_id(self, id):
        return self._execute_with_rollback(
            select(
                keyword_monitor_status
            ).where(
                keyword_monitor_status.c.id == id
            )
        ).mappings().fetchone()

    def update_keyword_monitor_status_by_id(self, id, params):
        self._execute_with_rollback(
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
        """Get single provider (legacy method - use get_keyword_monitoring_providers for multi-collector)"""
        row = self.get_keyword_monitor_settings_by_id(1)
        # TODO: Make this default configurable?
        provider = row['provider'] if row else 'newsapi'
        return provider

    def get_keyword_monitoring_providers(self):
        """Get selected providers as JSON array string"""
        row = self.get_keyword_monitor_settings_by_id(1)
        if row and row.get('providers'):
            return row['providers']
        # Fallback to single provider for backward compatibility
        elif row and row.get('provider'):
            import json
            return json.dumps([row['provider']])
        # Ultimate fallback
        return '["newsapi"]'

    def update_keyword_monitoring_providers(self, providers_json: str):
        """Update providers JSON array"""
        from sqlalchemy import update
        from app.database_models import t_keyword_monitor_settings

        stmt = update(t_keyword_monitor_settings).where(
            t_keyword_monitor_settings.c.id == 1
        ).values(providers=providers_json)

        self._execute_with_rollback(stmt)

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
        self._execute_with_rollback(insert(keyword_monitor_status).values(**params))
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
        return self._execute_with_rollback(statement).mappings().fetchall()

    def get_monitored_keywords_for_topic(self, params):
        statement = select(
            monitored_keywords.c.keyword
            ).select_from(
                monitored_keywords
                .join(keyword_groups, monitored_keywords.c.group_id == keyword_groups.c.id)
            ).where(
                keyword_groups.c.topic == params[0]
            )
        rows = self._execute_with_rollback(statement).mappings().fetchall()
        topic_keywords = [row['keyword'] for row in rows]
        return topic_keywords

    def article_exists(self, params):
        article_exists =  self._execute_with_rollback(
            select(articles.c.uri).where(articles.c.uri == params[0])
        ).fetchone()
        return article_exists

    def create_article(self, article_exists, article_url, article, topic, keyword_id):
        # Don't call begin() - transaction is auto-started by PostgreSQL on first execute
        try:
            inserted_new_article = False
            if not article_exists:
                # Save new article
                self._execute_with_rollback(insert(articles).values(
                    uri=article_url,
                    title=article['title'],
                    news_source=article['source'],
                    publication_date=article['published_date'],
                    summary=article.get('summary', ''),
                    topic=topic,
                    analyzed=False
                ))

                inserted_new_article = True
                self.logger.info(f"Inserted new article: {article_url}")

            # Get the group_id for this keyword
            group_id = self._execute_with_rollback(
                select(monitored_keywords.c.group_id).where(monitored_keywords.c.id == keyword_id)
            ).scalar()

            # Check if we already have a match for this article in this group
            existing_match = self._execute_with_rollback(select(keyword_article_matches.c.id, keyword_article_matches.c.keyword_ids).where(
                keyword_article_matches.c.article_uri == article_url,
                keyword_article_matches.c.group_id == group_id)).fetchone()

            match_updated = False

            if existing_match:
                # Update the existing match with the new keyword
                match_id, keyword_ids = existing_match
                keyword_id_list = keyword_ids.split(',')
                if str(keyword_id) not in keyword_id_list:
                    keyword_id_list.append(str(keyword_id))
                    updated_keyword_ids = ','.join(keyword_id_list)
                    result = self._execute_with_rollback(update(keyword_article_matches).where(
                        keyword_article_matches.c.id == match_id
                        ).values(keyword_ids = updated_keyword_ids))

                    match_updated = True
            else:
                # Create a new match
                self._execute_with_rollback(insert(keyword_article_matches).values(
                    article_uri=article_url,
                    keyword_ids=str(keyword_id),
                    group_id=group_id))

                match_updated = True

            self.connection.commit()

            # For backward compatibility, return the same structure but alert_inserted is always False now
            return inserted_new_article, False, match_updated

        except Exception as e:
            self.connection.rollback()
            raise e

    def update_monitored_keyword_last_checked(self, params):
        statement = update(monitored_keywords).where(monitored_keywords.c.id == params[1]).values(last_checked = params[0])
        self._execute_with_rollback(statement)
        self.connection.commit() 

    def update_keyword_monitor_counter(self, params):
        statement = update(keyword_monitor_status).where(keyword_monitor_status.c.id == 1).values(requests_today = params[0])
        self._execute_with_rollback(statement)
        self.connection.commit() 


    def create_keyword_monitor_log_entry(self, params):
        existing = self._execute_with_rollback(select(keyword_monitor_status).where(keyword_monitor_status.c.id == 1)).fetchone()
        if existing:
            self._execute_with_rollback(update(keyword_monitor_status).where(keyword_monitor_status.c.id == 1).values(last_check_time = params[0], last_error = params[1], requests_today = params[2]))
        else:
            self._execute_with_rollback(insert(keyword_monitor_status).values(id = 1, last_check_time = params[0], last_error = params[1], requests_today = params[2]))

        self.connection.commit()

    def get_keyword_monitor_polling_enabled(self):
        statement = select(
            keyword_monitor_settings.c.is_enabled
        ).where(
            keyword_monitor_settings.c.id == 1
        )
        row = self._execute_with_rollback(statement).fetchone()
        is_enabled = row[0] if row and row[0] is not None else True
        return is_enabled

    def get_keyword_monitor_interval(self):
        statement = select(
            keyword_monitor_settings.c.check_interval,
            keyword_monitor_settings.c.interval_unit
        ).where(
            keyword_monitor_settings.c.id == 1
        )
        return self._execute_with_rollback(statement).fetchone()

    #### RESEARCH QUERIES ####
    def get_article_by_url(self, url):
        statement = select(articles).where(
            articles.c.uri == url
        )
        result = self._execute_with_rollback(statement).mappings()
        return result.fetchone()

    def create_article_with_extracted_content(self, params):
        statement = insert(
            articles
        ).values(
            uri=params[0],
            title=params[1],
            news_source=params[2],
            submission_date=func.current_timestamp(),
            topic=params[3],
            analyzed= params[4],
            summary=params[5]
        )
        self._execute_with_rollback(statement)
        self.connection.commit()

    async def move_alert_to_articles(self, url: str) -> None:
        statement = select(
            keyword_alert_articles
        ).where(
            keyword_alert_articles.c.url == url,
            keyword_alert_articles.c.moved_to_articles == False
        )
        alert = self._execute_with_rollback(statement).fetchone()
        if alert:
            statement = insert(
                articles
            ).values(
                uri=alert['url'],
                title=alert['title'],
                summary=alert['summary'],
                source=alert['source'],
                topic=alert['topic'],
                analyzed=False
            )
            self._execute_with_rollback(statement)
            
            statement = update(
                keyword_alert_articles
            ).where(
                keyword_alert_articles.c.url == url
            ).values(
                moved_to_articles = True
            )
            self._execute_with_rollback(statement)
            self.connection.commit()

    #### REINDEX CHROMA DB QUERIES ####
    def get_iter_articles(self, limit: int | None = None):

        statement = select(articles, raw_articles.c.raw_markdown.label('raw')).select_from(
            articles.outerjoin(raw_articles, articles.c.uri == raw_articles.c.uri)
        ).order_by(articles.c.uri)

        if limit:
            statement = statement.limit(limit)

        return self._execute_with_rollback(statement).mappings().fetchall()

    def save_analysis_version(self, params):
        statement = insert(
            analysis_versions
        ).values(
            topic=params[0],
            version_data=params[1],
            model_used=params[2],
            analysis_depth=params[3]
        )
        self._execute_with_rollback(statement)
        self.connection.commit()

    def get_latest_analysis_version(self, topic):
        statement = select(
            analysis_versions.c.version_data
        ).where(
            analysis_versions.c.topic == topic
        ).order_by(
            analysis_versions.c.created_at.desc()
        ).limit(1)
        return self._execute_with_rollback(statement).fetchone()

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
                # NOTE: publication_date is TEXT, use strftime() to match DB format
                articles.c.publication_date >= start_date.strftime('%Y-%m-%d'),
                articles.c.publication_date <= end_date.strftime('%Y-%m-%d %H:%M:%S'),
                articles.c.summary != '',
                articles.c.summary != None,
            )
        )
        if consistency_mode in [ConsistencyMode.DETERMINISTIC, ConsistencyMode.LOW_VARIANCE]:
            statement = statement.order_by(articles.c.publication_date.desc(), articles.c.title.asc())
        else:
            statement = statement.order_by(articles.c.publication_date.desc())

        statement = statement.limit(optimal_sample_size * fetch_multiplier)

        return self._execute_with_rollback(statement).mappings().fetchall() 

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
        return self._execute_with_rollback(statement).mappings().fetchone() 

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
        return self._execute_with_rollback(statement).mappings().fetchall() 

    def create_organisational_profile(self, params):
        statement = insert(
            organizational_profiles
        ).values(
            name=params[0],
            description=params[1],
            industry=params[2],
            organization_type=params[3],
            region=params[4],
            key_concerns=params[5],
            strategic_priorities=params[6],
            risk_tolerance=params[7],
            innovation_appetite=params[8],
            decision_making_style=params[9],
            stakeholder_focus=params[10],
            competitive_landscape=params[11],
            regulatory_environment=params[12],
            custom_context=params[13]
        )
        
        return self._execute_with_rollback(statement)

    def delete_organisational_profile(self, profile_id):
        statement = delete(organizational_profiles).where(organizational_profiles.c.id == profile_id)
        self._execute_with_rollback(statement)
        self.connection.commit() 

    def get_organisational_profile_by_name(self, name):
        statement = select(
            organizational_profiles.c.id
        ).where(
            organizational_profiles.c.name == name
        )
        return self._execute_with_rollback(statement).mappings().fetchone()

    def get_organisational_profile_by_id(self, profile_id):
        statement = select(
            organizational_profiles.c.id
        ).where(
            organizational_profiles.c.id == profile_id
        )
        return self._execute_with_rollback(statement).mappings().fetchone()

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
        return self._execute_with_rollback(statement).mappings().fetchone()

    def check_organisational_profile_name_conflict(self, name, profile_id):
        statement = select(
            organizational_profiles.c.id
        ).where(
            and_(
                organizational_profiles.c.name == name,
                organizational_profiles.c.id != profile_id
            )
        )
        return self._execute_with_rollback(statement).fetchone()

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
        self._execute_with_rollback(statement)
        self.connection.commit() 


    def check_if_profile_exists_and_is_not_default(self, profile_id):
        statement = select(
            organizational_profiles.c.is_default
        ).where(
            organizational_profiles.c.id == profile_id
        )
        return self._execute_with_rollback(statement).fetchone()

    #### AUTOMATED INGEST SERVICE ####
    def get_configured_llm_model(self):
        statement = select(
            keyword_monitor_settings.c.default_llm_model,
            keyword_monitor_settings.c.llm_temperature,
            keyword_monitor_settings.c.llm_max_tokens
        ).where(
            keyword_monitor_settings.c.id == 1
        )
        settings = self._execute_with_rollback(statement).mappings().fetchone()
        if settings:
            return settings['default_llm_model'] or "gpt-4o-mini"

    def get_llm_parameters(self):
        statement = select(
            keyword_monitor_settings.c.llm_temperature,
            keyword_monitor_settings.c.llm_max_tokens
        ).where(
            keyword_monitor_settings.c.id == 1
        )
        row = self._execute_with_rollback(statement).mappings().fetchone()
        if row:
            return (row['llm_temperature'], row['llm_max_tokens'])
        return None

    def save_approved_article(self, params):
        statement = update(
            articles
        ).where(
            articles.c.uri == params[27]
        ).values(
            title = func.coalesce(params[0], articles.c.title),
            summary = func.coalesce(params[1], articles.c.summary),
            auto_ingested = True,
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
            analyzed = True,
            confidence_score = params[24],
            overall_match_explanation = params[25],
            publication_date = params[26]
        )
        try:
            self._execute_with_rollback(statement)
            self.connection.commit()
        except Exception as e:
            # Rollback on error to avoid leaving transaction in aborted state
            self.connection.rollback()
            self.logger.error(f"Error in save_approved_article, rolled back transaction: {e}")
            raise 

    def get_min_relevance_threshold(self):
        statement = select(
            keyword_monitor_settings.c.min_relevance_threshold
        ).where(
            keyword_monitor_settings.c.id == 1
        )
        settings = self._execute_with_rollback(statement).mappings().fetchone()
        if settings and settings['min_relevance_threshold'] is not None:
            return float(settings['min_relevance_threshold'])

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
        return self._execute_with_rollback(statement).fetchone()

    def update_ingested_article(self, params):
        statement = update(
            articles
        ).where(
            articles.c.uri == params[3]
        ).values(
            auto_ingested = True,
            ingest_status = params[0],
            quality_score = params[1],
            quality_issues = params[2]
        )
        self._execute_with_rollback(statement)
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
        return self._execute_with_rollback(statement).mappings().fetchall()

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
        return self._execute_with_rollback(statement).mappings().fetchall()

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
        return self._execute_with_rollback(statement).mappings().fetchall()

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
        return self._execute_with_rollback(statement).mappings().fetchall()

    def get_topic_keywords(self, topic_id):
        statement = select(
            monitored_keywords.c.keyword
        ).select_from(
            monitored_keywords
            .join(keyword_groups, monitored_keywords.c.group_id == keyword_groups.c.id)
        ).where(
            keyword_groups.c.topic == topic_id
        )
        rows = self._execute_with_rollback(statement).mappings().fetchall()
        topic_keywords = [row['keyword'] for row in rows]
        return topic_keywords

    #### EXECUTIVE SUMMARY ROUTES ####
    def get_articles_for_market_signal_analysis(self, timeframe_days, topic_name):
        #calculate the date 'now' - timeframe_days days
        start_date = datetime.utcnow() - timedelta(days=timeframe_days)
        # Convert to string for text column comparison
        start_date_str = start_date.strftime('%Y-%m-%d %H:%M:%S')

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
                articles.c.publication_date >= start_date_str,
                articles.c.analyzed == True  # Use True for boolean column
            )
        ).order_by(
            desc(articles.c.publication_date)
        ).limit(50)
        return self._execute_with_rollback(statement).mappings().fetchall()

    def get_recent_articles_for_market_signal_analysis(self, timeframe_days, topic_name, optimal_sample_size):
        start_date = datetime.utcnow() - timedelta(days=timeframe_days)
        # Convert to string for text column comparison
        start_date_str = start_date.strftime('%Y-%m-%d %H:%M:%S')

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
                articles.c.publication_date >= start_date_str,
                articles.c.analyzed == True,  # Use True for boolean column
                articles.c.summary != None,
                articles.c.summary != ''
            )
        ).order_by(
            desc(articles.c.publication_date)
        ).limit(optimal_sample_size)
        return self._execute_with_rollback(statement).mappings().fetchall()

    def get_articles_by_topic(self, topic: str, limit: int = 100):
        """Get recent articles for a topic.

        Args:
            topic: Topic name
            limit: Maximum number of articles to return

        Returns:
            List of article dictionaries
        """
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
                articles.c.topic == topic,
                articles.c.analyzed == True  # Only analyzed articles
            )
        ).order_by(
            desc(articles.c.publication_date)
        ).limit(limit)

        return self._execute_with_rollback(statement).mappings().fetchall()

    def get_topic_filtered_future_signals_with_counts_for_market_signal_analysis(self, topic_name):
        # We need actual counts, not just the config list
        # Use ALL articles (including historical) as inputs for foresight analysis
        statement = select(
            articles.c.future_signal,
            func.count().label('count')
        ).where(
            and_(
                articles.c.topic == topic_name,
                articles.c.future_signal != None,
                articles.c.future_signal != '',
                articles.c.analyzed == True  # Use True for boolean column
            )
        ).group_by(
            articles.c.future_signal
        ).order_by(
            desc(func.count())
        )
        return self._execute_with_rollback(statement).mappings().fetchall()

    #### TOPIC MAP ROUTES ####
    def get_unique_topics(self):
        statement = select(
            articles.c.topic
        ).where(
            and_(
                articles.c.topic != None,
                articles.c.topic != '',
                articles.c.analyzed == True)
        ).distinct().order_by(
            articles.c.topic.asc()
        )
        rows = self._execute_with_rollback(statement).mappings().fetchall()

        return [row[0] for row in rows]

    def get_all_topics(self):
        """Get all topics as list of dictionaries.

        Returns:
            List of topic dictionaries with 'name' field
        """
        topic_names = self.get_unique_topics()
        return [{"name": name} for name in topic_names] 


    def get_unique_categories(self):
        statement = select(
            articles.c.category
        ).where(
            and_(
                articles.c.category != None,
                articles.c.category != '',
                articles.c.analyzed == True)
        ).distinct().order_by(
            articles.c.category.asc()
        )
        rows = self._execute_with_rollback(statement).mappings().fetchall()
        return [row[0] for row in rows] 


    #### OAUTH USERS ####
    def count_oauth_allowlist_active_users(self):
        statement = select(func.count()).where(oauth_allowlist.c.is_active == 1)
        return self._execute_with_rollback(statement).fetchone()[0] 

    def get_oauth_allowlist_user_by_email_and_provider(self, email, provider):
        statement = select(
            oauth_users
        ).where(
            and_(
                oauth_users.c.email == email,
                oauth_users.c.provider == provider
            )
        )
        return self._execute_with_rollback(statement).fetchone() 

    def get_oauth_allowlist_user_by_id(self, user_id):
        statement = select(
            oauth_users
        ).where(
            oauth_users.c.id == user_id
        )
        return self._execute_with_rollback(statement).fetchone() 


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
        return self._execute_with_rollback(statement).mappings().fetchall() 

    def is_oauth_user_allowed(self, email):
        statement = select(func.count()).where(oauth_allowlist.c.email == email, oauth_allowlist.c.is_active == 1)
        count = self._execute_with_rollback(statement).fetchone()[0]
        return count > 0 

    def add_oauth_user_to_allowlist(self, email, added_by):
        is_email_exists = self.is_oauth_user_allowed(email)
        if is_email_exists:
            update_statement = update(oauth_allowlist).where(oauth_allowlist.c.email == email).values(email = email, added_by = added_by)
            self._execute_with_rollback(update_statement)
        else:
            insert_statement = insert(oauth_allowlist).values(email = email, added_by = added_by)
            self._execute_with_rollback(insert_statement)

        self.connection.commit()

    def remove_oauth_user_from_allowlist(self, email):
        statement = update(
            oauth_allowlist
        ).where(
            oauth_allowlist.c.email == email
        ).values(
            is_active = 0
        )
        result = self._execute_with_rollback(statement)
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
        return self._execute_with_rollback(statement).mappings().fetchall() 

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
        result = self._execute_with_rollback(statement)
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
        return self._execute_with_rollback(statement).fetchone() 

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
        return self._execute_with_rollback(statement).fetchone() 
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
        self._execute_with_rollback(statement)
        self.connection.commit() 

    def create_oauth_allowlist_user(self, params):
        statement = insert(
            oauth_users
        ).values(
            email=params[0],
            name=params[1],
            provider=params[2],
            provider_id=params[3],
            avatar_url=params[4]
        )
        result =self._execute_with_rollback(statement)
        self.connection.commit()

        return result.inserted_primary_key[0]

    # ==================== USER MANAGEMENT METHODS (Multi-User Support) ====================
    # Added 2025-10-21 for simple multi-user implementation with role-based access

    def create_user(self, username: str, email: str, password_hash: str,
                    role: str = 'user', is_active: bool = True,
                    force_password_change: bool = False,
                    completed_onboarding: bool = False):
        """Create a new user with email and role support."""
        from app.database_models import t_users
        from sqlalchemy import insert

        # Force username to lowercase for consistency
        username = username.lower()
        email = email.lower()

        stmt = insert(t_users).values(
            username=username,
            email=email,
            password_hash=password_hash,
            role=role,
            is_active=is_active,
            force_password_change=force_password_change,
            completed_onboarding=completed_onboarding
        )
        self._execute_with_rollback(stmt, operation_name="create_user")
        self.connection.commit()

        # Return created user
        return self.get_user_by_username(username)

    def get_user_by_username(self, username: str):
        """Get user by username (case-insensitive)."""
        from app.database_models import t_users
        from sqlalchemy import select

        # Handle edge case where username might be a dict (OAuth user info)
        if isinstance(username, dict):
            username = username.get('username') or username.get('email')

        # Handle None username
        if not username:
            return None

        stmt = select(t_users).where(t_users.c.username == username.lower())
        result = self._execute_with_rollback(stmt, operation_name="get_user_by_username")
        row = result.fetchone()
        return dict(row._mapping) if row else None

    def get_user_by_email(self, email: str):
        """Get user by email (case-insensitive)."""
        from app.database_models import t_users
        from sqlalchemy import select

        # Handle None email gracefully
        if email is None:
            return None

        stmt = select(t_users).where(t_users.c.email == email.lower())
        result = self._execute_with_rollback(stmt, operation_name="get_user_by_email")
        row = result.fetchone()
        return dict(row._mapping) if row else None

    def list_all_users(self, include_inactive: bool = False):
        """List all users, optionally including inactive users."""
        from app.database_models import t_users
        from sqlalchemy import select

        stmt = select(t_users)
        if not include_inactive:
            stmt = stmt.where(t_users.c.is_active == True)
        stmt = stmt.order_by(t_users.c.username)

        result = self._execute_with_rollback(stmt, operation_name="list_all_users")
        return [dict(row._mapping) for row in result.fetchall()]

    def update_user(self, username: str, **updates):
        """Update user fields by username."""
        from app.database_models import t_users
        from sqlalchemy import update

        stmt = update(t_users).where(t_users.c.username == username.lower()).values(**updates)
        self._execute_with_rollback(stmt, operation_name="update_user")
        self.connection.commit()
        return True

    def deactivate_user_by_username(self, username: str):
        """Soft delete user by setting is_active=False."""
        from app.database_models import t_users
        from sqlalchemy import update

        stmt = update(t_users).where(t_users.c.username == username.lower()).values(is_active=False)
        self._execute_with_rollback(stmt, operation_name="deactivate_user_by_username")
        self.connection.commit()
        return True

    def check_user_is_admin(self, username: str):
        """Check if user has admin role."""
        user = self.get_user_by_username(username)
        return user and user.get('role') == 'admin' if user else False

    def count_admin_users(self):
        """Count active admin users (critical for preventing last admin deletion)."""
        from app.database_models import t_users
        from sqlalchemy import select, func, and_

        stmt = select(func.count()).select_from(t_users).where(
            and_(t_users.c.role == 'admin', t_users.c.is_active == True)
        )
        result = self._execute_with_rollback(stmt, operation_name="count_admin_users")
        return result.scalar() or 0

    # ==================== END USER MANAGEMENT METHODS ====================

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
            return self._execute_with_rollback(statement).mappings().fetchall() 

    def get_oauth_system_status_and_settings(self):
        #count allowlist entries
        statement = select(
            func.count()
        ).select_from(
            oauth_allowlist
        ).where(
            oauth_allowlist.c.is_active == 1
        )
        allowlist_count = self._execute_with_rollback(statement).scalar()
        
        #count Oauth users
        statement = select(
            func.count()
        ).select_from(
            oauth_users
        ).where(
            oauth_users.c.is_active == 1
        )
        oauth_users_count = self._execute_with_rollback(statement).scalar()
        
        #get recent logins
        statement = select(
            oauth_users.c.provider,
            func.count().label('count')
        ).where(
            oauth_users.c.is_active == 1
        ).group_by(
            oauth_users.c.provider
        )
        provider_stats = {row['provider']: row['count'] for row in self._execute_with_rollback(statement).mappings().fetchall()}
        
        return allowlist_count, oauth_users_count, provider_stats

    def get_feed_item_tags(self, item_id):
        statement = select(
            feed_items.c.tags
        ).where(
            feed_items.c.id == item_id
        )
        return self._execute_with_rollback(statement).fetchone() 

    def get_feed_item_url(self, item_id):
        statement = select(
            feed_items.c.url
        ).where(
            feed_items.c.id == item_id
        )
        return self._execute_with_rollback(statement).fetchone() 

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
        return self._execute_with_rollback(statement).fetchone() 

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
        return self._execute_with_rollback(statement).fetchone() 

    def update_feed_article_data(self, params):
        statement = update(
            articles
        ).where(
            articles.c.uri == params[4]
        ).values(
            analyzed = True,
            title = func.coalesce(articles.c.title, params[0]),
            summary = func.coalesce(articles.c.summary, params[1]),
            news_source = func.coalesce(articles.c.news_source, params[2]),
            publication_date = func.coalesce(articles.c.publication_date, params[3]),
            topic = func.coalesce(articles.c.topic, 'General')
        )
        self._execute_with_rollback(statement)
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
            articles.c.analyzed == True,
            articles.c.summary != None,
            articles.c.summary != '',
            func.length(articles.c.summary) > 50
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
        return self._execute_with_rollback(statement).mappings().fetchall() 

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
        result = self._execute_with_rollback(statement)
        self.connection.commit()
        return result.lastrowid 

    def get_feed_groups_including_inactive(self):
        statement = select(
            feed_keyword_groups
        ).order_by(
            feed_keyword_groups.c.name
        )
        return self._execute_with_rollback(statement).mappings().fetchall() 



    def get_feed_groups_excluding_inactive(self):
        statement = select(
            feed_keyword_groups
        ).where(
            feed_keyword_groups.c.is_active == 1
        ).order_by(
            feed_keyword_groups.c.name
        )
        return self._execute_with_rollback(statement).mappings().fetchall() 

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
        return self._execute_with_rollback(statement).mappings().fetchall() 

    def get_feed_group_by_id(self, group_id):
        statement = select(
            feed_keyword_groups
        ).where(
            feed_keyword_groups.c.id == group_id
        )
        return self._execute_with_rollback(statement).fetchone() 

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
        self._execute_with_rollback(statement)
        self.connection.commit() 

    def delete_feed_group(self, group_id):
        statement = delete(
            feed_keyword_groups
        ).where(
            feed_keyword_groups.c.id == group_id
        )
        self._execute_with_rollback(statement)
        self.connection.commit() 

    def create_default_feed_subscription(self, group_id):
        statement = insert(
            user_feed_subscriptions
        ).values(
            group_id = group_id
        )
        self._execute_with_rollback(statement)
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
        self._execute_with_rollback(statement)
        self.connection.commit() 


    def get_source_by_id(self, source_id):
        statement = select(
            feed_group_sources
        ).where(
            feed_group_sources.c.id == source_id
        )
        return self._execute_with_rollback(statement).fetchone() 

    def get_group_source(self, group_id, source_type):
        statement = select(
            feed_group_sources.c.id
        ).where(
            feed_group_sources.c.group_id == group_id,
            feed_group_sources.c.source_type == source_type
        )
        return self._execute_with_rollback(statement).fetchone() 

    def delete_group_source(self, source_id):
        statement = delete(
            feed_group_sources
        ).where(
            feed_group_sources.c.id == source_id
        )
        self._execute_with_rollback(statement)
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
        result = self._execute_with_rollback(statement)
        self.connection.commit() 
        return result.lastrowid 

    def get_feed_group_by_name(self, name):
        statement = select(
            feed_keyword_groups.c.id
        ).where(
            feed_keyword_groups.c.name == name
        )
        return self._execute_with_rollback(statement).fetchone() 

    def get_keyword_groups_count(self):
        statement = select(
            func.count()
        ).select_from(
            keyword_groups
        )
        return self._execute_with_rollback(statement).fetchone()[0]

    def get_total_article_count(self):
        """Get total count of all articles in the database."""
        statement = select(
            func.count()
        ).select_from(
            articles
        )
        return self._execute_with_rollback(statement).scalar() or 0

    def get_articles_count_since(self, since_datetime: str):
        """Get count of articles published since a given datetime.

        Args:
            since_datetime: Datetime string in format 'YYYY-MM-DD HH:MM:SS'
        """
        statement = select(
            func.count()
        ).select_from(
            articles
        ).where(
            articles.c.publication_date >= since_datetime
        )
        return self._execute_with_rollback(statement).scalar() or 0

    def get_feed_item_count(self):
        statement = select(
            func.count()
        ).select_from(
            feed_items
        )
        return self._execute_with_rollback(statement).fetchone()[0] 

    def get_article_id_by_url(self, url):
        statement = select(
            articles.c.id
        ).where(
            articles.c.uri == url
        )
        article_result = self._execute_with_rollback(statement).fetchone()

        return article_result[0] if article_result else None 

    def check_if_article_exists_with_enrichment(self, url):
        statement = select(
            articles.c.id
        ).where(
            articles.c.uri == url,
            articles.c.analyzed == True
        )
        return self._execute_with_rollback(statement).fetchone()

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
            analyzed = False,
            topic = 'General'
        )
        result = self._execute_with_rollback(statement)
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
        return self._execute_with_rollback(statement).fetchone() 

    def update_feed_tags(self, params):
        statement = update(
            feed_items
        ).where(
            feed_items.c.id == params[1]
        ).values(
            tags = params[0],
            updated_at = func.now()
        )
        self._execute_with_rollback(statement)
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

        return self._execute_with_rollback(statement).mappings().fetchall() 

    def get_statistics_for_specific_feed_group(self, group_id):
        # Get total items count
        statement = select(
            func.count()
        ).select_from(
            feed_items
        ).where(
            feed_items.c.group_id == group_id
        )

        total_items = self._execute_with_rollback(statement).scalar()
        
        # Get counts by source type
        statement = select(
            feed_items.c.source_type,
            func.count().label('count')
        ).where(
            feed_items.c.group_id == group_id
        ).group_by(
            feed_items.c.source_type
        )
        source_counts = dict(self.connection.execute(statement).mappings().fetchall())

        # Get recent items count (last 7 days)
        # Calculate 7 days ago in Python (portable across dialects)
        seven_days_ago = datetime.utcnow() - timedelta(days=7)

        statement = select(
            func.count()
        ).select_from(
            feed_items
        ).where(
            feed_items.c.group_id == group_id,
            feed_items.c.publication_date >= seven_days_ago
        )
        recent_items = self._execute_with_rollback(statement).scalar()

        return total_items, source_counts, recent_items

    def get_is_keyword_monitor_enabled(self):
        settings = self.get_keyword_monitor_settings_by_id(1)
        return bool(settings['is_enabled']) if settings and settings['is_enabled'] else False

    def get_keyword_monitor_last_check_time(self):
        # TODO: Table t_keyword_monitor_checks doesn't exist, need to add or remove this method
        return None
        # statement = select(
        #     func.max(keyword_monitor_checks.c.check_time)
        # )
        # return self._execute_with_rollback(statement).scalar() 

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
        return self._execute_with_rollback(statement).mappings().fetchall() 

    def delete_keyword_alerts_by_article_url(self, url):
        statement = delete(
            keyword_alerts
        ).where(
            keyword_alerts.c.article_uri == url
        )
        self._execute_with_rollback(statement)
        self.connection.commit() 

    def delete_keyword_alerts_by_article_url_from_new_table(self, url):
        statement = delete(
            keyword_article_matches
        ).where(
            keyword_article_matches.c.article_uri == url
        )
        self._execute_with_rollback(statement)
        self.connection.commit()

    def mark_article_as_below_threshold(self, article_uri):
        """
        Mark keyword_article_matches for this article as processed but filtered.
        No database changes needed - the article exists with relevance scores,
        and we can determine if it's below threshold by checking the scores.
        """
        # No-op: The article is already saved with relevance scores
        # The UI can determine if it's below threshold by comparing scores
        self.logger.debug(f"Article {article_uri} saved with relevance scores for review")
        pass

    def get_total_articles_and_sample_categories_for_topic(self, topic: str):
        statement = select(
            func.count()
        ).select_from(
            articles
        ).where(
            func.lower(articles.c.topic) == func.lower(topic)
        )
        total_topic_articles = self._execute_with_rollback(statement).scalar()

        statement = select(
            func.count()
        ).select_from(
            articles
        ).where(
            func.lower(articles.c.topic) == func.lower(topic),
            articles.c.category != None,
            articles.c.category != ''
        )
        articles_with_categories = self._execute_with_rollback(statement).scalar()

        statement = select(
            articles.c.category
        ).where(
            func.lower(articles.c.topic) == func.lower(topic),
            articles.c.category != None,
            articles.c.category != ''
        ).distinct()
        sample_categories = [row["category"] for row in self._execute_with_rollback(statement).mappings().fetchall()]

        return total_topic_articles, articles_with_categories, sample_categories 

    def get_topic(self, topic):
        statement = select(
            articles.c.topic
        ).where(
            func.lower(articles.c.topic) == func.lower(topic)
        ).distinct()
        return self._execute_with_rollback(statement).fetchone() 

    def get_articles_count_from_topic_and_categories(self, placeholders, params):
        statement = select(
            func.count()
        ).select_from(
            articles
        ).where(
            func.lower(articles.c.topic) == func.lower(params[0]),
            articles.c.category.in_(placeholders)
        )
        return self._execute_with_rollback(statement).scalar()

    def get_article_count_for_topic(self, topic):
        statement = select(
            func.count()
        ).select_from(
            articles
        ).where(
            func.lower(articles.c.topic) == func.lower(topic)
        )
        return self._execute_with_rollback(statement).scalar() 

    def get_recent_articles_for_topic_and_category(self, params):
        statement = select(
            articles.c.title,
            articles.c.news_source,
            articles.c.uri,
            articles.c.sentiment,
            articles.c.future_signal,
            articles.c.time_to_impact,
            articles.c.publication_date
        ).where(
            and_(
                func.lower(articles.c.topic) == func.lower(params[0]),
                func.lower(articles.c.category) == func.lower(params[1]),
                articles.c.publication_date >= datetime.utcnow() - timedelta(days=params[2])
            )
        ).order_by(
            articles.c.publication_date.desc()
        ).limit(5)

        return self._execute_with_rollback(statement).mappings().fetchall()

    def get_categories_for_topic(self, topic):
        statement = select(
            articles.c.category
        ).where(
            func.lower(articles.c.topic) == func.lower(topic),
            articles.c.category != None,
            articles.c.category != ''
        ).distinct()

        return [row["category"] for row in self._execute_with_rollback(statement).mappings().fetchall()] 

    def get_podcasts_columns(self):
        return [col.name for col in podcasts.columns]

    def generate_latest_podcasts(self, topic, column_names, has_transcript, has_topic, has_audio_url):
        select_columns = [podcasts.c.id]

        if 'title' in column_names:
            select_columns.append(podcasts.c.title)
        else:
            select_columns.append(literal("Untitled Podcast").label("title"))

        if 'created_at' in column_names:
            select_columns.append(podcasts.c.created_at)
        else:
            select_columns.append(literal(None).label("created_at"))

        if has_audio_url:
            select_columns.append(podcasts.c.audio_url)

        if has_transcript:
            select_columns.append(podcasts.c.transcript)

        # Build base statement
        statement = select(*select_columns).select_from(podcasts)

        # Add WHERE clause if needed
        if has_topic:
            statement = statement.where(
                or_(
                    podcasts.c.topic == topic,
                    podcasts.c.topic.is_(None),
                    podcasts.c.topic == "General"
                )
            )

        # Add ORDER BY and LIMIT
        statement = statement.order_by(podcasts.c.created_at.desc()).limit(1)

        # Execute and return result
        return self._execute_with_rollback(statement).fetchone()

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

        articles_list = self._execute_with_rollback(statement).mappings().fetchall()
        column_names = [col.name for col in articles.columns]

        return column_names, articles_list 

    def enriched_articles(self, limit):
        # Query for articles that have a non-null and non-empty category
        statement = select(articles).where(
            articles.c.category.isnot(None),
            articles.c.category != ''
        ).order_by(
            articles.c.submission_date.desc()
        ).limit(limit)

        articles_list = self._execute_with_rollback(statement).mappings().fetchall()

        result_articles = []
        for article in articles_list:
            # Convert mapping to dict to allow modification
            article_dict = dict(article)

            if article_dict.get('tags'):
                article_dict['tags'] = article_dict['tags'].split(',')
            else:
                article_dict['tags'] = []

            result_articles.append(article_dict)

        return result_articles

    def create_model_bias_arena_runs(self, params):
        statement = insert(model_bias_arena_runs).values(
            name=params[0],
            description=params[1],
            benchmark_model=params[2],
            selected_models=params[3],
            article_count=params[4],
            rounds=params[5],
            current_round=params[6],
            status='running'
        )

        result = self._execute_with_rollback(statement)
        self.connection.commit()

        return result.inserted_primary_key[0]

    def store_evaluation_results(self, params):
        statement = insert(model_bias_arena_results).values(
            run_id=params[0],
            article_uri=params[1],
            model_name=params[2],
            response_text=params[3],
            bias_score=params[4],
            confidence_score=params[5],
            response_time_ms=params[6],
            error_message=params[7]
        )
        self._execute_with_rollback(statement)
        self.connection.commit()

    def store_ontological_results(self, params):
        statement = insert(model_bias_arena_results).values(
            run_id=params[0],
            article_uri=params[1],
            model_name=params[2],
            response_text=params[3],
            response_time_ms=params[4],
            sentiment=params[5],
            sentiment_explanation=params[6],
            future_signal=params[7],
            future_signal_explanation=params[8],
            time_to_impact=params[9],
            time_to_impact_explanation=params[10],
            driver_type=params[11],
            driver_type_explanation=params[12],
            category=params[13],
            category_explanation=params[14],
            political_bias=params[15],
            political_bias_explanation=params[16],
            factuality=params[17],
            factuality_explanation=params[18],
            round_number=params[19]
        )
        self._execute_with_rollback(statement)
        self.connection.commit()

    def update_run_status(self, params):
        statement = update(model_bias_arena_runs).where(model_bias_arena_runs.c.id == params[1]).values(
                status=params[0],
                completed_at=func.current_timestamp()
            )

        self._execute_with_rollback(statement)
        self.connection.commit()

    def get_run_details(self, run_id):
        statement = select(
            model_bias_arena_runs.c.id,
            model_bias_arena_runs.c.name,
            model_bias_arena_runs.c.description,
            model_bias_arena_runs.c.benchmark_model,
            model_bias_arena_runs.c.selected_models,
            model_bias_arena_runs.c.article_count,
            model_bias_arena_runs.c.rounds,
            model_bias_arena_runs.c.current_round,
            model_bias_arena_runs.c.created_at,
            model_bias_arena_runs.c.completed_at,
            model_bias_arena_runs.c.status
        ).where(model_bias_arena_runs.c.id == run_id)

        return self._execute_with_rollback(statement).mappings().fetchone()                         

    def get_ontological_results_with_article_info(self, run_id):
        statement = select(
            model_bias_arena_results.c.model_name,
            model_bias_arena_results.c.article_uri,
            model_bias_arena_results.c.sentiment,
            model_bias_arena_results.c.sentiment_explanation,
            model_bias_arena_results.c.future_signal,
            model_bias_arena_results.c.future_signal_explanation,
            model_bias_arena_results.c.time_to_impact,
            model_bias_arena_results.c.time_to_impact_explanation,
            model_bias_arena_results.c.driver_type,
            model_bias_arena_results.c.driver_type_explanation,
            model_bias_arena_results.c.category,
            model_bias_arena_results.c.category_explanation,
            model_bias_arena_results.c.political_bias,
            model_bias_arena_results.c.political_bias_explanation,
            model_bias_arena_results.c.factuality,
            model_bias_arena_results.c.factuality_explanation,
            model_bias_arena_results.c.confidence_score,
            model_bias_arena_results.c.response_time_ms,
            model_bias_arena_results.c.error_message,
            model_bias_arena_results.c.response_text,
            model_bias_arena_results.c.round_number,
            model_bias_arena_articles.c.article_title,
            model_bias_arena_articles.c.article_summary
        ).select_from(
            model_bias_arena_results
            .join(
                model_bias_arena_articles,
                and_(
                    model_bias_arena_results.c.article_uri == model_bias_arena_articles.c.article_uri,
                    model_bias_arena_results.c.run_id == model_bias_arena_articles.c.run_id
                )
            )
        ).where(
            model_bias_arena_results.c.run_id == run_id
        ).order_by(
            model_bias_arena_results.c.article_uri,
            model_bias_arena_results.c.model_name, 
            model_bias_arena_results.c.round_number
        )

        return self._execute_with_rollback(statement).mappings().fetchall()

    def get_benchmark_data_including_media_bias_info(self, run_id):
        statement = select(
            articles.c.uri,
            articles.c.title,
            articles.c.sentiment,
            articles.c.future_signal,
            articles.c.time_to_impact,
            articles.c.driver_type,
            articles.c.category,
            articles.c.sentiment_explanation,
            articles.c.future_signal_explanation,
            articles.c.time_to_impact_explanation,
            articles.c.driver_type_explanation,
            articles.c.bias,
            articles.c.factual_reporting,
            articles.c.mbfc_credibility_rating,
            articles.c.bias_country,
            articles.c.press_freedom,
            articles.c.media_type,
            articles.c.popularity,
            articles.c.news_source
        ).select_from(
            articles
            .join(
                model_bias_arena_articles, model_bias_arena_articles.c.article_uri == articles.c.uri
            )
        ).where(
            model_bias_arena_articles.c.run_id == run_id
        ).order_by(
            articles.c.uri
        )
        return self._execute_with_rollback(statement).mappings().fetchall()

    def delete_run(self, run_id):
        statement = delete(model_bias_arena_runs).where(model_bias_arena_runs.c.id == run_id)
        result = self._execute_with_rollback(statement)
        self.connection.commit()

        return result.rowcount

    def get_source_bias_validation_data(self, url):
        statement = select(
            articles.c.bias,
            articles.c.factual_reporting,
            articles.c.mbfc_credibility_rating,
            articles.c.bias_country,
            articles.c.press_freedom,
            articles.c.media_type,
            articles.c.popularity
        ).where(articles.c.uri == url)

        return self._execute_with_rollback(statement).fetchone()

    def get_run_articles(self, run_id):
        statement = select(
            model_bias_arena_articles.c.article_uri,
            model_bias_arena_articles.c.article_title,
            model_bias_arena_articles.c.article_summary
        ).where(model_bias_arena_articles.c.run_id == run_id)

        return self._execute_with_rollback(statement).mappings().fetchall()

    def get_all_bias_evaluation_runs(self):
        statement = select(
            model_bias_arena_runs.c.id,
            model_bias_arena_runs.c.name,
            model_bias_arena_runs.c.description,
            model_bias_arena_runs.c.benchmark_model,
            model_bias_arena_runs.c.selected_models,
            model_bias_arena_runs.c.article_count,
            model_bias_arena_runs.c.rounds,
            model_bias_arena_runs.c.current_round,
            model_bias_arena_runs.c.created_at,
            model_bias_arena_runs.c.completed_at,
            model_bias_arena_runs.c.status
        ).order_by(
            model_bias_arena_runs.c.created_at.desc()
        )

        return self._execute_with_rollback(statement).mappings().fetchall()

    def update_run(self, params):
        statement = update(model_bias_arena_runs).where(
            model_bias_arena_runs.c.id == params[1]
        ).values(
                current_round=params[0]
        )

        self._execute_with_rollback(statement)
        self.connection.commit()

    def get_topics_from_article(self, article_url):
        statement = select(
            articles.c.topic
        ).where(
            articles.c.uri == article_url
        ).distinct()

        return self._execute_with_rollback(statement).fetchone()

    def get_run_info(self, run_id):
        statement = select(
            model_bias_arena_runs.c.rounds,
            model_bias_arena_runs.c.current_round
        ).where(
            model_bias_arena_runs.c.id == run_id
        )

        return self._execute_with_rollback(statement).fetchone()

    def add_articles_to_run(self, params):
        statement = insert(model_bias_arena_articles).values(
            run_id=params[0],
            article_uri=params[1],
            article_title=params[2],
            article_summary=params[3]
        )
        self._execute_with_rollback(statement)
        self.connection.commit()

    def sample_articles(self, count, topic):
        """Sample articles with complete benchmark ontological data.

        PostgreSQL-compatible version that handles NULL values correctly.
        """
        statement = select(
            articles.c.uri,
            articles.c.title,
            articles.c.summary,
            articles.c.news_source,
            articles.c.topic,
            articles.c.category,
            articles.c.sentiment,
            articles.c.future_signal,
            articles.c.time_to_impact,
            articles.c.driver_type,
            articles.c.bias,
            articles.c.factual_reporting,
            articles.c.mbfc_credibility_rating,
            articles.c.bias_country
        ).where(
            # Summary must exist and be substantial
            articles.c.summary.isnot(None),
            func.char_length(articles.c.summary) > 100,  # PostgreSQL-compatible

            # Must be analyzed (explicit boolean check for PostgreSQL)
            articles.c.analyzed.is_(True),

            # Ontological fields must be non-NULL and non-empty
            # Using and_() for explicit PostgreSQL NULL handling
            and_(articles.c.sentiment.isnot(None), articles.c.sentiment != ''),
            and_(articles.c.future_signal.isnot(None), articles.c.future_signal != ''),
            and_(articles.c.time_to_impact.isnot(None), articles.c.time_to_impact != ''),
            and_(articles.c.driver_type.isnot(None), articles.c.driver_type != ''),
            and_(articles.c.category.isnot(None), articles.c.category != ''),
            and_(articles.c.news_source.isnot(None), articles.c.news_source != '')
        )

        # Optional topic filter (filter out 'undefined' from frontend)
        if topic and topic != 'undefined' and topic.strip():
            statement = statement.where(
                articles.c.topic == topic
            )

        statement = statement.order_by(
            func.random()
        ).limit(count)

        return self._execute_with_rollback(statement).mappings().fetchall()

    def get_topics_with_article_counts(self):
        statement = select(
            articles.c.topic,
            func.count(distinct(articles.c.uri)).label('article_count'),
            func.max(articles.c.publication_date).label('last_article_date')
        ).where(
            articles.c.topic.isnot(None),
            articles.c.topic != '',
        )
        statement = statement.group_by(
            articles.c.topic
        )
        
        db_topics = {row['topic']: {"article_count": row['article_count'], "last_article_date": row['last_article_date']}
                        for row in self._execute_with_rollback(statement).mappings().fetchall()}
        return db_topics

    def debug_articles(self):
        statement = select(articles)
        articles = self._execute_with_rollback(statement).mappings().fetchall()
        return articles

    def get_rate_limit_status(self):
        statement = select(
            keyword_monitor_status.c.requests_today,
            keyword_monitor_status.c.last_error
        ).where(
            keyword_monitor_status.c.id == 1
        )
        return self._execute_with_rollback(statement).mappings().fetchone()

    def get_monitor_page_keywords(self):
        statement = select(
            keyword_groups.c.id,
            keyword_groups.c.name,
            keyword_groups.c.topic,
            monitored_keywords.c.id.label('keyword_id'),
            monitored_keywords.c.keyword
        ).select_from(
            keyword_groups.join(monitored_keywords, keyword_groups.c.id == monitored_keywords.c.group_id, isouter=True)
        ).order_by(
            keyword_groups.c.name,
            monitored_keywords.c.keyword
        )

        return self._execute_with_rollback(statement).mappings().fetchall()

    def get_monitored_keywords_for_keyword_alerts_page(self):
        statement = select(
            func.max(monitored_keywords.c.last_checked).label('last_check_time'),
            select(keyword_monitor_settings.c.check_interval).where(keyword_monitor_settings.c.id == 1).scalar_subquery().label('check_interval'),
            select(keyword_monitor_settings.c.interval_unit).where(keyword_monitor_settings.c.id == 1).scalar_subquery().label('interval_unit'),
            select(keyword_monitor_status.c.last_error).where(keyword_monitor_status.c.id == 1).scalar_subquery().label('last_error'),
            select(keyword_monitor_settings.c.is_enabled).where(keyword_monitor_settings.c.id == 1).scalar_subquery().label('is_enabled')
        ).select_from(
            monitored_keywords
        )

        return self._execute_with_rollback(statement).fetchone()

    def get_all_groups_with_their_alerts_and_status(self):

        # CTE for alert counts
        alert_counts_cte = select(
            keyword_groups.c.id.label('group_id'),
            func.count(distinct(keyword_alerts.c.id)).label('unread_count')
        ).select_from(
            keyword_groups
            .join(monitored_keywords, keyword_groups.c.id == monitored_keywords.c.group_id, isouter=True)
            .join(keyword_alerts, (monitored_keywords.c.id == keyword_alerts.c.keyword_id) & (keyword_alerts.c.is_read == 0), isouter=True)
        ).group_by(
            keyword_groups.c.id
        ).cte('alert_counts')

        
        # Subquery for keywords
        keywords_subq = select(
            func.group_concat(monitored_keywords.c.keyword, literal_column('||'))
        ).where(
            monitored_keywords.c.group_id == keyword_groups.c.id
        ).scalar_subquery()

        # Main query
        statement = select(
            keyword_groups.c.id,
            keyword_groups.c.name,
            keyword_groups.c.topic,
            alert_counts_cte.c.unread_count,
            keywords_subq.label('keywords')
        ).select_from(
            keyword_groups
            .join(alert_counts_cte, keyword_groups.c.id == alert_counts_cte.c.group_id, isouter=True)
        ).order_by(
            alert_counts_cte.c.unread_count.desc(),
            keyword_groups.c.name
        )

        return self._execute_with_rollback(statement).mappings().fetchall()

    def check_if_keyword_article_matches_table_exists(self):
        inspector = inspect(self.connection)
        return inspector.has_table('keyword_article_matches')

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
        statement = select(
            keyword_alerts.c.id,
            keyword_alerts.c.detected_at,
            keyword_alerts.c.article_uri,
            articles.c.title,
            articles.c.uri.label('url'),
            articles.c.news_source,
            articles.c.publication_date,
            articles.c.summary,
            monitored_keywords.c.keyword.label('matched_keyword')
        ).select_from(
            keyword_alerts.join(monitored_keywords, keyword_alerts.c.keyword_id == monitored_keywords.c.id)
            .join(articles, keyword_alerts.c.article_uri == articles.c.uri)
        ).where(
            monitored_keywords.c.group_id == group_id,
            keyword_alerts.c.is_read == 0
        ).order_by(
            keyword_alerts.c.detected_at.desc()
        )

        return self._execute_with_rollback(statement).mappings().fetchall()

    def get_all_completed_podcasts(self):
        statement = select(
            podcasts.c.id,
            podcasts.c.title,
            podcasts.c.created_at,
            podcasts.c.audio_url,
            podcasts.c.transcript
        ).where(
            podcasts.c.status == 'completed'
        ).order_by(
            podcasts.c.created_at.desc()
        ).limit(50)

        return self._execute_with_rollback(statement).mappings().fetchall()

    def create_podcast(self, params):
        statement = insert(podcasts).values(
            id=params[0],
            title=params[1],
            created_at=func.current_timestamp(),
            status= 'processing',
            config=params[2],
            article_uris=params[3]
        )
        self._execute_with_rollback(statement)
        self.connection.commit()

    def update_podcast_status(self, params):
        statement = update(podcasts).where(podcasts.c.id == params[3]).values(
                status=params[0],
                audio_url=params[1],
                transcript=params[2]
            )
        self._execute_with_rollback(statement)
        self.connection.commit()

    def get_flow_data(self, topic, timeframe, limit):
        statement = select(
            func.coalesce(articles.c.news_source, 'Unknown').label('source'),
            func.coalesce(articles.c.category, 'Unknown').label('category'),
            func.coalesce(articles.c.sentiment, 'Unknown').label('sentiment'),
            func.coalesce(articles.c.driver_type, 'Unknown').label('driver_type'),
            articles.c.submission_date
        ).select_from(
            articles
        )
        if topic:
            statement = statement.where(
                articles.c.topic == topic
            )
        if timeframe != "all":
            try:
                days = int(timeframe)
                statement = statement.where(
                    articles.c.submission_date >= datetime.utcnow() - timedelta(days=days)
                )
            except ValueError:
                self.logger.warning("Invalid timeframe value provided: %s", timeframe)

        statement = statement.order_by(
            articles.c.submission_date.desc()
        ).limit(limit)

        return self._execute_with_rollback(statement).mappings().fetchall()

    def create_keyword_monitor_group(self, params):
        statement = insert(keyword_groups).values(
            name=params[0],
            topic=params[1]
        )
        result =self._execute_with_rollback(statement)
        self.connection.commit()

        return result.inserted_primary_key[0]

    def create_keyword(self, params):
        statement = insert(monitored_keywords).values(
            group_id=params[0],
            keyword=params[1]
        )
        self._execute_with_rollback(statement)
        self.connection.commit()

    def delete_keyword(self, keyword_id):
        statement = delete(monitored_keywords).where(monitored_keywords.c.id == keyword_id)
        self._execute_with_rollback(statement)
        self.connection.commit()

    def delete_keyword_group(self, group_id):
        statement = delete(keyword_groups).where(keyword_groups.c.id == group_id)
        self._execute_with_rollback(statement)
        self.connection.commit()

    def delete_group_keywords(self, group_id):
        statement = delete(monitored_keywords).where(monitored_keywords.c.group_id == group_id)
        self._execute_with_rollback(statement)
        self.connection.commit()

    def create_group(self, group_name, group_topic):
        statement = insert(keyword_groups).values(
            name=group_name,
            topic=group_topic
        )
        result = self._execute_with_rollback(statement)
        self.connection.commit()

        return result.inserted_primary_key[0]

    def add_keywords_to_group(self, group_id, keyword):
        statement = insert(monitored_keywords).values(
            group_id=group_id,
            keyword=keyword
        )
        self._execute_with_rollback(statement)
        self.connection.commit()

    def get_all_group_ids_associated_to_topic(self, topic_name):
        statement = select(
            keyword_groups.c.id
        ).where(
            keyword_groups.c.topic == topic_name
        )
        return self._execute_with_rollback(statement).mappings().fetchall()

    def get_keyword_ids_associated_to_group(self, group_id):
        statement = select(
            monitored_keywords.c.id
        ).where(
            monitored_keywords.c.group_id == group_id
        )
        return self._execute_with_rollback(statement).mappings().fetchall()

    def get_keywords_associated_to_group(self, group_id):
        statement = select(
            monitored_keywords.c.keyword
        ).where(
            monitored_keywords.c.group_id == group_id
        )

        return [row["keyword"] for row in self._execute_with_rollback(statement).mappings().fetchall()]

    def get_keywords_associated_to_group_ordered_by_keyword(self, group_id):
        statement = select(
            monitored_keywords.c.keyword
        ).where(
            monitored_keywords.c.group_id == group_id
        ).order_by(
            monitored_keywords.c.keyword
        )

        return [row["keyword"] for row in self._execute_with_rollback(statement).mappings().fetchall()]

    def delete_keyword_article_matches_from_new_table_structure(self, group_id):
        statement = delete(keyword_article_matches).where(keyword_article_matches.c.group_id == group_id)
        result = self._execute_with_rollback(statement)
        self.connection.commit()

        return result.rowcount

    def delete_keyword_article_matches_from_old_table_structure(self, ids_str, keyword_ids):
        statement = delete(keyword_alerts).where(keyword_alerts.c.keyword_id.in_(keyword_ids))
        result = self._execute_with_rollback(statement)
        self.connection.commit()

        return result.rowcount

    def delete_groups_keywords(self, ids_str, group_ids):
        statement = delete(monitored_keywords).where(monitored_keywords.c.group_id.in_(group_ids))
        result = self._execute_with_rollback(statement)
        self.connection.commit()

        return result.rowcount

    def delete_all_keyword_groups(self, topic_name):
        statement = delete(keyword_groups).where(keyword_groups.c.topic == topic_name)
        result = self._execute_with_rollback(statement)
        self.connection.commit()

        return result.rowcount

    def check_if_alert_id_exists_in_new_table_structure(self, alert_id):
        statement = select(
            keyword_article_matches.c.id
        ).where(
            keyword_article_matches.c.id == alert_id
        )

        return self._execute_with_rollback(statement).fetchone()

    def mark_alert_as_read_or_unread_in_new_table(self, alert_id, read_or_unread):
        statement = update(keyword_article_matches).where(keyword_article_matches.c.id == alert_id).values(is_read = read_or_unread)

        self._execute_with_rollback(statement)
        self.connection.commit()

    def mark_alert_as_read_or_unread_in_old_table(self, alert_id, read_or_unread):
        statement = update(keyword_alerts).where(keyword_alerts.c.id == alert_id).values(is_read = read_or_unread)

        self._execute_with_rollback(statement)
        self.connection.commit()

    def get_number_of_monitored_keywords_by_group_id(self, group_id):
        statement = select(
            func.count()
        ).select_from(
            monitored_keywords
        ).where(
            monitored_keywords.c.group_id == group_id
        )

        return self._execute_with_rollback(statement).scalar()

    def get_total_number_of_keywords(self):
        statement = select(
            func.count()
        ).select_from(
            monitored_keywords
        )

        return self._execute_with_rollback(statement).scalar()

    def get_alerts(self, show_read):
        statement = select(
            keyword_alerts,
            articles,
            monitored_keywords.c.keyword.label('matched_keyword')
        ).select_from(
            keyword_alerts.join(
                articles,
                keyword_alerts.c.article_uri == articles.c.uri
            ).join(
                monitored_keywords,
                keyword_alerts.c.keyword_id == monitored_keywords.c.id
            )
        ).order_by(
            keyword_alerts.c.detected_at.desc()
        ).limit(100)

        if not show_read:
            statement = statement.where(
                keyword_alerts.c.is_read == 0
            )

        columns = [column.name for column in statement.columns]

        return columns, self._execute_with_rollback(statement).mappings().fetchall()

    def get_article_enrichment(self, article_data):
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
            articles.c.quality_issues
        ).where(articles.c.uri == article_data["uri"])

        return self._execute_with_rollback(statement).fetchone()

    def get_all_groups_with_alerts_and_status_new_table_structure(self):
        """Get all keyword groups with their alert counts and growth status.

        Uses PostgreSQL connection to query keyword_article_matches table.
        Returns list of tuples: (id, name, topic, unread_count, total_count, growth_status)
        """
        query = text("""
            WITH alert_counts AS (
                SELECT kg.id as group_id,
                       COUNT(DISTINCT CASE WHEN ka.is_read = 0 AND a.uri IS NOT NULL THEN ka.id END) as unread_count,
                       COUNT(DISTINCT CASE WHEN a.uri IS NOT NULL THEN ka.id END) as total_count
                FROM keyword_groups kg
                LEFT JOIN keyword_article_matches ka ON kg.id = ka.group_id
                LEFT JOIN articles a ON ka.article_uri = a.uri
                GROUP BY kg.id
            ),
            growth_data AS (
                SELECT kg.id as group_id,
                       CASE
                           WHEN COUNT(CASE WHEN a.uri IS NOT NULL THEN ka.id END) = 0 THEN 'No data'
                           WHEN MAX(ka.detected_at) < (CURRENT_DATE - INTERVAL '7 days')::text THEN 'Inactive'
                           WHEN COUNT(DISTINCT CASE WHEN a.uri IS NOT NULL THEN ka.id END) > 20 THEN 'High growth'
                           WHEN COUNT(DISTINCT CASE WHEN a.uri IS NOT NULL THEN ka.id END) > 10 THEN 'Growing'
                           ELSE 'Stable'
                       END as growth_status
                FROM keyword_groups kg
                LEFT JOIN keyword_article_matches ka ON kg.id = ka.group_id
                LEFT JOIN articles a ON ka.article_uri = a.uri
                GROUP BY kg.id
            )
            SELECT kg.id,
                   kg.name,
                   kg.topic,
                   COALESCE(ac.unread_count, 0) as unread_count,
                   COALESCE(ac.total_count, 0) as total_count,
                   COALESCE(gd.growth_status, 'No data') as growth_status
            FROM keyword_groups kg
            LEFT JOIN alert_counts ac ON kg.id = ac.group_id
            LEFT JOIN growth_data gd ON kg.id = gd.group_id
            ORDER BY ac.unread_count DESC, kg.name
        """)

        result = self._execute_with_rollback(query)
        return result.fetchall()

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
        statement = select(
            keyword_article_matches.c.id,
            keyword_article_matches.c.article_uri,
            keyword_article_matches.c.keyword_ids,
            literal(None).label("matched_keyword"),
            keyword_article_matches.c.is_read,
            keyword_article_matches.c.detected_at,
            literal(None).label("below_threshold"),
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
                keyword_article_matches.c.article_uri == articles.c.uri
            )
        ).where(
            keyword_article_matches.c.group_id == group_id,
            keyword_article_matches.c.is_read == 0
        ).order_by(
            keyword_article_matches.c.detected_at.desc()
        ).limit(25)

        return self._execute_with_rollback(statement).mappings().fetchall()

    def get_most_recent_unread_alerts_for_group_id_old_table_structure(self, group_id):
        statement = select(
            keyword_alerts.c.id,
            keyword_alerts.c.article_uri,
            keyword_alerts.c.keyword_id,
            monitored_keywords.c.keyword.label("matched_keyword"),
            keyword_alerts.c.is_read,
            keyword_alerts.c.detected_at,
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
            articles.c.extracted_article_keywords
        ).select_from(
            keyword_alerts.join(
                articles,
                keyword_alerts.c.article_uri == articles.c.uri
            ).join(
                monitored_keywords,
                keyword_alerts.c.keyword_id == monitored_keywords.c.id
            )
        ).where(
            monitored_keywords.c.group_id == group_id,
            keyword_alerts.c.is_read == 0
        ).order_by(
            keyword_alerts.c.detected_at.desc()
        ).limit(25)

        return self._execute_with_rollback(statement).mappings().fetchall()

    def count_total_group_unread_articles_new_table_structure(self, group_id):
        statement = select(
            func.count()
        ).select_from(
            keyword_article_matches.join(
                articles,
                keyword_article_matches.c.article_uri == articles.c.uri
            )
        ).where(
            keyword_article_matches.c.group_id == group_id,
            keyword_article_matches.c.is_read == 0
        )

        return self._execute_with_rollback(statement).scalar()

    def count_total_group_unread_articles_old_table_structure(self, group_id):
        statement = select(
            func.count()
        ).select_from(
            keyword_alerts.join(
                articles,
                keyword_alerts.c.article_uri == articles.c.uri
            ).join(
                monitored_keywords,
                keyword_alerts.c.keyword_id == monitored_keywords.c.id
            )
        ).where(
            monitored_keywords.c.group_id == group_id,
            keyword_alerts.c.is_read == 0
        )

    def get_all_matched_keywords_for_article_and_group(self, placeholders, keyword_id_list_and_group_id):
        statement = select(
            monitored_keywords.c.keyword
        ).where(
            monitored_keywords.c.id.in_(keyword_id_list_and_group_id[:-1]),
            monitored_keywords.c.group_id == keyword_id_list_and_group_id[-1]
        ).distinct()
        
        return [row["keyword"] for row in self._execute_with_rollback(statement).mappings().fetchall()]

    def get_all_matched_keywords_for_article_and_group_by_article_url_and_group_id(self, article_url, group_id):
        statement = select(
            monitored_keywords.c.keyword
        ).select_from(
            keyword_alerts.join(
                monitored_keywords,
                keyword_alerts.c.keyword_id == monitored_keywords.c.id
            )
        ).where(
            keyword_alerts.c.article_uri == article_url,
            monitored_keywords.c.group_id == group_id
        ).distinct()
        
        return [row["keyword"] for row in self._execute_with_rollback(statement).mappings().fetchall()]

    def get_article_enrichment_by_article_url(self, article_url):
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
            articles.c.extracted_article_keywords
        ).where(articles.c.uri == article_url)
        
        return self._execute_with_rollback(statement).fetchone()

    def create_keyword_monitor_table_if_not_exists_and_insert_default_value(self):
        # TODO: Move to migrations.

        # Check if the keyword_monitor_status table has a row with id 1
        statement = select(keyword_monitor_status).where(keyword_monitor_status.c.id == 1)
        existing = self._execute_with_rollback(statement).fetchone()

        if not existing:
            statement = insert(keyword_monitor_status).values(
                id = 1,
                requests_today = 0
            )
            self._execute_with_rollback(statement)
            self.connection.commit()

    def check_keyword_monitor_status_and_settings_tables(self):
        status_data_stmt = select(keyword_monitor_status).where(keyword_monitor_status.c.id == 1)
        status_data = self._execute_with_rollback(status_data_stmt).fetchone()

        settings_data_stmt = select(keyword_monitor_settings).where(keyword_monitor_settings.c.id == 1)
        settings_data = self._execute_with_rollback(settings_data_stmt).fetchone()

        return status_data, settings_data

    def get_count_of_monitored_keywords(self):
        statement = select(func.count()).select_from(
                monitored_keywords
            ).where(
                exists(
                    select(1).select_from(
                        keyword_groups
                    ).where(
                        keyword_groups.c.id == monitored_keywords.c.group_id
                    )
                )
            )

        return self._execute_with_rollback(statement).scalar()


    def get_settings_and_status_together(self):
        kms_subq = select(
            keyword_monitor_status.c.id,
            keyword_monitor_status.c.requests_today,
            keyword_monitor_status.c.last_error,
            keyword_monitor_status.c.last_check_time
        ).where(
            keyword_monitor_status.c.id == 1,
            keyword_monitor_status.c.last_reset_date == func.cast(func.current_date(), Text)
        ).subquery()

        statement = select(
            keyword_monitor_settings.c.check_interval,
            keyword_monitor_settings.c.interval_unit,
            keyword_monitor_settings.c.search_fields,
            keyword_monitor_settings.c.language,
            keyword_monitor_settings.c.sort_by,
            keyword_monitor_settings.c.page_size,
            keyword_monitor_settings.c.daily_request_limit,
            keyword_monitor_settings.c.is_enabled,
            keyword_monitor_settings.c.provider,
            func.coalesce(keyword_monitor_settings.c.auto_ingest_enabled, False).label("auto_ingest_enabled"),
            func.coalesce(keyword_monitor_settings.c.min_relevance_threshold, 0.0).label("min_relevance_threshold"),
            func.coalesce(keyword_monitor_settings.c.quality_control_enabled, True).label("quality_control_enabled"),
            func.coalesce(keyword_monitor_settings.c.auto_save_approved_only, False).label("auto_save_approved_only"),
            func.coalesce(keyword_monitor_settings.c.default_llm_model, "gpt-4o-mini").label("default_llm_model"),
            func.coalesce(keyword_monitor_settings.c.llm_temperature, 0.1).label("llm_temperature"),
            func.coalesce(keyword_monitor_settings.c.llm_max_tokens, 1000).label("llm_max_tokens"),
            func.coalesce(kms_subq.c.requests_today, 0).label("requests_today"),
            kms_subq.c.last_error,
            kms_subq.c.last_check_time
        ).select_from(
            keyword_monitor_settings.join(
                kms_subq,
                kms_subq.c.id == 1,
                isouter=True
            )
        ).where(keyword_monitor_settings.c.id == 1)

        return self._execute_with_rollback(statement).fetchone()

    def update_or_insert_keyword_monitor_settings(self, params):
        values_dict = {
            "id": 1,
            "check_interval": params[0],
            "interval_unit": params[1],
            "search_fields": params[2],
            "language": params[3],
            "sort_by": params[4],
            "page_size": params[5],
            "daily_request_limit": params[6],
            "provider": params[7],
            "auto_ingest_enabled": params[8],
            "min_relevance_threshold": params[9],
            "quality_control_enabled": params[10],
            "auto_save_approved_only": params[11],
            "default_llm_model": params[12],
            "llm_temperature": params[13],
            "llm_max_tokens": params[14]
        }

        stmt = (
            update(keyword_monitor_settings)
            .where(keyword_monitor_settings.c.id == 1)
            .values(**values_dict)
            if self._execute_with_rollback(
                select(keyword_monitor_settings).where(keyword_monitor_settings.c.id == 1)
            ).fetchone()
            else insert(keyword_monitor_settings).values(**values_dict)
        )

        self._execute_with_rollback(stmt)
        self.connection.commit()

    def update_keyword_monitor_settings_provider(self, provider: str):
        """Update or create keyword_monitor_settings with the specified provider.

        This is a simplified version for onboarding that only updates the provider field.
        If no settings exist, it creates default settings with the specified provider.

        Args:
            provider: The news provider to use ('newsapi', 'thenewsapi', or 'newsdata')
        """
        # Check if settings exist
        existing = self._execute_with_rollback(
            select(keyword_monitor_settings).where(keyword_monitor_settings.c.id == 1)
        ).fetchone()

        if existing:
            # Update existing settings - only provider field
            stmt = update(keyword_monitor_settings).where(
                keyword_monitor_settings.c.id == 1
            ).values(provider=provider)
        else:
            # Create default settings with the specified provider
            stmt = insert(keyword_monitor_settings).values(
                id=1,
                check_interval=15,
                interval_unit=60,
                search_fields="title,description",
                language="en",
                sort_by="publishedAt",
                page_size=100,
                is_enabled=True,
                daily_request_limit=100,
                search_date_range=7,
                provider=provider,
                auto_ingest_enabled=False,
                min_relevance_threshold=0.7,
                quality_control_enabled=True,
                auto_save_approved_only=False,
                default_llm_model="gpt-4",
                llm_temperature=0.7,
                llm_max_tokens=2000
            )

        self._execute_with_rollback(stmt)
        self.connection.commit()

    def get_trends(self):
        """Get trend data for all keyword groups over the last 7 days.

        Uses PostgreSQL connection and keyword_article_matches table.
        Returns: List of tuples (group_id, group_name, date, count)
        """
        # PostgreSQL-compatible query using generate_series instead of recursive CTE
        query = text("""
            WITH dates AS (
                SELECT generate_series(
                    CURRENT_DATE - INTERVAL '6 days',
                    CURRENT_DATE,
                    INTERVAL '1 day'
                )::date as date
            ),
            daily_counts AS (
                SELECT
                    kg.id as group_id,
                    kg.name as group_name,
                    CAST(kam.detected_at::timestamp AS DATE) as detection_date,
                    COUNT(*) as article_count
                FROM keyword_article_matches kam
                JOIN keyword_groups kg ON kam.group_id = kg.id
                WHERE kam.detected_at::timestamp >= CURRENT_DATE - INTERVAL '6 days'
                GROUP BY kg.id, kg.name, CAST(kam.detected_at::timestamp AS DATE)
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

        result = self._execute_with_rollback(query)
        return result.fetchall()

    def topic_exists(self, topic):
        statement = select(
            articles.c.topic
        ).where(articles.c.topic == topic).limit(1)

        return self._execute_with_rollback(statement).fetchone() is not None

    def get_keyword_group_id_by_name_and_topic(self, group_name, topic_name):
        statement = select(
            keyword_groups.c.id
        ).where(
            keyword_groups.c.name == group_name,
            keyword_groups.c.topic == topic_name
        )

        return self._execute_with_rollback(statement).fetchone()

    def toggle_polling(self, toggle):
        statement = select(
            keyword_monitor_settings.c.id
        ).where(
            keyword_monitor_settings.c.id == 1
        )

        # First check if settings exist
        settings_exists = self._execute_with_rollback(statement).fetchone() is not None

        if settings_exists:
            # Just update is_enabled if settings exist
            statement = update(keyword_monitor_settings).where(keyword_monitor_settings.c.id == 1).values(is_enabled = toggle.enabled)
            self._execute_with_rollback(statement)
        else:
            # Insert with defaults if no settings exist
            statement = insert(keyword_monitor_settings).values(
                id = 1, 
                check_interval = 15,
                interval_unit = 60,
                search_fields = 'title,description,content',
                language = 'en',
                sort_by = 'publishedAt',
                page_size = 10,
                is_enabled = toggle.enabled
            )
            self._execute_with_rollback(statement)
            
        self.connection.commit()

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
        statement = select(
            keyword_groups.c.name.label("group_name"),
            keyword_groups.c.topic,
            articles.c.title,
            articles.c.news_source,
            articles.c.uri,
            articles.c.publication_date,
            monitored_keywords.c.keyword.label("matched_keyword"),
            keyword_alerts.c.detected_at
        ).select_from(
            keyword_alerts.join(
                monitored_keywords,
                keyword_alerts.c.keyword_id == monitored_keywords.c.id
            ).join(
                keyword_groups,
                monitored_keywords.c.group_id == keyword_groups.c.id
            ).join(
                articles,
                keyword_alerts.c.article_uri == articles.c.uri
            )
        ).order_by(
            keyword_alerts.c.detected_at.desc()
        )
        
        return self._execute_with_rollback(statement).mappings().fetchall()

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
        statement = select(
            keyword_groups.c.name.label("group_name"),
            keyword_groups.c.topic,
            articles.c.title,
            articles.c.news_source,
            articles.c.uri,
            articles.c.publication_date,
            monitored_keywords.c.keyword.label("matched_keyword"),
            keyword_alerts.c.detected_at,
            keyword_alerts.c.is_read
        ).select_from(
            keyword_alerts.join(
                monitored_keywords,
                keyword_alerts.c.keyword_id == monitored_keywords.c.id
            ).join(
                keyword_groups,
                monitored_keywords.c.group_id == keyword_groups.c.id
            ).join(
                articles,
                keyword_alerts.c.article_uri == articles.c.uri
            )
        ).where(
            keyword_groups.c.id == group_id,
            keyword_groups.c.topic == topic
        ).order_by(
            keyword_alerts.c.detected_at.desc()
        )

        return self._execute_with_rollback(statement).mappings().fetchall()

    def save_keyword_alert(self, article_data):
        is_keyword_alert_exists = self._execute_with_rollback(select(keyword_alert_articles).where(keyword_alert_articles.c.url == article_data['url'])).fetchone()
        if not is_keyword_alert_exists:
            statement = insert(keyword_alert_articles).values(
                url = article_data['url'],
                title = article_data['title'],
                summary = article_data['summary'],
                source = article_data['source'],
                topic = article_data['topic'],
                keywords = ','.join(article_data['matched_keywords'])
            )
            self._execute_with_rollback(statement)
            self.connection.commit()

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

        return self._execute_with_rollback(statement).mappings().fetchall()

    def get_alerts_by_group_id_from_old_table_structure(self, status, show_read, group_id, page_size, offset):
        statement = select(
            keyword_alerts.c.id,
            keyword_alerts.c.article_uri,
            keyword_alerts.c.keyword_id,
            monitored_keywords.c.keyword.label("matched_keyword"),
            keyword_alerts.c.is_read,
            keyword_alerts.c.detected_at,
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
            keyword_alerts.join(
                articles,
                keyword_alerts.c.article_uri == articles.c.uri
            ).join(
                monitored_keywords,
                keyword_alerts.c.keyword_id == monitored_keywords.c.id
            )
        ).where(
            monitored_keywords.c.group_id == group_id
        ).order_by(
            keyword_alerts.c.detected_at.desc()
        )

        # Add read filter condition
        if not show_read:
            statement = statement.where(
                keyword_alerts.c.is_read == 0
            )

        # Add status filter condition
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
        
        # Add pagination
        statement = statement.limit(page_size).offset(offset)

        return self._execute_with_rollback(statement).mappings().fetchall()

    def count_unread_articles_by_group_id_from_new_table_structure(self, group_id):
        statement = select(
            func.count(keyword_article_matches.c.id)
        ).select_from(
            keyword_article_matches
        ).where(
            keyword_article_matches.c.group_id == group_id,
            keyword_article_matches.c.is_read == 0
        )
        
        return self._execute_with_rollback(statement).scalar()

    def count_unread_articles_by_group_id_from_old_table_structure(self, group_id):
        statement = select(
            func.count(keyword_alerts.c.id)
        ).select_from(
            keyword_alerts
        ).join(
            monitored_keywords,
            keyword_alerts.c.keyword_id == monitored_keywords.c.id
        ).where(
            monitored_keywords.c.group_id == group_id,
            keyword_alerts.c.is_read == 0
        )
        
        return self._execute_with_rollback(statement).scalar()

    def count_total_articles_by_group_id_from_new_table_structure(self, group_id, status='all'):
        statement = select(
            func.count(keyword_article_matches.c.id)
        ).select_from(
            keyword_article_matches.join(
                articles,
                keyword_article_matches.c.article_uri == articles.c.uri
            )
        ).where(
            keyword_article_matches.c.group_id == group_id
        )

        # Add status filter condition
        if status == "new":
            statement = statement.where(
                or_(
                    articles.c.category.is_(None),
                    articles.c.category == ''
                )
            )
        elif status == "added":
            statement = statement.where(
                and_(
                    articles.c.category.is_not(None),
                    articles.c.category != ''
                )
            )

        return self._execute_with_rollback(statement).scalar()

    def count_total_articles_by_group_id_from_old_table_structure(self, group_id, status='all'):
        statement = select(
            func.count(keyword_alerts.c.id)
        ).select_from(
            keyword_alerts.join(
                monitored_keywords,
                keyword_alerts.c.keyword_id == monitored_keywords.c.id
            ).join(
                articles,
                keyword_alerts.c.article_uri == articles.c.uri
            )
        ).where(
            monitored_keywords.c.group_id == group_id
        )

        # Add status filter condition (matching get_alerts_by_group_id_from_old_table_structure)
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

        return self._execute_with_rollback(statement).scalar()

    def update_media_bias(self, source):
        statement = update(mediabias).where(mediabias.c.source == source).values(enabled = 1)
        self._execute_with_rollback(statement)
        self.connection.commit()

    def get_group_name(self, group_id):
        statement = select(
            keyword_groups.c.name
        ).where(
            keyword_groups.c.id == group_id
        )

        group_name = self._execute_with_rollback(statement).scalar()

        return group_name if group_name else "Unknown Group"

    def get_article_urls_from_news_search_results_by_topic(self, topic_name):
        # TODO: add news_search_results table to database_models.py file!!
        statement = select(
            news_search_results.c.article_uri
        ).where(
            news_search_results.c.topic == topic_name
        )

        return self._execute_with_rollback(statement).mappings().fetchall()

    def get_article_urls_from_paper_search_results_by_topic(self, topic_name):
        # TODO: add paper_search_results table to database_models.py file!!
        statement = select(
            paper_search_results.c.article_uri
        ).where(
            paper_search_results.c.topic == topic_name
        )

        return self._execute_with_rollback(statement).mappings().fetchall()

    def article_urls_by_topic(self, topic_name):
        statement = select(
            articles.c.uri
        ).where(
            articles.c.topic == topic_name
        )

        return self._execute_with_rollback(statement).mappings().fetchall()

    def delete_article_matches_by_url(self, url):
        statement = delete(
            keyword_article_matches
        ).where(
            keyword_article_matches.c.article_uri == url
        )
        result = self._execute_with_rollback(statement)
        self.connection.commit()

        return result.rowcount

    def delete_keyword_alerts_by_url(self, url):
        statement = delete(
            keyword_alerts
        ).where(
            keyword_alerts.c.article_uri == url
        )
        result = self._execute_with_rollback(statement)
        self.connection.commit()

        return result.rowcount

    def delete_news_search_results_by_topic(self, topic_name):
        # Check if table exists before trying to delete
        if news_search_results is None:
            return 0

        statement = delete(
            news_search_results
        ).where(
            news_search_results.c.topic == topic_name
        )
        result = self._execute_with_rollback(statement)
        self.connection.commit()
        return result.rowcount

    def delete_paper_search_results_by_topic(self, topic_name):
        # Check if table exists before trying to delete
        if paper_search_results is None:
            return 0

        statement = delete(
            paper_search_results
        ).where(
            paper_search_results.c.topic == topic_name
        )
        result = self._execute_with_rollback(statement)
        self.connection.commit()
        return result.rowcount

    def delete_article_by_url(self, url):
        statement = delete(
            articles
        ).where(
            articles.c.uri == url
        )
        result = self._execute_with_rollback(statement)
        self.connection.commit()

        return result.rowcount

    def check_if_keyword_groups_table_exists(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            return cursor.fetchone()

    def get_all_topics_referenced_in_keyword_groups(self):
        statement = select(
            keyword_groups.c.topic
        ).distinct()
        topics = self._execute_with_rollback(statement).mappings().fetchall()

        return [row[0] for row in topics]

    def check_if_articles_table_exists(self):
        inspector = inspect(self.connection)
        return inspector.has_table('articles')

    def get_urls_and_topics_from_articles(self):
        statement = select(
            articles.c.uri,
            articles.c.topic
        ).where(
            articles.c.topic.isnot(None),
            articles.c.topic != ''
        )

        return self._execute_with_rollback(statement).mappings().fetchall()

    def check_if_news_search_results_table_exists(self):
        inspector = inspect(self.connection)
        return inspector.has_table('news_search_results')

    def get_urls_and_topics_from_news_search_results(self):
        statement = select(
            news_search_results.c.article_uri,
            news_search_results.c.topic
        ).group_by(
            news_search_results.c.article_uri,
            news_search_results.c.topic
        )

        return self._execute_with_rollback(statement).mappings().fetchall()

    def get_urls_and_topics_from_paper_search_results(self):
        statement = select(
            paper_search_results.c.article_uri,
            paper_search_results.c.topic
        ).group_by(
            paper_search_results.c.article_uri,
            paper_search_results.c.topic
        )

        return self._execute_with_rollback(statement).mappings().fetchall()

    def check_if_articles_table_has_topic_column(self):
        statement = select(articles)
        columns = self._execute_with_rollback(statement).mappings().fetchone().keys()

        return 'topic' in columns

    def check_if_paper_search_results_table_exists(self):
        inspector = inspect(self.connection)
        return inspector.has_table('paper_search_results')

    def get_orphaned_urls_from_news_results_and_or_paper_results(self, has_news_results, has_paper_results):
        statement = select(
            articles.c.uri
        )

        if has_news_results:
            news_exists = exists(
                select(news_search_results.c.article_uri).where(news_search_results.c.article_uri == articles.c.uri)
            )
            statement = statement.where(
                not_(news_exists)
            )

        if has_paper_results:
            paper_exists = exists(
                select(paper_search_results).where(paper_search_results.c.article_uri == articles.c.uri)
            )
            statement = statement.where(
                not_(paper_exists)
            )
        
        result = self._execute_with_rollback(statement).mappings().fetchall()

        return [row[0] for row in result]

    def delete_keyword_article_matches_from_new_table_structure_by_url(self, url):
        statement = delete(
            keyword_article_matches
        ).where(
            keyword_article_matches.c.article_uri == url
        )
        result = self._execute_with_rollback(statement)
        self.connection.commit()

        return result.rowcount

    def delete_keyword_article_matches_from_old_table_structure_by_url(self, url):
        statement = delete(
            keyword_alerts
        ).where(
            keyword_alerts.c.article_uri == url
        )
        result = self._execute_with_rollback(statement)
        self.connection.commit()

        return result.rowcount

    def delete_news_search_results_by_article_urls(self, placeholders, batch):
        statement = delete(
            news_search_results
        ).where(
            news_search_results.c.article_uri.in_(batch)
        )
        self._execute_with_rollback(statement)
        self.connection.commit()

    def delete_paper_search_results_by_article_urls(self, placeholders, batch):
        statement = delete(
            paper_search_results
        ).where(
            paper_search_results.c.article_uri.in_(batch)
        )
        self._execute_with_rollback(statement)
        self.connection.commit()

    def delete_articles_by_article_urls(self, placeholders, batch):
        statement = delete(
            articles
        ).where(
            articles.c.uri.in_(batch)
        )
        result = self._execute_with_rollback(statement)
        self.connection.commit()

        return result.rowcount

    def get_monitor_settings(self):
        statement = select(
            keyword_monitor_settings.c.check_interval,
            keyword_monitor_settings.c.interval_unit,
            keyword_monitor_settings.c.is_enabled,
            keyword_monitor_settings.c.search_date_range,
            keyword_monitor_settings.c.daily_request_limit
        ).where(
            keyword_monitor_settings.c.id == 1
        )

        return self._execute_with_rollback(statement).fetchone()

    def get_request_count_for_today(self):
        statement = select(
            keyword_monitor_status.c.requests_today,
            keyword_monitor_status.c.last_reset_date
        ).where(
            keyword_monitor_status.c.id == 1
        )

        return self._execute_with_rollback(statement).fetchone()

    def get_articles_by_url(self, url):
        statement = select(
            articles
        ).where(
            articles.c.uri == url
        )

        return self._execute_with_rollback(statement).mappings().fetchone()

    def get_raw_articles_markdown_by_url(self, url):
        statement = select(
            raw_articles.c.raw_markdown
        ).where(
            raw_articles.c.uri == url
        )

        return self._execute_with_rollback(statement).mappings().fetchone()

    def get_podcasts_for_newsletter_inclusion(self, column_names):
        # Build a query that works with the available columns
        # Base columns we need
        select_columns = ["id", "title", "created_at"]
        if "audio_url" in column_names:
            select_columns.append("audio_url")
        if "topic" in column_names:
            select_columns.append("topic")

        # Execute query to get recent podcasts
        statement = select(*select_columns).select_from(podcasts).order_by(podcasts.c.created_at.desc()).limit(20)

        podcasts = self._execute_with_rollback(statement).mappings().fetchall()

        # Format results
        result = []
        for podcast in podcasts:
            podcast_dict = {}
            for i, col in enumerate(select_columns):
                podcast_dict[col] = podcast[i]
            result.append(podcast_dict)

        return result

    def generate_tts_podcast(self, params):
        statement = insert(podcasts).values(
            id=params[0],
            title=params[1],
            status='processing',
            created_at=func.current_timestamp(),
            transcript=params[2],
            metadata=params[3]
        )
        self._execute_with_rollback(statement)
        self.connection.commit()

    def mark_podcast_generation_as_complete(self, params):
        statement = update(podcasts).where(podcasts.c.id == params[2]).values(
            status='completed',
            audio_url=params[0],
            completed_at=func.current_timestamp(),
            error=None,
            metadata=params[1]
        )
        self._execute_with_rollback(statement)
        self.connection.commit()

    def log_error_generating_podcast(self, params):
        statement = update(podcasts).where(podcasts.c.id == params[1]).values(
            status='failed',
            error=params[0],
            completed_at=func.current_timestamp()
        )
        self._execute_with_rollback(statement)
        self.connection.commit()

    def test_data_select(self):
        """Test database connection - works with both SQLite and PostgreSQL"""
        from sqlalchemy import text
        self._execute_with_rollback(text("SELECT 1"))

    def get_keyword_monitor_is_enabled_and_daily_request_limit(self):
        statement = select(
            keyword_monitor_settings.c.is_enabled,
            keyword_monitor_settings.c.daily_request_limit
        ).where(
            keyword_monitor_settings.c.id == 1
        )

        return self._execute_with_rollback(statement).fetchone()

    def get_topic_statistics(self):
        last_date = func.max(func.coalesce(articles.c.submission_date, articles.c.publication_date))

        stmt = (
            select(
                articles.c.topic,
                func.count().label("article_count"),
                last_date.label("last_article_date"),
            )
            .where(
                articles.c.topic.isnot(None),
                articles.c.topic != ""
            )
            .group_by(articles.c.topic)
            .order_by(
                case((last_date.is_(None), 1), else_=0),
                last_date.desc()
            )
        )

        result = self._execute_with_rollback(stmt).mappings().fetchall()

        # Return mapping objects directly so callers can access by column name
        return result

    def get_last_check_time_using_timezone_format(self):
        from datetime import datetime, timezone
        statement = select(keyword_monitor_status.c.last_check_time).where(keyword_monitor_status.c.id == 1)

        result = self._execute_with_rollback(statement).mappings().fetchone()

        if not result or not result['last_check_time']:
            return None

        last_check = result['last_check_time']

        # Handle both datetime objects and string timestamps
        if isinstance(last_check, str):
            # Already a string, parse it first if needed
            try:
                dt = datetime.fromisoformat(last_check.replace('Z', '+00:00'))
                return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            except:
                # If it's already in the right format, return as-is
                return last_check
        else:
            # It's a datetime object - ensure it's timezone-aware
            if last_check.tzinfo is None:
                last_check = last_check.replace(tzinfo=timezone.utc)
            return last_check.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    def get_podcast_transcript(self, podcast_id):
        statement = select(
            podcasts.c.title,
            podcasts.c.transcript,
            podcasts.c.metadata
        ).where(
            podcasts.c.id == podcast_id
        )

        return self._execute_with_rollback(statement).fetchone()

    def get_all_podcasts(self):
        statement = select(
            podcasts.c.id,
            podcasts.c.title,
            podcasts.c.status,
            podcasts.c.audio_url,
            podcasts.c.created_at,
            podcasts.c.completed_at,
            podcasts.c.error,
            podcasts.c.transcript,
            podcasts.c.metadata
        ).order_by(
            podcasts.c.created_at.desc()
        )

        return self._execute_with_rollback(statement).mappings().fetchall()

    def get_podcast_generation_status(self, podcast_id):
        statement = select(
            podcasts.c.id,
            podcasts.c.title,
            podcasts.c.status,
            podcasts.c.audio_url,
            podcasts.c.created_at,
            podcasts.c.completed_at,
            podcasts.c.error,
            podcasts.c.transcript,
            podcasts.c.metadata
        ).where(
            podcasts.c.id == podcast_id
        )

        return self._execute_with_rollback(statement).fetchone()

    def get_podcast_audio_file(self, podcast_id):
        statement = select(
            podcasts.c.audio_url
        ).where(
            podcasts.c.id == podcast_id
        )

        return self._execute_with_rollback(statement).fetchone()

    def delete_podcast(self, podcast_id):
        statement = delete(
            podcasts
        ).where(
            podcasts.c.id == podcast_id
        )
        self._execute_with_rollback(statement)
        self.connection.commit()

    def search_for_articles_based_on_query_date_range_and_topic(self, query, topic, start_date, end_date, limit):
        statement = select(articles)

        if query:
            statement = statement.where(
                or_(
                    articles.c.title.ilike(f"%{query}%"),
                    articles.c.summary.ilike(f"%{query}%")
                )
            )
        if topic:
            statement = statement.where(
                articles.c.topic == topic
            )
        if start_date:
            statement = statement.where(
                articles.c.publication_date >= start_date
            )
        if end_date:
            statement = statement.where(
                articles.c.publication_date <= end_date
            )
        statement = statement.order_by(
            articles.c.publication_date.desc()
        ).limit(limit)

        return self._execute_with_rollback(statement).mappings().fetchall()

    def update_article_by_url(self, params):
        statement = update(articles).where(articles.c.uri == params[6]).values(
            topic_alignment_score = params[0],
            keyword_relevance_score = params[1],
            confidence_score = params[2],
            overall_match_explanation = params[3],
            extracted_article_topics = params[4],
            extracted_article_keywords = params[5]
        )
        result = self._execute_with_rollback(statement)
        self.connection.commit()

        return result.rowcount

    def upsert_article(self, article_data: dict):
        """
        Upsert article using SQLAlchemy (works with both SQLite and PostgreSQL).
        Handles both inserts and updates based on URI.

        Args:
            article_data: Dictionary containing article fields

        Returns:
            Dictionary with success status and URI
        """
        try:
            # Validate topic exists in config.json
            topic = article_data.get('topic')
            if topic:
                from app.config.config import validate_topic_exists
                if not validate_topic_exists(topic):
                    raise ValueError(f"Invalid topic '{topic}'. Topic must be defined in config.json before use.")

            # Convert tags list to string if necessary
            if 'tags' in article_data and isinstance(article_data['tags'], list):
                article_data['tags'] = ','.join(article_data['tags'])

            # Check if article already exists
            uri = article_data.get('uri')
            if not uri:
                raise ValueError("Article URI is required")

            existing = self._execute_with_rollback(
                select(articles.c.uri).where(articles.c.uri == uri)
            ).fetchone()

            # Define all possible article fields
            valid_fields = [
                'uri', 'title', 'news_source', 'summary', 'sentiment',
                'time_to_impact', 'category', 'future_signal',
                'future_signal_explanation', 'publication_date',
                'submission_date', 'topic', 'sentiment_explanation',
                'time_to_impact_explanation', 'tags', 'driver_type',
                'driver_type_explanation', 'analyzed',
                'bias', 'factual_reporting', 'mbfc_credibility_rating',
                'bias_source', 'bias_country', 'press_freedom',
                'media_type', 'popularity',
                'topic_alignment_score', 'keyword_relevance_score',
                'confidence_score', 'overall_match_explanation',
                'extracted_article_topics', 'extracted_article_keywords',
                'ingest_status', 'auto_ingested'
            ]

            # Filter to only include fields that exist in article_data
            filtered_data = {k: v for k, v in article_data.items() if k in valid_fields}

            if existing:
                # Update existing article (exclude uri from values)
                update_data = {k: v for k, v in filtered_data.items() if k != 'uri'}
                statement = update(articles).where(articles.c.uri == uri).values(**update_data)
                self._execute_with_rollback(statement)
            else:
                # Insert new article
                statement = insert(articles).values(**filtered_data)
                self._execute_with_rollback(statement)

            self.connection.commit()
            return {"success": True, "uri": uri}

        except Exception as e:
            self.connection.rollback()
            self.logger.error(f"Error in upsert_article: {str(e)}")
            raise

    def enable_or_disable_auto_ingest(self, enabled):
        statement = update(keyword_monitor_settings).where(keyword_monitor_settings.c.id == 1).values(
            auto_ingest_enabled = enabled
        )
        self._execute_with_rollback(statement)
        self.connection.commit()

    def get_auto_ingest_settings(self):
        statement = select(
            keyword_monitor_settings.c.auto_ingest_enabled,
            keyword_monitor_settings.c.min_relevance_threshold,
            keyword_monitor_settings.c.quality_control_enabled,
            keyword_monitor_settings.c.auto_save_approved_only,
            keyword_monitor_settings.c.default_llm_model,
            keyword_monitor_settings.c.llm_temperature,
            keyword_monitor_settings.c.llm_max_tokens
        ).where(keyword_monitor_settings.c.id == 1)

        return self._execute_with_rollback(statement).fetchone()

    def get_processing_statistics(self):
        stmt = (
            select(
                func.count().label("total_auto_ingested"),
                func.count(
                    case((articles.c.ingest_status == "approved", 1))
                ).label("approved_count"),
                func.count(
                    case((articles.c.ingest_status == "failed", 1))
                ).label("failed_count"),
                func.avg(articles.c.quality_score).label("avg_quality_score"),
            )
            .where(articles.c.auto_ingested == True)
        )

        return self._execute_with_rollback(stmt).fetchone()

    def stamp_keyword_monitor_status_table_with_todays_date(self, params):
        # check if the keyword_monitor_status table has a row with id 1
        statement = select(keyword_monitor_status).where(keyword_monitor_status.c.id == 1)
        result = self._execute_with_rollback(statement).fetchone()

        if result:
            update_statement = update(keyword_monitor_status).where(keyword_monitor_status.c.id == 1).values(
                requests_today = params[0],
                last_check_time = func.current_timestamp(),
                last_reset_date = params[1]
            )
            self._execute_with_rollback(update_statement)
            self.connection.commit()
        else:
            insert_statement = insert(keyword_monitor_status).values(
                id = 1,
                requests_today = params[0],
                last_check_time = func.current_timestamp(),
                last_reset_date = params[1]
            )
            self._execute_with_rollback(insert_statement)
            self.connection.commit()

    def get_keyword_monitor_status_daily_request_limit(self):
        statement = select(keyword_monitor_settings.c.daily_request_limit).where(keyword_monitor_settings.c.id == 1)
        return self._execute_with_rollback(statement).fetchone()

    #### AUTOMATED INGEST SERVICE ####

    #### MEDIA BIAS ####

    def check_if_media_bias_has_updated_at_column(self):
        return [column.name for column in mediabias.columns]

    def insert_media_bias(self, params):
        # check if the source already exists in the mediabias table
        statement = select(mediabias).where(mediabias.c.source == params[0])
        result = self._execute_with_rollback(statement).fetchone()
        if result:
            statement = update(mediabias).where(mediabias.c.source == params[0]).values(
                country = params[1],
                bias = params[2],
                factual_reporting = params[3],
                press_freedom = params[4],
                media_type = params[5],
                popularity = params[6],
                mbfc_credibility_rating = params[7],
                updated_at = func.current_timestamp(),
                enabled = params[8]
            )
            result = self._execute_with_rollback(statement)
            self.connection.commit()
            return result.rowcount
        else:
            statement = insert(mediabias).values(
                source = params[0],
                country = params[1],
                bias = params[2],
                factual_reporting = params[3],
                press_freedom = params[4],
                media_type = params[5],
                popularity = params[6],
                mbfc_credibility_rating = params[7],
                updated_at = func.current_timestamp(),
                enabled = 1
            )
            result = self._execute_with_rollback(statement)
            self.connection.commit()
            return result.inserted_primary_key[0]

    def update_media_bias_source(self, params):
        statement = update(mediabias).where(mediabias.c.id == params[9]).values(
            source = params[0],
            country = params[1],
            bias = params[2],
            factual_reporting = params[3],
            press_freedom = params[4],
            media_type = params[5],
            popularity = params[6],
            mbfc_credibility_rating = params[7],
            updated_at = func.current_timestamp(),
            enabled = params[8]
        )
        self._execute_with_rollback(statement)
        self.connection.commit()

    def drop_media_bias_table(self):
        mediabias.drop(self.connection, checkfirst=True)
        self.connection.commit()

    def update_media_bias_settings(self, file_path):
        statement = update(mediabias_settings).where(mediabias_settings.c.id == 1).values(
            enabled = 1,
            source_file = file_path,
            last_updated = func.current_timestamp()
        )
        self._execute_with_rollback(statement)
        self.connection.commit()

    def get_all_media_bias_sources(self):
        statement = select(
            mediabias.c.source,
            mediabias.c.country,
            mediabias.c.bias,
            mediabias.c.factual_reporting,
            mediabias.c.press_freedom,
            mediabias.c.media_type,
            mediabias.c.popularity,
            mediabias.c.mbfc_credibility_rating
        ).order_by(
            mediabias.c.source.asc()
        )
        return self._execute_with_rollback(statement).mappings().fetchall()

    def get_media_bias_status(self):
        statement = select(
            mediabias_settings.c.enabled,
            mediabias_settings.c.last_updated,
            mediabias_settings.c.source_file
        ).where(mediabias_settings.c.id == 1)

        return self._execute_with_rollback(statement).fetchone()

    def get_media_bias_source(self, source_id):
        statement = select(
            mediabias.c.id
        ).where(mediabias.c.id == source_id)

        return self._execute_with_rollback(statement).fetchone()

    def delete_media_bias_source(self, source_id):
        statement = delete(mediabias).where(mediabias.c.id == source_id)
        self._execute_with_rollback(statement)
        self.connection.commit()

    def get_total_media_bias_sources(self):
        statement = select(
            func.count()
        ).select_from(
            mediabias
        )
        return self._execute_with_rollback(statement).scalar()

    def enable_media_bias_sources(self, enabled):
        statement = update(mediabias_settings).where(mediabias_settings.c.id == 1).values(
            enabled = 1 if enabled else 0,
            last_updated = func.current_timestamp()
        )
        self._execute_with_rollback(statement)
        # NOTE: commit is handled by _execute_with_rollback

    def update_media_bias_last_updated(self):
        statement = update(mediabias_settings).where(mediabias_settings.c.id == 1).values(
            last_updated = func.current_timestamp()
        )
        result = self._execute_with_rollback(statement)
        # NOTE: commit is handled by _execute_with_rollback

        return result.rowcount

    def reset_media_bias_sources(self):
        # delete all media bias data
        statement = delete(mediabias)
        self._execute_with_rollback(statement)

        # Reset settings but keep enabled state
        statement = update(mediabias_settings).where(mediabias_settings.c.id == 1).values(
            last_updated = None,
            source_file = None
        )
        self._execute_with_rollback(statement)
        self.connection.commit()

    def enable_media_source(self, source):
        statement = update(mediabias).where(mediabias.c.source == source).values(
            enabled = 1
        )
        self._execute_with_rollback(statement)
        self.connection.commit()

    def search_media_bias_sources(self, query, bias_filter, factual_filter, country_filter, page, per_page):
        # Build base query
        base_stmt = select(mediabias)

        # Apply filters
        if query:
            base_stmt = base_stmt.where(mediabias.c.source.ilike(f"%{query}%"))
        if bias_filter:
            base_stmt = base_stmt.where(mediabias.c.bias.ilike(f"%{bias_filter}%"))
        if factual_filter:
            base_stmt = base_stmt.where(mediabias.c.factual_reporting.ilike(f"%{factual_filter}%"))
        if country_filter:
            base_stmt = base_stmt.where(mediabias.c.country.ilike(f"%{country_filter}%"))

        # Get total count
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_count = self._execute_with_rollback(count_stmt).scalar()

        # Add pagination
        offset_value = (page - 1) * per_page
        paginated_stmt = (
            base_stmt
            .order_by(asc(mediabias.c.source))
            .limit(per_page)
            .offset(offset_value)
        )

        return total_count, self._execute_with_rollback(paginated_stmt).mappings().fetchall()

    def delete_media_bias_source(self, source_id):
        statement = delete(mediabias).where(mediabias.c.id == source_id)
        self._execute_with_rollback(statement)
        self.connection.commit()

    def get_media_bias_source_by_id(self, source_id):
        statement = select(
            mediabias.c.id,
            mediabias.c.source,
            mediabias.c.country,
            mediabias.c.bias,
            mediabias.c.factual_reporting,
            mediabias.c.press_freedom,
            mediabias.c.media_type,
            mediabias.c.popularity,
            mediabias.c.mbfc_credibility_rating
        ).where(mediabias.c.id == source_id)

        return self._execute_with_rollback(statement).mappings().fetchone()

    def get_media_bias_filter_options(self):
        # Get unique biases
        biases_statement = select(
            mediabias.c.bias
        ).where(
            mediabias.c.bias.isnot(None),
            mediabias.c.bias != ''
        ).distinct()

        biases = [row[0] for row in self._execute_with_rollback(biases_statement).fetchall()]

        # Get unique factual reporting levels
        factual_reporting_statement = select(
            mediabias.c.factual_reporting
        ).where(
            mediabias.c.factual_reporting.isnot(None),
            mediabias.c.factual_reporting != ''
        ).distinct()

        factual_levels = [row[0] for row in self._execute_with_rollback(factual_reporting_statement).fetchall()]

        # Get unique countries
        countries_statement = select(
            mediabias.c.country
        ).where(
            mediabias.c.country.isnot(None),
            mediabias.c.country != ''
        ).distinct()

        countries = [row[0] for row in self._execute_with_rollback(countries_statement).fetchall()]

        return biases, factual_levels, countries

    def load_media_bias_sources_from_database(self):
        return self._execute_with_rollback(select(mediabias)).mappings().fetchall()

    #### ARTICLE SEARCH QUERIES ####
    def search_articles(
        self,
        topic=None,
        category=None,
        future_signal=None,
        sentiment=None,
        tags=None,
        keyword=None,
        pub_date_start=None,
        pub_date_end=None,
        page=1,
        per_page=10,
        date_type='publication',
        date_field=None,
        require_category=False
    ):
        """Search articles with filters including topic - SQLAlchemy version."""
        from typing import Tuple, List, Dict, Optional

        # Use the appropriate date field based on date_type
        date_field_to_use = articles.c.publication_date if date_type == 'publication' else articles.c.submission_date
        # Override with date_field if explicitly provided
        if date_field:
            date_field_to_use = getattr(articles.c, date_field)

        # Build WHERE conditions
        conditions = []

        # Add topic filter
        if topic:
            conditions.append(articles.c.topic == topic)

        if category:
            conditions.append(articles.c.category.in_(category))

        if future_signal:
            conditions.append(articles.c.future_signal.in_(future_signal))

        if sentiment:
            conditions.append(articles.c.sentiment.in_(sentiment))

        if tags:
            tag_conditions = []
            for tag in tags:
                tag_conditions.append(articles.c.tags.like(f"%{tag}%"))
            if tag_conditions:
                conditions.append(or_(*tag_conditions))

        if keyword:
            keyword_conditions = [
                articles.c.title.like(f"%{keyword}%"),
                articles.c.summary.like(f"%{keyword}%"),
                articles.c.category.like(f"%{keyword}%"),
                articles.c.future_signal.like(f"%{keyword}%"),
                articles.c.sentiment.like(f"%{keyword}%"),
                articles.c.tags.like(f"%{keyword}%")
            ]
            conditions.append(or_(*keyword_conditions))

        if pub_date_start:
            conditions.append(date_field_to_use >= pub_date_start)

        if pub_date_end:
            conditions.append(date_field_to_use <= pub_date_end)

        # Add filter for requiring a category if specified
        if require_category:
            conditions.append(and_(
                articles.c.category.isnot(None),
                articles.c.category != ''
            ))

        # Build the WHERE clause
        where_clause = and_(*conditions) if conditions else literal(True)

        # Count total results
        count_query = select(func.count()).select_from(articles).where(where_clause)
        total_count = self._execute_with_rollback(count_query).scalar()

        # Get paginated results
        offset = (page - 1) * per_page
        query = select(articles).where(where_clause).order_by(
            desc(articles.c.submission_date)
        ).limit(per_page).offset(offset)

        result = self._execute_with_rollback(query).mappings().fetchall()
        articles_list = [dict(row) for row in result]

        return articles_list, total_count

    def get_recent_articles_by_topic(self, topic_name, limit=10, start_date=None, end_date=None):
        """Fetch recent articles for a topic - SQLAlchemy version."""
        from sqlalchemy import case, cast, Date
        import logging
        logger = logging.getLogger(__name__)

        logger.info(f"Database: Fetching {limit} recent articles for topic {topic_name} (date range: {start_date} to {end_date})")

        # Build WHERE conditions
        conditions = [articles.c.topic == topic_name]

        # COALESCE for date ordering
        coalesce_date = func.coalesce(articles.c.submission_date, articles.c.publication_date)

        # Cast to DATE for proper comparison (handles timestamps vs date strings)
        if start_date:
            conditions.append(cast(coalesce_date, Date) >= start_date)
        if end_date:
            conditions.append(cast(coalesce_date, Date) <= end_date)

        # Build query
        # Note: PostgreSQL doesn't have rowid, so we only order by date
        query = select(articles).where(
            and_(*conditions)
        ).order_by(
            desc(coalesce_date)
        ).limit(limit)

        logger.debug(f"Executing query: {query}")
        result = self._execute_with_rollback(query).mappings().fetchall()
        articles_list = [dict(row) for row in result]
        logger.info(f"Found {len(articles_list)} articles in database")

        # Convert tags string back to list
        for article in articles_list:
            if article['tags']:
                article['tags'] = article['tags'].split(',')
            else:
                article['tags'] = []

        return articles_list

    #### NEWS FEED SERVICE QUERIES ####
    def get_news_feed_articles_for_date_range(
        self,
        date_condition_type: str,
        date_params: list,
        max_articles: int,
        topic: str = None,
        bias_filter: str = None,
        offset: int = 0,
        limit: int = None
    ):
        """
        Get articles for news feed with complex filtering and quality-based ordering.

        Args:
            date_condition_type: Type of date filter ('custom', '24h', '7d', '30d', '3m', '1y', 'all')
            date_params: List of date parameters for the WHERE clause
            max_articles: Maximum number of articles to return (deprecated, use limit instead)
            topic: Optional topic filter (matches topic field or title/summary LIKE pattern)
            bias_filter: Optional bias filter ('no_bias' or specific bias value)
            offset: Number of articles to skip (for pagination)
            limit: Maximum number of articles to return (overrides max_articles if provided)

        Returns:
            List of article dictionaries
        """
        from datetime import datetime, timedelta

        # Build date condition based on type
        now = datetime.now()

        if date_condition_type == 'custom' and len(date_params) > 0:
            # Custom date - use DATE(publication_date) = ?
            where_conditions = [
                func.date(articles.c.publication_date) == date_params[0]
            ]
        elif date_condition_type == 'all':
            # All articles with non-null publication_date
            where_conditions = [
                articles.c.publication_date.isnot(None)
            ]
        else:
            # Range queries (24h, 7d, 30d, 3m, 1y)
            if len(date_params) >= 2:
                where_conditions = [
                    and_(
                        articles.c.publication_date >= date_params[0],
                        articles.c.publication_date <= date_params[1]
                    )
                ]
            else:
                # Default to last 24 hours if params missing
                start_date = now - timedelta(days=1)
                where_conditions = [
                    and_(
                        # NOTE: publication_date is TEXT, use strftime()
                        articles.c.publication_date >= start_date.strftime('%Y-%m-%d'),
                        articles.c.publication_date <= now.strftime('%Y-%m-%d %H:%M:%S')
                    )
                ]

        # Add required filters - only show enriched articles with metadata
        where_conditions.extend([
            articles.c.category.isnot(None),
            articles.c.sentiment.isnot(None)
        ])

        # Add bias filter if specified
        if bias_filter:
            if bias_filter.lower() == 'no_bias':
                where_conditions.append(articles.c.bias.is_(None))
            else:
                where_conditions.append(articles.c.bias == bias_filter)

        # Add topic filter if specified
        if topic:
            topic_pattern = f"%{topic}%"
            where_conditions.append(
                or_(
                    articles.c.topic == topic,
                    articles.c.title.like(topic_pattern),
                    articles.c.summary.like(topic_pattern)
                )
            )

        # Add spam/promotional content filters
        where_conditions.extend([
            not_(articles.c.title.like('%Call@%')),
            not_(articles.c.title.like('%+91%')),
            not_(articles.c.title.like('%best%agency%')),
            not_(articles.c.title.like('%#1%')),
            not_(articles.c.summary.like('%Call@%')),
            not_(articles.c.summary.like('%phone%number%')),
            not_(articles.c.news_source.like('%medium.com/@%'))
        ])

        # Build quality-based ordering using CASE expressions
        # Note: mediabias table stores lowercase values ('high', 'very high', etc.)
        factual_reporting_order = case(
            (articles.c.factual_reporting == 'very high', 4),
            (articles.c.factual_reporting == 'high', 3),
            (articles.c.factual_reporting == 'mostly factual', 2),
            else_=1
        )

        news_source_order = case(
            (
                and_(
                    articles.c.news_source.like('%.com'),
                    not_(articles.c.news_source.like('%medium.com%'))
                ),
                2
            ),
            (
                or_(
                    articles.c.news_source.like('%reuters%'),
                    articles.c.news_source.like('%bloomberg%'),
                    articles.c.news_source.like('%techcrunch%')
                ),
                3
            ),
            else_=1
        )

        # Build the complete query
        statement = select(
            articles.c.uri,
            articles.c.title,
            articles.c.summary,
            articles.c.news_source,
            articles.c.publication_date,
            articles.c.submission_date,
            articles.c.category,
            articles.c.topic,  # Add topic field for Auspex context
            articles.c.sentiment,
            articles.c.sentiment_explanation,
            articles.c.time_to_impact,
            articles.c.time_to_impact_explanation,
            articles.c.tags,
            articles.c.bias,
            articles.c.factual_reporting,
            articles.c.mbfc_credibility_rating,
            articles.c.bias_source,
            articles.c.bias_country,
            articles.c.press_freedom,
            articles.c.media_type,
            articles.c.popularity,
            articles.c.future_signal,
            articles.c.future_signal_explanation,
            articles.c.driver_type,
            articles.c.driver_type_explanation
        ).where(
            and_(*where_conditions)
        ).order_by(
            factual_reporting_order.desc(),
            news_source_order.desc(),
            articles.c.publication_date.desc()
        )

        # Apply pagination (use limit parameter if provided, otherwise max_articles)
        actual_limit = limit if limit is not None else max_articles
        statement = statement.limit(actual_limit).offset(offset)

        # Execute and return results
        results = self._execute_with_rollback(statement).mappings().fetchall()

        # Convert to list of dicts
        articles_list = []
        for row in results:
            article_dict = dict(row)
            articles_list.append(article_dict)

        return articles_list

    def get_news_feed_articles_count_for_date_range(
        self,
        date_condition_type: str,
        date_params: list,
        topic: str = None,
        bias_filter: str = None
    ) -> int:
        """
        Get count of articles for news feed with same filtering as get_news_feed_articles_for_date_range.

        Args:
            date_condition_type: Type of date filter ('custom', '24h', '7d', '30d', '3m', '1y', 'all')
            date_params: List of date parameters for the WHERE clause
            topic: Optional topic filter (matches topic field or title/summary LIKE pattern)
            bias_filter: Optional bias filter ('no_bias' or specific bias value)

        Returns:
            Integer count of matching articles
        """
        from datetime import datetime, timedelta

        # Build date condition based on type (same logic as article query)
        now = datetime.now()

        if date_condition_type == 'custom' and len(date_params) > 0:
            where_conditions = [
                func.date(articles.c.publication_date) == date_params[0]
            ]
        elif date_condition_type == 'all':
            where_conditions = [
                articles.c.publication_date.isnot(None)
            ]
        else:
            if len(date_params) >= 2:
                where_conditions = [
                    and_(
                        articles.c.publication_date >= date_params[0],
                        articles.c.publication_date <= date_params[1]
                    )
                ]
            else:
                start_date = now - timedelta(days=1)
                where_conditions = [
                    and_(
                        # NOTE: publication_date is TEXT, use strftime()
                        articles.c.publication_date >= start_date.strftime('%Y-%m-%d'),
                        articles.c.publication_date <= now.strftime('%Y-%m-%d %H:%M:%S')
                    )
                ]

        # Add required filters (same as article query)
        where_conditions.extend([
            articles.c.category.isnot(None),
            articles.c.sentiment.isnot(None)
        ])

        # Add spam/promotional content filters
        where_conditions.extend([
            not_(articles.c.title.like('%Call@%')),
            not_(articles.c.title.like('%+91%')),
            not_(articles.c.title.like('%best%agency%')),
            not_(articles.c.title.like('%#1%')),
            not_(articles.c.summary.like('%Call@%')),
            not_(articles.c.summary.like('%phone%number%')),
            not_(articles.c.news_source.like('%medium.com/@%'))
        ])

        # Add bias filter if specified
        if bias_filter:
            if bias_filter.lower() == 'no_bias':
                where_conditions.append(articles.c.bias.is_(None))
            else:
                where_conditions.append(articles.c.bias == bias_filter)

        # Add topic filter if specified
        if topic:
            topic_pattern = f"%{topic}%"
            where_conditions.append(
                or_(
                    articles.c.topic == topic,
                    articles.c.title.like(topic_pattern),
                    articles.c.summary.like(topic_pattern)
                )
            )

        # Build COUNT query
        statement = select(
            func.count()
        ).select_from(
            articles
        ).where(
            and_(*where_conditions)
        )

        # Execute and return scalar result
        result = self._execute_with_rollback(statement).scalar()
        return result if result else 0

    def get_articles_by_uris(self, uris: List[str]) -> List[Dict]:
        """
        Fetch articles directly by their URIs, regardless of date filters.
        Useful for retrieving starred articles that may have aged out of current date range.

        Args:
            uris: List of article URIs to fetch

        Returns:
            List of article dictionaries
        """
        if not uris:
            return []

        # Build query to fetch articles by URI
        statement = select(articles).where(
            articles.c.uri.in_(uris)
        )

        # Execute query
        result = self._execute_with_rollback(statement).mappings()
        articles_list = [dict(row) for row in result]

        self.logger.info(f"Fetched {len(articles_list)} articles by URI out of {len(uris)} requested")
        return articles_list

    def get_topic_articles_count(self, topic_name: str) -> int:
        """Get total count of articles for a specific topic.

        Args:
            topic_name: The topic to count articles for

        Returns:
            Integer count of articles for the topic
        """
        statement = select(
            func.count()
        ).select_from(
            articles
        ).where(
            articles.c.topic == topic_name
        )

        result = self._execute_with_rollback(statement).scalar()
        return result if result else 0

    def get_topic_articles_count_since(self, topic_name: str, since_datetime: str) -> int:
        """Get count of articles for a topic since a specific datetime.

        Args:
            topic_name: The topic to count articles for
            since_datetime: ISO format datetime string to count from

        Returns:
            Integer count of articles for the topic since the datetime
        """
        statement = select(
            func.count()
        ).select_from(
            articles
        ).where(
            and_(
                articles.c.topic == topic_name,
                articles.c.submission_date >= since_datetime
            )
        )

        result = self._execute_with_rollback(statement).scalar()
        return result if result else 0

    def get_dominant_news_source_for_topic(self, topic_name: str, since_datetime: str) -> Optional[str]:
        """Get the most frequent news source for a topic since a datetime.

        Args:
            topic_name: The topic to analyze
            since_datetime: ISO format datetime string to count from

        Returns:
            The most frequent news source name, or None if no results
        """
        statement = select(
            articles.c.news_source,
            func.count().label('count')
        ).select_from(
            articles
        ).where(
            and_(
                articles.c.topic == topic_name,
                articles.c.submission_date >= since_datetime,
                articles.c.news_source.isnot(None),
                articles.c.news_source != ''
            )
        ).group_by(
            articles.c.news_source
        ).order_by(
            text('count DESC')
        ).limit(1)

        result = self._execute_with_rollback(statement).mappings().fetchone()
        return result['news_source'] if result else None

    def get_most_frequent_time_to_impact_for_topic(self, topic_name: str, since_datetime: str) -> Optional[str]:
        """Get the most frequent time_to_impact value for a topic since a datetime.

        Args:
            topic_name: The topic to analyze
            since_datetime: ISO format datetime string to count from

        Returns:
            The most frequent time_to_impact value, or None if no results
        """
        statement = select(
            articles.c.time_to_impact,
            func.count().label('count')
        ).select_from(
            articles
        ).where(
            and_(
                articles.c.topic == topic_name,
                articles.c.submission_date >= since_datetime,
                articles.c.time_to_impact.isnot(None),
                articles.c.time_to_impact != ''
            )
        ).group_by(
            articles.c.time_to_impact
        ).order_by(
            text('count DESC')
        ).limit(1)

        result = self._execute_with_rollback(statement).mappings().fetchone()
        return result['time_to_impact'] if result else None

    # ============================================================
    # Signal Alerts Methods
    # ============================================================

    def get_signal_alerts(self, topic: str = None, instruction_id: int = None,
                         acknowledged: bool = None, limit: int = 100) -> List[Dict]:
        """Get signal alerts with optional filters.

        Args:
            topic: Filter by topic name
            instruction_id: Filter by instruction ID
            acknowledged: Filter by acknowledgment status (True/False/None for all)
            limit: Maximum number of alerts to return

        Returns:
            List of signal alert dictionaries with article details
        """
        from sqlalchemy import and_, or_

        # Build the base query with LEFT JOIN to articles
        query = """
        SELECT sa.id, sa.article_uri, sa.instruction_id, sa.instruction_name,
               sa.confidence, sa.threat_level, sa.summary, sa.detected_at,
               sa.is_acknowledged, sa.acknowledged_at,
               a.title as article_title, a.news_source as article_source,
               a.publication_date as article_publication_date
        FROM signal_alerts sa
        LEFT JOIN articles a ON sa.article_uri = a.uri
        WHERE 1=1
        """

        params = {}

        if instruction_id is not None:
            query += " AND sa.instruction_id = :instruction_id"
            params['instruction_id'] = instruction_id

        if acknowledged is not None:
            query += " AND sa.is_acknowledged = :acknowledged"
            params['acknowledged'] = acknowledged

        if topic:
            query += " AND (a.topic = :topic OR a.title LIKE :topic_pattern OR a.summary LIKE :topic_pattern)"
            params['topic'] = topic
            params['topic_pattern'] = f"%{topic}%"

        query += " ORDER BY sa.detected_at DESC LIMIT :limit"
        params['limit'] = limit

        try:
            result = self._execute_with_rollback(text(query), params)
            alerts = []
            for row in result.mappings():
                alerts.append({
                    'id': row['id'],
                    'article_uri': row['article_uri'],
                    'instruction_id': row['instruction_id'],
                    'instruction_name': row['instruction_name'],
                    'confidence': row['confidence'],
                    'threat_level': row['threat_level'],
                    'summary': row['summary'],
                    'detected_at': row['detected_at'],
                    'is_acknowledged': bool(row['is_acknowledged']),
                    'acknowledged_at': row['acknowledged_at'],
                    'article_title': row['article_title'],
                    'article_source': row['article_source'],
                    'article_publication_date': row['article_publication_date']
                })
            return alerts
        except Exception as e:
            self.logger.error(f"Error getting signal alerts: {e}")
            return []

    def acknowledge_signal_alert(self, alert_id: int) -> bool:
        """Mark a signal alert as acknowledged.

        Args:
            alert_id: ID of the alert to acknowledge

        Returns:
            True if successfully acknowledged, False otherwise
        """
        try:
            query = """
            UPDATE signal_alerts
            SET is_acknowledged = true, acknowledged_at = CURRENT_TIMESTAMP
            WHERE id = :alert_id
            """
            result = self._execute_with_rollback(text(query), {'alert_id': alert_id})
            self.connection.commit()
            return result.rowcount > 0
        except Exception as e:
            self.logger.error(f"Error acknowledging signal alert {alert_id}: {e}")
            return False

    def get_signal_instructions(self, topic: str = None, active_only: bool = True) -> List[Dict]:
        """Get signal instructions with optional filters.

        Args:
            topic: Filter by topic name (also matches NULL topics). Empty string treated as None.
            active_only: If True, only return active instructions; if False, return all

        Returns:
            List of signal instruction dictionaries
        """
        query = "SELECT * FROM signal_instructions WHERE 1=1"
        params = {}

        # Treat empty string as None (no topic filter)
        if topic is not None and topic != "":
            query += " AND (topic = :topic OR topic IS NULL)"
            params['topic'] = topic

        if active_only:
            query += " AND is_active = true"

        query += " ORDER BY updated_at DESC"

        try:
            result = self._execute_with_rollback(text(query), params)
            instructions = []
            for row in result.mappings():
                instructions.append({
                    'id': row['id'],
                    'name': row['name'],
                    'description': row['description'],
                    'instruction': row['instruction'],
                    'topic': row['topic'],
                    'is_active': bool(row['is_active']),
                    'created_at': row['created_at'],
                    'updated_at': row['updated_at']
                })
            return instructions
        except Exception as e:
            self.logger.error(f"Error getting signal instructions: {e}")
            return []

    def save_signal_instruction(self, name: str, description: str, instruction: str,
                               topic: str = None, is_active: bool = True) -> bool:
        """Save a custom signal instruction for threat hunting.

        Args:
            name: Unique name for the instruction
            description: Description of what the signal detects
            instruction: The instruction text for the AI
            topic: Optional topic to associate with
            is_active: Whether the instruction is active

        Returns:
            True if successfully saved, False otherwise
        """
        try:
            # PostgreSQL uses INSERT ... ON CONFLICT instead of INSERT OR REPLACE
            query = """
            INSERT INTO signal_instructions (name, description, instruction, topic, is_active, updated_at)
            VALUES (:name, :description, :instruction, :topic, :is_active, CURRENT_TIMESTAMP)
            ON CONFLICT (name) DO UPDATE SET
                description = :description,
                instruction = :instruction,
                topic = :topic,
                is_active = :is_active,
                updated_at = CURRENT_TIMESTAMP
            """
            self._execute_with_rollback(text(query), {
                'name': name,
                'description': description,
                'instruction': instruction,
                'topic': topic,
                'is_active': is_active
            })
            self.connection.commit()
            self.logger.info(f"Saved signal instruction: {name}")
            return True
        except Exception as e:
            self.logger.error(f"Error saving signal instruction: {e}")
            return False

    def delete_signal_instruction(self, instruction_id: int) -> bool:
        """Delete a signal instruction.

        Args:
            instruction_id: ID of the instruction to delete

        Returns:
            True if successfully deleted, False otherwise
        """
        try:
            query = "DELETE FROM signal_instructions WHERE id = :instruction_id"
            result = self._execute_with_rollback(text(query), {'instruction_id': instruction_id})
            self.connection.commit()
            deleted = result.rowcount > 0
            if deleted:
                self.logger.info(f"Deleted signal instruction ID: {instruction_id}")
            return deleted
        except Exception as e:
            self.logger.error(f"Error deleting signal instruction {instruction_id}: {e}")
            return False

    def save_signal_alert(self, article_uri: str, instruction_id: int,
                         instruction_name: str, confidence: float,
                         threat_level: str, summary: str) -> Optional[int]:
        """Save a signal alert.

        Args:
            article_uri: URI of the article
            instruction_id: ID of the signal instruction
            instruction_name: Name of the signal instruction
            confidence: Confidence score (0.0 to 1.0)
            threat_level: Threat level (e.g., 'low', 'medium', 'high', 'critical')
            summary: Summary of the alert

        Returns:
            ID of the created alert, or None if failed
        """
        try:
            query = """
            INSERT INTO signal_alerts
            (article_uri, instruction_id, instruction_name, confidence, threat_level, summary)
            VALUES (:article_uri, :instruction_id, :instruction_name, :confidence, :threat_level, :summary)
            ON CONFLICT (article_uri, instruction_id) DO UPDATE SET
                confidence = :confidence,
                threat_level = :threat_level,
                summary = :summary,
                detected_at = CURRENT_TIMESTAMP
            RETURNING id
            """
            result = self._execute_with_rollback(text(query), {
                'article_uri': article_uri,
                'instruction_id': instruction_id,
                'instruction_name': instruction_name,
                'confidence': confidence,
                'threat_level': threat_level,
                'summary': summary
            })
            self.connection.commit()
            row = result.fetchone()
            return row[0] if row else None
        except Exception as e:
            self.logger.error(f"Error saving signal alert: {e}")
            return None

    #### AUSPEX CHAT QUERIES ####
    def create_auspex_chat(self, topic: str, title: str = None, user_id: str = None, profile_id: int = None, metadata: dict = None) -> int:
        """Create a new Auspex chat session with optional organizational profile."""
        try:
            metadata_json = json.dumps(metadata) if metadata else None

            # Insert new chat session
            result = self._execute_with_rollback(
                insert(auspex_chats).values(
                    topic=topic,
                    title=title,
                    user_id=user_id,
                    profile_id=profile_id,
                    metadata=metadata_json
                )
            )
            self.connection.commit()

            # Get the inserted ID
            return result.inserted_primary_key[0]
        except Exception as e:
            self.logger.error(f"Error creating auspex chat: {e}")
            self.connection.rollback()
            raise

    def get_auspex_chat(self, chat_id: int):
        """Get an Auspex chat session by ID."""
        try:
            result = self._execute_with_rollback(
                select(auspex_chats).where(auspex_chats.c.id == chat_id)
            ).mappings().fetchone()

            if result:
                # Parse metadata if it exists
                chat_dict = dict(result)
                if chat_dict.get('metadata'):
                    try:
                        chat_dict['metadata'] = json.loads(chat_dict['metadata'])
                    except:
                        pass
                return chat_dict
            return None
        except Exception as e:
            self.logger.error(f"Error getting auspex chat: {e}")
            return None

    def get_auspex_chats(self, topic: str = None, user_id: str = None, limit: int = 50):
        """Get Auspex chat sessions with optional filters and message counts."""
        try:
            # Subquery to count messages per chat
            message_count_subquery = (
                select(
                    auspex_messages.c.chat_id,
                    func.count().label('message_count')
                )
                .group_by(auspex_messages.c.chat_id)
                .subquery()
            )

            # Main query with LEFT JOIN to get message counts
            query = (
                select(
                    auspex_chats,
                    func.coalesce(message_count_subquery.c.message_count, 0).label('message_count')
                )
                .outerjoin(
                    message_count_subquery,
                    auspex_chats.c.id == message_count_subquery.c.chat_id
                )
                .order_by(desc(auspex_chats.c.updated_at))
            )

            if topic:
                query = query.where(auspex_chats.c.topic == topic)
            if user_id:
                query = query.where(auspex_chats.c.user_id == user_id)

            query = query.limit(limit)

            results = self._execute_with_rollback(query).mappings().fetchall()

            # Parse metadata for each result
            chats = []
            for result in results:
                chat_dict = dict(result)
                if chat_dict.get('metadata'):
                    try:
                        chat_dict['metadata'] = json.loads(chat_dict['metadata'])
                    except:
                        pass
                chats.append(chat_dict)

            return chats
        except Exception as e:
            self.logger.error(f"Error getting auspex chats: {e}")
            return []

    def update_auspex_chat_profile(self, chat_id: int, profile_id: int) -> bool:
        """Update the profile_id for an Auspex chat session."""
        try:
            self._execute_with_rollback(
                update(auspex_chats)
                .where(auspex_chats.c.id == chat_id)
                .values(
                    profile_id=profile_id,
                    updated_at=func.now()
                )
            )
            self.connection.commit()
            return True
        except Exception as e:
            self.logger.error(f"Error updating auspex chat profile: {e}")
            self.connection.rollback()
            return False

    def delete_auspex_chat(self, chat_id: int) -> bool:
        """Delete an Auspex chat session and its messages."""
        try:
            self._execute_with_rollback(
                delete(auspex_chats).where(auspex_chats.c.id == chat_id)
            )
            self.connection.commit()
            return True
        except Exception as e:
            self.logger.error(f"Error deleting auspex chat: {e}")
            self.connection.rollback()
            return False

    def add_auspex_message(self, chat_id: int, role: str, content: str,
                          model_used: str = None, tokens_used: int = None,
                          metadata: dict = None) -> int:
        """Add a message to an Auspex chat session."""
        try:
            metadata_json = json.dumps(metadata) if metadata else None

            result = self._execute_with_rollback(
                insert(auspex_messages).values(
                    chat_id=chat_id,
                    role=role,
                    content=content,
                    model_used=model_used,
                    tokens_used=tokens_used,
                    metadata=metadata_json
                )
            )
            self.connection.commit()

            return result.inserted_primary_key[0]
        except Exception as e:
            self.logger.error(f"Error adding auspex message: {e}")
            self.connection.rollback()
            raise

    def get_auspex_messages(self, chat_id: int):
        """Get all messages for an Auspex chat session."""
        try:
            results = self._execute_with_rollback(
                select(auspex_messages)
                .where(auspex_messages.c.chat_id == chat_id)
                .order_by(auspex_messages.c.timestamp)
            ).mappings().fetchall()

            # Parse metadata for each message
            messages = []
            for result in results:
                msg_dict = dict(result)
                if msg_dict.get('metadata'):
                    try:
                        msg_dict['metadata'] = json.loads(msg_dict['metadata'])
                    except:
                        pass
                messages.append(msg_dict)

            return messages
        except Exception as e:
            self.logger.error(f"Error getting auspex messages: {e}")
            return []

    def get_auspex_prompt(self, name: str):
        """Get an Auspex prompt by name."""
        try:
            result = self._execute_with_rollback(
                select(auspex_prompts).where(auspex_prompts.c.name == name)
            ).mappings().fetchone()

            return dict(result) if result else None
        except Exception as e:
            self.logger.error(f"Error getting auspex prompt: {e}")
            return None

    def create_auspex_prompt(self, name: str, title: str, content: str,
                            description: str = None, is_default: bool = False,
                            user_created: str = None) -> int:
        """Create a new Auspex prompt."""
        try:
            result = self._execute_with_rollback(
                insert(auspex_prompts).values(
                    name=name,
                    title=title,
                    content=content,
                    description=description,
                    is_default=is_default,
                    user_created=user_created
                )
            )
            self.connection.commit()

            return result.inserted_primary_key[0]
        except Exception as e:
            self.logger.error(f"Error creating auspex prompt: {e}")
            self.connection.rollback()
            raise

    def update_auspex_prompt(self, name: str, title: str = None, content: str = None,
                            description: str = None) -> bool:
        """Update an Auspex prompt."""
        try:
            values = {'updated_at': func.now()}
            if title is not None:
                values['title'] = title
            if content is not None:
                values['content'] = content
            if description is not None:
                values['description'] = description

            self._execute_with_rollback(
                update(auspex_prompts)
                .where(auspex_prompts.c.name == name)
                .values(**values)
            )
            self.connection.commit()
            return True
        except Exception as e:
            self.logger.error(f"Error updating auspex prompt: {e}")
            self.connection.rollback()
            return False

    def delete_auspex_prompt(self, name: str) -> bool:
        """Delete an Auspex prompt."""
        try:
            self._execute_with_rollback(
                delete(auspex_prompts).where(auspex_prompts.c.name == name)
            )
            self.connection.commit()
            return True
        except Exception as e:
            self.logger.error(f"Error deleting auspex prompt: {e}")
            self.connection.rollback()
            return False

    def get_all_auspex_prompts(self):
        """Get all Auspex prompts."""
        try:
            results = self._execute_with_rollback(
                select(auspex_prompts).order_by(auspex_prompts.c.name)
            ).mappings().fetchall()

            return [dict(result) for result in results]
        except Exception as e:
            self.logger.error(f"Error getting all auspex prompts: {e}")
            return []

    def get_cached_trend_analysis(self, cache_key: str):
        """Get cached trend analysis by cache_key."""
        try:
            statement = select(
                analysis_versions_v2.c.version_data,
                analysis_versions_v2.c.created_at
            ).where(
                analysis_versions_v2.c.cache_key == cache_key
            ).order_by(
                analysis_versions_v2.c.created_at.desc()
            ).limit(1)

            result = self._execute_with_rollback(statement).mappings().fetchone()
            return result
        except Exception as e:
            self.logger.error(f"Error getting cached trend analysis: {e}")
            return None

    def save_cached_trend_analysis(self, cache_key: str, topic: str, version_data: str, cache_metadata: str, created_at: str):
        """Save cached trend analysis with PostgreSQL UPSERT."""
        try:
            # Import PostgreSQL-specific insert
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            # PostgreSQL uses ON CONFLICT for UPSERT
            statement = pg_insert(analysis_versions_v2).values(
                cache_key=cache_key,
                topic=topic,
                version_data=version_data,
                cache_metadata=cache_metadata,
                created_at=created_at
            ).on_conflict_do_update(
                index_elements=['cache_key'],
                set_={
                    'topic': topic,
                    'version_data': version_data,
                    'cache_metadata': cache_metadata,
                    'created_at': created_at
                }
            )

            self._execute_with_rollback(statement)
            self.connection.commit()
        except Exception as e:
            self.logger.error(f"Error saving cached trend analysis: {e}")
            self.connection.rollback()
            raise

    def ensure_analysis_cache_table(self):
        """Ensure the analysis_versions_v2 table exists."""
        try:
            # Create table if it doesn't exist using SQLAlchemy metadata
            from app.database_models import metadata
            analysis_versions_v2.create(self.connection, checkfirst=True)
            self.connection.commit()
        except Exception as e:
            self.logger.error(f"Error ensuring analysis cache table: {e}")
            self.connection.rollback()
            raise

    # =============================================================================
    # Dashboard Cache Methods
    # =============================================================================

    def upsert_dashboard_cache(
        self,
        cache_key: str,
        dashboard_type: str,
        date_range: str,
        topic: Optional[str],
        profile_id: Optional[int],
        persona: Optional[str],
        content_json: str,
        summary_text: str,
        article_count: int,
        model_used: Optional[str],
        generation_time_seconds: Optional[float]
    ) -> None:
        """Save or update a dashboard in cache (PostgreSQL UPSERT)."""
        try:
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            statement = pg_insert(dashboard_cache).values(
                cache_key=cache_key,
                dashboard_type=dashboard_type,
                date_range=date_range,
                topic=topic,
                profile_id=profile_id,
                persona=persona,
                content_json=content_json,
                summary_text=summary_text,
                article_count=article_count,
                model_used=model_used,
                generation_time_seconds=generation_time_seconds,
                generated_at=func.now()
            ).on_conflict_do_update(
                index_elements=['cache_key'],
                set_={
                    'dashboard_type': dashboard_type,
                    'date_range': date_range,
                    'topic': topic,
                    'profile_id': profile_id,
                    'persona': persona,
                    'content_json': content_json,
                    'summary_text': summary_text,
                    'article_count': article_count,
                    'model_used': model_used,
                    'generation_time_seconds': generation_time_seconds,
                    'generated_at': func.now()
                }
            )

            self._execute_with_rollback(statement)
            self.connection.commit()
        except Exception as e:
            self.logger.error(f"Error upserting dashboard cache: {e}")
            self.connection.rollback()
            raise

    def get_dashboard_cache(self, cache_key: str) -> Optional[Dict]:
        """Retrieve cached dashboard by key."""
        try:
            result = self._execute_with_rollback(
                select(dashboard_cache).where(dashboard_cache.c.cache_key == cache_key)
            ).mappings().fetchone()

            if result:
                data = dict(result)
                # Parse JSON content
                data['content'] = json.loads(data['content_json'])
                return data
            return None
        except Exception as e:
            self.logger.error(f"Error getting dashboard cache: {e}")
            return None

    def update_dashboard_cache_access(self, cache_key: str) -> None:
        """Update the accessed_at timestamp for a dashboard."""
        try:
            self._execute_with_rollback(
                update(dashboard_cache)
                .where(dashboard_cache.c.cache_key == cache_key)
                .values(accessed_at=func.now())
            )
            self.connection.commit()
        except Exception as e:
            self.logger.error(f"Error updating dashboard cache access: {e}")
            self.connection.rollback()

    def get_latest_dashboard_cache(
        self,
        dashboard_type: str,
        topic: Optional[str] = None
    ) -> Optional[Dict]:
        """Get the most recently generated dashboard of this type/topic."""
        try:
            query = select(dashboard_cache).where(
                dashboard_cache.c.dashboard_type == dashboard_type
            )

            if topic is not None:
                query = query.where(dashboard_cache.c.topic == topic)

            query = query.order_by(dashboard_cache.c.generated_at.desc()).limit(1)

            result = self._execute_with_rollback(query).mappings().fetchone()

            if result:
                data = dict(result)
                data['content'] = json.loads(data['content_json'])
                return data
            return None
        except Exception as e:
            self.logger.error(f"Error getting latest dashboard cache: {e}")
            return None

    def list_dashboard_cache(self, limit: int = 20) -> List[Dict]:
        """List all cached dashboards, most recently accessed first."""
        try:
            results = self._execute_with_rollback(
                select(dashboard_cache)
                .order_by(dashboard_cache.c.accessed_at.desc())
                .limit(limit)
            ).mappings().fetchall()

            dashboards = []
            for result in results:
                data = dict(result)
                # Don't include full content in list view, just metadata
                data.pop('content_json', None)
                dashboards.append(data)

            return dashboards
        except Exception as e:
            self.logger.error(f"Error listing dashboard cache: {e}")
            return []

    def delete_dashboard_cache(self, cache_key: str) -> bool:
        """Delete a cached dashboard."""
        try:
            result = self._execute_with_rollback(
                delete(dashboard_cache).where(dashboard_cache.c.cache_key == cache_key)
            )
            self.connection.commit()
            return result.rowcount > 0
        except Exception as e:
            self.logger.error(f"Error deleting dashboard cache: {e}")
            self.connection.rollback()
            return False

    # ========================================
    # Six Articles Configuration Methods
    # ========================================

    def get_six_articles_config(self, username: str) -> Optional[Dict]:
        """
        Get Six Articles configuration for a user.
        Stores system prompt, persona definitions, and format spec.
        """
        if not username:
            return None

        try:
            # Try to get from dedicated settings table if it exists
            # Otherwise fall back to user_preferences or create inline
            query = text("""
                SELECT config_value
                FROM user_preferences
                WHERE username = :username
                AND preference_key = 'six_articles_config'
            """)

            result = self.connection.execute(
                query,
                {"username": username}
            ).fetchone()

            if result and result[0]:
                import json
                return json.loads(result[0])

            return None

        except Exception as e:
            self.logger.error(f"Error getting Six Articles config for user {username}: {e}")
            return None

    def save_six_articles_config(self, username: str, config: Dict) -> bool:
        """
        Save Six Articles configuration for a user.
        Upserts into user_preferences table.
        """
        if not username:
            return False

        try:
            import json

            # Serialize config to JSON
            config_json = json.dumps(config, ensure_ascii=False)

            # Upsert into user_preferences
            if self.db_type == 'postgresql':
                query = text("""
                    INSERT INTO user_preferences (username, preference_key, config_value, updated_at)
                    VALUES (:username, 'six_articles_config', :config_json, NOW())
                    ON CONFLICT (username, preference_key)
                    DO UPDATE SET
                        config_value = EXCLUDED.config_value,
                        updated_at = NOW()
                """)
            else:  # SQLite
                query = text("""
                    INSERT OR REPLACE INTO user_preferences (username, preference_key, config_value, updated_at)
                    VALUES (:username, 'six_articles_config', :config_json, datetime('now'))
                """)

            self.connection.execute(
                query,
                {
                    "username": username,
                    "config_json": config_json
                }
            )
            self.connection.commit()

            self.logger.info(f"Saved Six Articles config for user {username}")
            return True

        except Exception as e:
            self.logger.error(f"Error saving Six Articles config for user {username}: {e}")
            self.connection.rollback()
            return False

    # ==========================================
    # Analysis Run Logging Methods
    # ==========================================

    def create_analysis_run_log(self, run_id: str, analysis_type: str, topic: str,
                                model_used: str = None, sample_size: int = None,
                                timeframe_days: int = None, consistency_mode: str = None,
                                profile_id: int = None, persona: str = None,
                                customer_type: str = None, cache_key: str = None,
                                cache_hit: bool = False, metadata: dict = None):
        """Create a new analysis run log entry"""
        try:
            from app.database_models import t_analysis_run_logs as analysis_run_logs

            statement = analysis_run_logs.insert().values(
                run_id=run_id,
                analysis_type=analysis_type,
                topic=topic,
                model_used=model_used,
                sample_size=sample_size,
                timeframe_days=timeframe_days,
                consistency_mode=consistency_mode,
                profile_id=profile_id,
                persona=persona,
                customer_type=customer_type,
                cache_key=cache_key,
                cache_hit=cache_hit,
                status='running',
                metadata=json.dumps(metadata) if metadata else None
            )
            self._execute_with_rollback(statement)
            self.connection.commit()

            self.logger.info(f"Created analysis run log: {run_id} for topic '{topic}'")
            return run_id

        except Exception as e:
            self.logger.error(f"Error creating analysis run log: {e}")
            self.connection.rollback()
            return None

    def log_articles_for_analysis_run(self, run_id: str, articles: list):
        """Log all articles reviewed in an analysis run"""
        try:
            from app.database_models import t_analysis_run_articles as analysis_run_articles

            article_records = []
            for idx, article in enumerate(articles):
                article_records.append({
                    'run_id': run_id,
                    'article_uri': article.get('uri') or article.get('url'),
                    'article_title': article.get('title'),
                    'article_source': article.get('news_source') or article.get('source'),
                    'published_date': article.get('publication_date') or article.get('published_date'),
                    'sentiment': article.get('sentiment'),
                    'relevance_score': article.get('relevance_score'),
                    'included_in_prompt': True,
                    'article_position': idx + 1
                })

            if article_records:
                statement = analysis_run_articles.insert().values(article_records)
                self._execute_with_rollback(statement)
                self.connection.commit()

                self.logger.info(f"Logged {len(article_records)} articles for run {run_id}")
                return len(article_records)

            return 0

        except Exception as e:
            self.logger.error(f"Error logging articles for analysis run {run_id}: {e}")
            self.connection.rollback()
            return 0

    def complete_analysis_run_log(self, run_id: str, articles_analyzed: int = None,
                                  status: str = 'completed', error_message: str = None):
        """Mark an analysis run as completed or failed"""
        try:
            from app.database_models import t_analysis_run_logs as analysis_run_logs
            from sqlalchemy import func

            update_values = {
                'status': status,
                'completed_at': func.current_timestamp()
            }

            if articles_analyzed is not None:
                update_values['articles_analyzed'] = articles_analyzed

            if error_message:
                update_values['error_message'] = error_message

            statement = analysis_run_logs.update().where(
                analysis_run_logs.c.run_id == run_id
            ).values(**update_values)

            self._execute_with_rollback(statement)
            self.connection.commit()

            self.logger.info(f"Completed analysis run log: {run_id} with status '{status}'")
            return True

        except Exception as e:
            self.logger.error(f"Error completing analysis run log {run_id}: {e}")
            self.connection.rollback()
            return False

    def get_analysis_run_details(self, run_id: str):
        """Get details of a specific analysis run including all articles"""
        try:
            from app.database_models import (
                t_analysis_run_logs as analysis_run_logs,
                t_analysis_run_articles as analysis_run_articles
            )

            # Get run details
            run_stmt = select(analysis_run_logs).where(
                analysis_run_logs.c.run_id == run_id
            )
            run_row = self._execute_with_rollback(run_stmt).fetchone()

            if not run_row:
                return None

            # Get articles
            articles_stmt = select(analysis_run_articles).where(
                analysis_run_articles.c.run_id == run_id
            ).order_by(analysis_run_articles.c.article_position)

            articles_rows = self._execute_with_rollback(articles_stmt).fetchall()

            return {
                'run': dict(run_row._mapping) if hasattr(run_row, '_mapping') else dict(run_row),
                'articles': [dict(row._mapping) if hasattr(row, '_mapping') else dict(row)
                           for row in articles_rows]
            }

        except Exception as e:
            self.logger.error(f"Error getting analysis run details for {run_id}: {e}")
            return None

    def get_recent_analysis_runs(self, analysis_type: str = None, topic: str = None,
                                limit: int = 50):
        """Get recent analysis runs with optional filtering"""
        try:
            from app.database_models import t_analysis_run_logs as analysis_run_logs

            stmt = select(analysis_run_logs).order_by(
                analysis_run_logs.c.started_at.desc()
            )

            if analysis_type:
                stmt = stmt.where(analysis_run_logs.c.analysis_type == analysis_type)

            if topic:
                stmt = stmt.where(analysis_run_logs.c.topic == topic)

            stmt = stmt.limit(limit)

            rows = self._execute_with_rollback(stmt).fetchall()

            return [dict(row._mapping) if hasattr(row, '_mapping') else dict(row)
                   for row in rows]

        except Exception as e:
            self.logger.error(f"Error getting recent analysis runs: {e}")
            return []

    # =========================
    # Consensus Analysis Methods
    # =========================

    def save_consensus_analysis(
        self,
        analysis_id: str,
        user_id: int,
        topic: str,
        timeframe: str,
        selected_categories: list,
        raw_output: dict,
        article_list: list,
        total_articles_analyzed: int,
        analysis_duration_seconds: float
    ) -> bool:
        """
        Save a consensus analysis run to the database.

        Args:
            analysis_id: UUID for the analysis run
            user_id: ID of the user who requested the analysis
            topic: Topic analyzed
            timeframe: Timeframe for analysis
            selected_categories: List of categories analyzed
            raw_output: Full JSON output from the AI
            article_list: List of articles with id, title, source, url
            total_articles_analyzed: Total number of articles processed
            analysis_duration_seconds: Time taken to complete analysis

        Returns:
            bool: True if saved successfully, False otherwise
        """
        try:
            from app.database_models import t_consensus_analysis_runs
            from sqlalchemy import insert
            import json

            stmt = insert(t_consensus_analysis_runs).values(
                id=analysis_id,
                user_id=user_id,
                topic=topic,
                timeframe=timeframe,
                selected_categories=json.dumps(selected_categories) if selected_categories else None,
                raw_output=json.dumps(raw_output),
                article_list=json.dumps(article_list) if article_list else None,
                total_articles_analyzed=total_articles_analyzed,
                analysis_duration_seconds=analysis_duration_seconds
            )

            self._execute_with_rollback(stmt)
            self.logger.info(f"Saved consensus analysis {analysis_id} for topic '{topic}'")
            return True

        except Exception as e:
            self.logger.error(f"Error saving consensus analysis: {e}")
            return False

    def get_consensus_analysis(self, analysis_id: str) -> dict:
        """
        Retrieve a consensus analysis by ID.

        Args:
            analysis_id: UUID of the analysis run

        Returns:
            dict: Analysis data including raw output, or empty dict if not found
        """
        try:
            from app.database_models import t_consensus_analysis_runs
            from sqlalchemy import select
            import json

            stmt = select(t_consensus_analysis_runs).where(
                t_consensus_analysis_runs.c.id == analysis_id
            )

            result = self._execute_with_rollback(stmt).fetchone()

            if result:
                data = dict(result._mapping) if hasattr(result, '_mapping') else dict(result)
                # Parse JSON fields
                if data.get('raw_output'):
                    data['raw_output'] = json.loads(data['raw_output']) if isinstance(data['raw_output'], str) else data['raw_output']
                if data.get('selected_categories'):
                    data['selected_categories'] = json.loads(data['selected_categories']) if isinstance(data['selected_categories'], str) else data['selected_categories']
                return data

            return {}

        except Exception as e:
            self.logger.error(f"Error retrieving consensus analysis {analysis_id}: {e}")
            return {}

    def get_recent_consensus_analyses(self, user_id: int = None, limit: int = 10) -> list:
        """
        Get recent consensus analyses, optionally filtered by user.

        Args:
            user_id: Optional user ID to filter by
            limit: Maximum number of results to return

        Returns:
            list: List of analysis records (without full raw_output for performance)
        """
        try:
            from app.database_models import t_consensus_analysis_runs
            from sqlalchemy import select

            stmt = select(
                t_consensus_analysis_runs.c.id,
                t_consensus_analysis_runs.c.user_id,
                t_consensus_analysis_runs.c.topic,
                t_consensus_analysis_runs.c.timeframe,
                t_consensus_analysis_runs.c.total_articles_analyzed,
                t_consensus_analysis_runs.c.created_at,
                t_consensus_analysis_runs.c.analysis_duration_seconds
            ).order_by(t_consensus_analysis_runs.c.created_at.desc())

            if user_id is not None:
                stmt = stmt.where(t_consensus_analysis_runs.c.user_id == user_id)

            stmt = stmt.limit(limit)

            rows = self._execute_with_rollback(stmt).fetchall()

            return [dict(row._mapping) if hasattr(row, '_mapping') else dict(row)
                   for row in rows]

        except Exception as e:
            self.logger.error(f"Error getting recent consensus analyses: {e}")
            return []

    # Market Signals Analysis Storage Methods
    def save_market_signals_analysis(
        self,
        analysis_id: str,
        user_id: int,
        topic: str,
        model_used: str,
        raw_output: dict,
        total_articles_analyzed: int,
        analysis_duration_seconds: float
    ) -> bool:
        """Save a market signals analysis run to the database."""
        try:
            from app.database_models import t_market_signals_runs
            from sqlalchemy import insert
            import json

            stmt = insert(t_market_signals_runs).values(
                id=analysis_id,
                user_id=user_id,
                topic=topic,
                model_used=model_used,
                raw_output=json.dumps(raw_output),
                total_articles_analyzed=total_articles_analyzed,
                analysis_duration_seconds=analysis_duration_seconds
            )

            self._execute_with_rollback(stmt)
            self.logger.info(f"Saved market signals analysis {analysis_id} for topic '{topic}'")
            return True

        except Exception as e:
            self.logger.error(f"Error saving market signals analysis: {e}")
            return False

    def get_market_signals_analysis(self, analysis_id: str) -> dict:
        """Retrieve a market signals analysis by ID."""
        try:
            from app.database_models import t_market_signals_runs
            from sqlalchemy import select
            import json

            stmt = select(t_market_signals_runs).where(
                t_market_signals_runs.c.id == analysis_id
            )

            result = self._execute_with_rollback(stmt).fetchone()

            if result:
                data = dict(result._mapping) if hasattr(result, '_mapping') else dict(result)
                if data.get('raw_output'):
                    data['raw_output'] = json.loads(data['raw_output']) if isinstance(data['raw_output'], str) else data['raw_output']
                return data

            return {}

        except Exception as e:
            self.logger.error(f"Error retrieving market signals analysis {analysis_id}: {e}")
            return {}

    def get_recent_market_signals_analyses(self, user_id: int = None, limit: int = 10) -> list:
        """Get recent market signals analyses."""
        try:
            from app.database_models import t_market_signals_runs
            from sqlalchemy import select

            stmt = select(
                t_market_signals_runs.c.id,
                t_market_signals_runs.c.user_id,
                t_market_signals_runs.c.topic,
                t_market_signals_runs.c.model_used,
                t_market_signals_runs.c.total_articles_analyzed,
                t_market_signals_runs.c.created_at,
                t_market_signals_runs.c.analysis_duration_seconds
            ).order_by(t_market_signals_runs.c.created_at.desc())

            if user_id is not None:
                stmt = stmt.where(t_market_signals_runs.c.user_id == user_id)

            stmt = stmt.limit(limit)

            rows = self._execute_with_rollback(stmt).fetchall()

            return [dict(row._mapping) if hasattr(row, '_mapping') else dict(row)
                   for row in rows]

        except Exception as e:
            self.logger.error(f"Error getting recent market signals analyses: {e}")
            return []

    # Impact Timeline Analysis Storage Methods
    def save_impact_timeline_analysis(
        self,
        analysis_id: str,
        user_id: int,
        topic: str,
        model_used: str,
        raw_output: dict,
        total_articles_analyzed: int,
        analysis_duration_seconds: float
    ) -> bool:
        """Save an impact timeline analysis run to the database."""
        try:
            from app.database_models import t_impact_timeline_runs
            from sqlalchemy import insert
            import json

            stmt = insert(t_impact_timeline_runs).values(
                id=analysis_id,
                user_id=user_id,
                topic=topic,
                model_used=model_used,
                raw_output=json.dumps(raw_output),
                total_articles_analyzed=total_articles_analyzed,
                analysis_duration_seconds=analysis_duration_seconds
            )

            self._execute_with_rollback(stmt)
            self.logger.info(f"Saved impact timeline analysis {analysis_id} for topic '{topic}'")
            return True

        except Exception as e:
            self.logger.error(f"Error saving impact timeline analysis: {e}")
            return False

    def get_impact_timeline_analysis(self, analysis_id: str) -> dict:
        """Retrieve an impact timeline analysis by ID."""
        try:
            from app.database_models import t_impact_timeline_runs
            from sqlalchemy import select
            import json

            stmt = select(t_impact_timeline_runs).where(
                t_impact_timeline_runs.c.id == analysis_id
            )

            result = self._execute_with_rollback(stmt).fetchone()

            if result:
                data = dict(result._mapping) if hasattr(result, '_mapping') else dict(result)
                if data.get('raw_output'):
                    data['raw_output'] = json.loads(data['raw_output']) if isinstance(data['raw_output'], str) else data['raw_output']
                return data

            return {}

        except Exception as e:
            self.logger.error(f"Error retrieving impact timeline analysis {analysis_id}: {e}")
            return {}

    def get_recent_impact_timeline_analyses(self, user_id: int = None, limit: int = 10) -> list:
        """Get recent impact timeline analyses."""
        try:
            from app.database_models import t_impact_timeline_runs
            from sqlalchemy import select

            stmt = select(
                t_impact_timeline_runs.c.id,
                t_impact_timeline_runs.c.user_id,
                t_impact_timeline_runs.c.topic,
                t_impact_timeline_runs.c.model_used,
                t_impact_timeline_runs.c.total_articles_analyzed,
                t_impact_timeline_runs.c.created_at,
                t_impact_timeline_runs.c.analysis_duration_seconds
            ).order_by(t_impact_timeline_runs.c.created_at.desc())

            if user_id is not None:
                stmt = stmt.where(t_impact_timeline_runs.c.user_id == user_id)

            stmt = stmt.limit(limit)

            rows = self._execute_with_rollback(stmt).fetchall()

            return [dict(row._mapping) if hasattr(row, '_mapping') else dict(row)
                   for row in rows]

        except Exception as e:
            self.logger.error(f"Error getting recent impact timeline analyses: {e}")
            return []

    # Strategic Recommendations Analysis Storage Methods
    def save_strategic_recommendations_analysis(
        self,
        analysis_id: str,
        user_id: int,
        topic: str,
        model_used: str,
        raw_output: dict,
        total_articles_analyzed: int,
        analysis_duration_seconds: float
    ) -> bool:
        """Save a strategic recommendations analysis run to the database."""
        try:
            from app.database_models import t_strategic_recommendations_runs
            from sqlalchemy import insert
            import json

            stmt = insert(t_strategic_recommendations_runs).values(
                id=analysis_id,
                user_id=user_id,
                topic=topic,
                model_used=model_used,
                raw_output=json.dumps(raw_output),
                total_articles_analyzed=total_articles_analyzed,
                analysis_duration_seconds=analysis_duration_seconds
            )

            self._execute_with_rollback(stmt)
            self.logger.info(f"Saved strategic recommendations analysis {analysis_id} for topic '{topic}'")
            return True

        except Exception as e:
            self.logger.error(f"Error saving strategic recommendations analysis: {e}")
            return False

    def get_strategic_recommendations_analysis(self, analysis_id: str) -> dict:
        """Retrieve a strategic recommendations analysis by ID."""
        try:
            from app.database_models import t_strategic_recommendations_runs
            from sqlalchemy import select
            import json

            stmt = select(t_strategic_recommendations_runs).where(
                t_strategic_recommendations_runs.c.id == analysis_id
            )

            result = self._execute_with_rollback(stmt).fetchone()

            if result:
                data = dict(result._mapping) if hasattr(result, '_mapping') else dict(result)
                if data.get('raw_output'):
                    data['raw_output'] = json.loads(data['raw_output']) if isinstance(data['raw_output'], str) else data['raw_output']
                return data

            return {}

        except Exception as e:
            self.logger.error(f"Error retrieving strategic recommendations analysis {analysis_id}: {e}")
            return {}

    def get_recent_strategic_recommendations_analyses(self, user_id: int = None, limit: int = 10) -> list:
        """Get recent strategic recommendations analyses."""
        try:
            from app.database_models import t_strategic_recommendations_runs
            from sqlalchemy import select

            stmt = select(
                t_strategic_recommendations_runs.c.id,
                t_strategic_recommendations_runs.c.user_id,
                t_strategic_recommendations_runs.c.topic,
                t_strategic_recommendations_runs.c.model_used,
                t_strategic_recommendations_runs.c.total_articles_analyzed,
                t_strategic_recommendations_runs.c.created_at,
                t_strategic_recommendations_runs.c.analysis_duration_seconds
            ).order_by(t_strategic_recommendations_runs.c.created_at.desc())

            if user_id is not None:
                stmt = stmt.where(t_strategic_recommendations_runs.c.user_id == user_id)

            stmt = stmt.limit(limit)

            rows = self._execute_with_rollback(stmt).fetchall()

            return [dict(row._mapping) if hasattr(row, '_mapping') else dict(row)
                   for row in rows]

        except Exception as e:
            self.logger.error(f"Error getting recent strategic recommendations analyses: {e}")
            return []

    # Future Horizons Analysis Storage Methods
    def save_future_horizons_analysis(
        self,
        analysis_id: str,
        user_id: int,
        topic: str,
        model_used: str,
        raw_output: dict,
        total_articles_analyzed: int,
        analysis_duration_seconds: float
    ) -> bool:
        """Save a future horizons analysis run to the database."""
        try:
            from app.database_models import t_future_horizons_runs
            from sqlalchemy import insert
            import json

            stmt = insert(t_future_horizons_runs).values(
                id=analysis_id,
                user_id=user_id,
                topic=topic,
                model_used=model_used,
                raw_output=json.dumps(raw_output),
                total_articles_analyzed=total_articles_analyzed,
                analysis_duration_seconds=analysis_duration_seconds
            )

            self._execute_with_rollback(stmt)
            self.logger.info(f"Saved future horizons analysis {analysis_id} for topic '{topic}'")
            return True

        except Exception as e:
            self.logger.error(f"Error saving future horizons analysis: {e}")
            return False

    def get_future_horizons_analysis(self, analysis_id: str) -> dict:
        """Retrieve a future horizons analysis by ID."""
        try:
            from app.database_models import t_future_horizons_runs
            from sqlalchemy import select
            import json

            stmt = select(t_future_horizons_runs).where(
                t_future_horizons_runs.c.id == analysis_id
            )

            result = self._execute_with_rollback(stmt).fetchone()

            if result:
                data = dict(result._mapping) if hasattr(result, '_mapping') else dict(result)
                if data.get('raw_output'):
                    data['raw_output'] = json.loads(data['raw_output']) if isinstance(data['raw_output'], str) else data['raw_output']
                return data

            return {}

        except Exception as e:
            self.logger.error(f"Error retrieving future horizons analysis {analysis_id}: {e}")
            return {}

    def get_recent_future_horizons_analyses(self, user_id: int = None, limit: int = 10) -> list:
        """Get recent future horizons analyses."""
        try:
            from app.database_models import t_future_horizons_runs
            from sqlalchemy import select

            stmt = select(
                t_future_horizons_runs.c.id,
                t_future_horizons_runs.c.user_id,
                t_future_horizons_runs.c.topic,
                t_future_horizons_runs.c.model_used,
                t_future_horizons_runs.c.total_articles_analyzed,
                t_future_horizons_runs.c.created_at,
                t_future_horizons_runs.c.analysis_duration_seconds
            ).order_by(t_future_horizons_runs.c.created_at.desc())

            if user_id is not None:
                stmt = stmt.where(t_future_horizons_runs.c.user_id == user_id)

            stmt = stmt.limit(limit)

            rows = self._execute_with_rollback(stmt).fetchall()

            return [dict(row._mapping) if hasattr(row, '_mapping') else dict(row)
                   for row in rows]

        except Exception as e:
            self.logger.error(f"Error getting recent future horizons analyses: {e}")
            return []

    # ==================== Notifications ====================

    def create_notification(self, username: str | None, type: str, title: str, message: str, link: str | None = None) -> int:
        """Create a new notification.

        Args:
            username: Username to notify (None for system-wide notifications)
            type: Notification type (e.g., 'evaluation_complete', 'article_analysis', 'system')
            title: Notification title
            message: Notification message
            link: Optional link to navigate to when clicked

        Returns:
            Notification ID
        """
        from app.database_models import t_notifications

        statement = insert(t_notifications).values(
            username=username,
            type=type,
            title=title,
            message=message,
            link=link,
            read=False
        ).returning(t_notifications.c.id)

        result = self._execute_with_rollback(statement).scalar_one()
        self.logger.info(f"Created notification {result} for user {username}: {title}")
        return result

    def get_user_notifications(self, username: str, unread_only: bool = False, limit: int = 50) -> list:
        """Get notifications for a user.

        Args:
            username: Username to get notifications for
            unread_only: If True, only return unread notifications
            limit: Maximum number of notifications to return

        Returns:
            List of notification dictionaries
        """
        from app.database_models import t_notifications

        statement = select(t_notifications).where(
            or_(
                t_notifications.c.username == username,
                t_notifications.c.username.is_(None)  # Include system-wide notifications
            )
        )

        if unread_only:
            statement = statement.where(t_notifications.c.read == False)

        statement = statement.order_by(
            t_notifications.c.created_at.desc()
        ).limit(limit)

        result = self._execute_with_rollback(statement)
        return [dict(row._mapping) for row in result]

    def get_unread_count(self, username: str) -> int:
        """Get count of unread notifications for a user.

        Args:
            username: Check notifications for this username

        Returns:
            Count of unread notifications
        """
        from app.database_models import t_notifications

        statement = select(func.count()).select_from(t_notifications).where(
            and_(
                or_(
                    t_notifications.c.username == username,
                    t_notifications.c.username.is_(None)
                ),
                t_notifications.c.read == False
            )
        )

        return self._execute_with_rollback(statement).scalar() or 0

    def mark_notification_as_read(self, notification_id: int, username: str) -> bool:
        """Mark a notification as read.

        Args:
            notification_id: Notification ID
            username: Username (for security check)

        Returns:
            True if successful
        """
        from app.database_models import t_notifications

        statement = update(t_notifications).where(
            and_(
                t_notifications.c.id == notification_id,
                or_(
                    t_notifications.c.username == username,
                    t_notifications.c.username.is_(None)
                )
            )
        ).values(read=True)

        self._execute_with_rollback(statement)
        return True

    def mark_all_notifications_as_read(self, username: str) -> int:
        """Mark all notifications as read for a user.

        Args:
            username: Username

        Returns:
            Number of notifications marked as read
        """
        from app.database_models import t_notifications

        statement = update(t_notifications).where(
            and_(
                or_(
                    t_notifications.c.username == username,
                    t_notifications.c.username.is_(None)
                ),
                t_notifications.c.read == False
            )
        ).values(read=True)

        result = self._execute_with_rollback(statement)
        count = result.rowcount
        self.logger.info(f"Marked {count} notifications as read for user {username}")
        return count

    def delete_notification(self, notification_id: int, username: str) -> bool:
        """Delete a specific notification.

        Args:
            notification_id: Notification ID to delete
            username: Username (for security check)

        Returns:
            True if successful
        """
        from app.database_models import t_notifications

        statement = delete(t_notifications).where(
            and_(
                t_notifications.c.id == notification_id,
                or_(
                    t_notifications.c.username == username,
                    t_notifications.c.username.is_(None)
                )
            )
        )

        result = self._execute_with_rollback(statement)
        self.logger.info(f"Deleted notification {notification_id} for user {username}")
        return result.rowcount > 0

    def delete_read_notifications(self, username: str) -> int:
        """Delete all read notifications for a user.

        Args:
            username: Username to delete read notifications for

        Returns:
            Number of notifications deleted
        """
        from app.database_models import t_notifications

        statement = delete(t_notifications).where(
            and_(
                t_notifications.c.username == username,
                t_notifications.c.read == True
            )
        )

        result = self._execute_with_rollback(statement)
        count = result.rowcount
        self.logger.info(f"Deleted {count} read notifications for user {username}")
        return count

    def delete_old_notifications(self, days: int = 30) -> int:
        """Delete notifications older than specified days.

        Args:
            days: Number of days to keep notifications

        Returns:
            Number of notifications deleted
        """
        from app.database_models import t_notifications
        from datetime import datetime, timedelta

        cutoff_date = datetime.now() - timedelta(days=days)

        statement = delete(t_notifications).where(
            t_notifications.c.created_at < cutoff_date
        )

        result = self._execute_with_rollback(statement)
        count = result.rowcount
        self.logger.info(f"Deleted {count} notifications older than {days} days")
        return count
