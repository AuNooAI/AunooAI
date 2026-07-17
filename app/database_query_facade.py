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
                                 t_raw_articles as raw_articles,
                                 t_llm_retry_state as llm_retry_state,
                                 t_llm_processing_errors as llm_processing_errors,
                                 t_processing_jobs as processing_jobs,
                                 t_auspex_research_sessions as auspex_research_sessions,
                                 t_auspex_tool_usage as auspex_tool_usage,
                                 t_auspex_search_routing as auspex_search_routing)
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

    def get_auto_regenerate_reports_setting(self) -> bool:
        """Get auto-regenerate reports setting"""
        row = self.get_keyword_monitor_settings_by_id(1)
        if row and 'auto_regenerate_reports' in row:
            return bool(row['auto_regenerate_reports'])
        return False

    def update_auto_regenerate_reports_setting(self, enabled: bool):
        """Update auto-regenerate reports setting"""
        from sqlalchemy import update
        from app.database_models import t_keyword_monitor_settings

        stmt = update(t_keyword_monitor_settings).where(
            t_keyword_monitor_settings.c.id == 1
        ).values(auto_regenerate_reports=enabled)

        self._execute_with_rollback(stmt)

    def invalidate_six_articles_cache_for_topic(self, topic: str):
        """Invalidate Six Articles cache entries for a topic"""
        from app.database_models import t_article_analysis_cache
        from sqlalchemy import delete, or_
        import logging

        logger = logging.getLogger(__name__)

        # Pattern matches: six_articles_v5_YYYY-MM-DD_{topic}_*
        topic_safe = topic or 'all'

        stmt = delete(t_article_analysis_cache).where(
            or_(
                t_article_analysis_cache.c.article_uri.like(f'%six_articles_v5_%_{topic_safe}_%'),
                t_article_analysis_cache.c.article_uri.like(f'%six_articles_%{topic_safe}%')
            )
        )

        result = self._execute_with_rollback(stmt)
        logger.info(f"Invalidated Six Articles cache for topic: {topic}")
        return result.rowcount if hasattr(result, 'rowcount') else 0

    def invalidate_insights_cache_for_topic(self, topic: str):
        """Invalidate insights cache entries (article insights and incident tracking) for a topic"""
        from app.database_models import t_article_analysis_cache
        from sqlalchemy import delete, or_, and_
        import logging

        logger = logging.getLogger(__name__)

        topic_safe = topic or 'all'

        # Delete cache entries for article insights and incident tracking
        # Patterns:
        # - analysis_type LIKE 'article_insights_%{topic}%' for narratives
        # - article_uri LIKE '%incident_tracking%{topic}%' for highlights
        stmt = delete(t_article_analysis_cache).where(
            or_(
                # Article insights (narratives) stored by analysis_type
                t_article_analysis_cache.c.analysis_type.like(f'%article_insights%{topic_safe}%'),
                # Incident tracking (highlights) stored by article_uri pattern
                t_article_analysis_cache.c.article_uri.like(f'%incident_tracking%{topic_safe}%'),
                # Also catch any with topic in the article_uri for article insights
                and_(
                    t_article_analysis_cache.c.analysis_type.like('%article_insights%'),
                    t_article_analysis_cache.c.article_uri.like(f'%{topic_safe}%')
                )
            )
        )

        result = self._execute_with_rollback(stmt)
        logger.info(f"Invalidated insights cache (narratives + highlights) for topic: {topic}")
        return result.rowcount if hasattr(result, 'rowcount') else 0

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
                monitored_keywords.c.group_id,
                keyword_groups.c.topic,
                keyword_groups.c.name.label('group_name')
            ).select_from(
                monitored_keywords
                .join(keyword_groups, monitored_keywords.c.group_id == keyword_groups.c.id)
            )
        return self._execute_with_rollback(statement).mappings().fetchall()

    def get_monitored_keywords_by_group_id(self, group_id: int):
        """Get all monitored keywords for a specific group."""
        statement = select(
                monitored_keywords.c.id,
                monitored_keywords.c.keyword,
                monitored_keywords.c.last_checked,
                monitored_keywords.c.group_id,
                keyword_groups.c.topic,
                keyword_groups.c.name.label('group_name')
            ).select_from(
                monitored_keywords
                .join(keyword_groups, monitored_keywords.c.group_id == keyword_groups.c.id)
            ).where(
                monitored_keywords.c.group_id == group_id
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
                    analyzed=False,
                    opoint_entities=article.get('opoint_entities'),
                    # Social posts (xpoz/bluesky) carry author + engagement here; the
                    # social-only group path saves ONLY via this insert, so dropping
                    # it loses author/likes for good (adverse rules depend on both).
                    social_meta=article.get('social_meta')
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

        # Import raw_articles table for LEFT JOIN
        from app.database_models import t_raw_articles as raw_articles_table

        # Build base conditions
        conditions = [
            # NOTE: publication_date is TEXT, use strftime() to match DB format
            articles.c.publication_date >= start_date.strftime('%Y-%m-%d'),
            articles.c.publication_date <= end_date.strftime('%Y-%m-%d %H:%M:%S'),
            articles.c.summary != '',
            articles.c.summary != None,
            articles.c.analyzed == True,  # Only include analyzed/relevant articles
        ]

        # Only filter by topic if one is specified (not None, empty, or "__all__")
        if topic and topic != "__all__":
            conditions.append(articles.c.topic == topic)

        statement = select(
            articles.c.title,
            articles.c.summary,
            articles.c.uri,
            articles.c.publication_date,
            articles.c.sentiment,
            articles.c.category,
            articles.c.future_signal,
            articles.c.driver_type,
            articles.c.time_to_impact,
            raw_articles_table.c.raw_markdown.label('raw_markdown')  # Add raw content
        ).select_from(
            articles.outerjoin(
                raw_articles_table,
                articles.c.uri == raw_articles_table.c.uri
            )
        ).where(and_(*conditions))
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
            organizational_profiles.c.updated_at,
            organizational_profiles.c.monitored_brands
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
            custom_context=params[13],
            monitored_brands=params[14] if len(params) > 14 else None
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
            organizational_profiles.c.updated_at,
            organizational_profiles.c.monitored_brands
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
            organizational_profiles.c.id == params[15]
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
            monitored_brands = params[14],
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
        """
        Get the configured LLM model name.
        Returns None if not set (meaning use first available model).
        """
        statement = select(
            keyword_monitor_settings.c.default_llm_model,
            keyword_monitor_settings.c.llm_temperature,
            keyword_monitor_settings.c.llm_max_tokens
        ).where(
            keyword_monitor_settings.c.id == 1
        )
        settings = self._execute_with_rollback(statement).mappings().fetchone()
        if settings:
            # Return the model or None if not set (frontend will select first available)
            return settings['default_llm_model']
        return None

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
        """Get recent articles for a topic, including raw markdown content.

        Args:
            topic: Topic name
            limit: Maximum number of articles to return

        Returns:
            List of article dictionaries with raw_markdown field
        """
        from app.database_models import t_raw_articles

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
            articles.c.news_source,
            t_raw_articles.c.raw_markdown
        ).select_from(
            articles.outerjoin(
                t_raw_articles,
                articles.c.uri == t_raw_articles.c.uri
            )
        ).where(
            and_(
                articles.c.topic == topic,
                articles.c.analyzed == True  # Only analyzed articles
            )
        ).order_by(
            desc(articles.c.publication_date)
        ).limit(limit)

        return self._execute_with_rollback(statement).mappings().fetchall()

    def get_articles_for_topic(self, topic: str, limit: int = 100, days_back: int = 1):
        """Get recent articles for a topic within a date range.

        Args:
            topic: Topic name
            limit: Maximum number of articles to return
            days_back: Number of days to look back from now

        Returns:
            List of article dictionaries with uri field
        """
        from datetime import datetime, timedelta

        # Calculate cutoff date and format as ISO 8601 string (publication_date is TEXT)
        cutoff_date = datetime.now() - timedelta(days=days_back)
        cutoff_date_str = cutoff_date.strftime('%Y-%m-%dT%H:%M:%S')

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
                articles.c.analyzed == True,
                articles.c.publication_date >= cutoff_date_str
            )
        ).order_by(
            desc(articles.c.publication_date)
        ).limit(limit)

        return self._execute_with_rollback(statement).mappings().fetchall()

    def get_relevant_articles_for_topic(
        self, topic: str, *, days_back: int = 110,
        min_alignment: float = 0.3, limit: int = 200,
    ):
        """Recent articles for a topic, filtered by ``topic_alignment_score``.

        ``get_articles_for_topic`` returns EVERYTHING tagged to a topic,
        including the off-topic general news that lands in a feed (a
        peer-review topic collects "fighter jets scrambled" etc. with
        ``topic_alignment_score = 0.0``). Anything customer-facing — event
        extraction, the "what's changed" section — must use the alignment
        score the ingest pipeline already computed, or it inherits that
        noise. Real on-topic articles score 0.9–1.0; the noise scores 0.0,
        so a modest floor (default 0.3) cleanly separates them.

        Ordered by alignment desc so the most on-topic material is consumed
        first when a caller caps the result.
        """
        from datetime import datetime, timedelta

        cutoff_str = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%dT%H:%M:%S')
        statement = select(
            articles.c.uri,
            articles.c.title,
            articles.c.summary,
            articles.c.publication_date,
            articles.c.news_source,
            articles.c.topic_alignment_score,
        ).where(
            and_(
                articles.c.topic == topic,
                articles.c.analyzed == True,
                articles.c.publication_date >= cutoff_str,
                articles.c.topic_alignment_score != None,
                articles.c.topic_alignment_score > min_alignment,
            )
        ).order_by(
            desc(articles.c.topic_alignment_score),
            desc(articles.c.publication_date),
        ).limit(limit)

        return self._execute_with_rollback(statement).mappings().fetchall()

    def count_relevant_articles_for_topic_window(
        self, topic: str, *, start: str, end: str, min_alignment: float = 0.3,
    ) -> int:
        """Count on-topic articles for ``topic`` with publication_date in [start, end).

        Same alignment filter as ``get_relevant_articles_for_topic`` (so the
        count reflects genuine on-topic coverage, not feed noise), but bounded
        by an explicit ISO date window so two equal-length periods can be
        compared for the "where press attention shifted" signal. ``start`` and
        ``end`` are ISO strings; ``publication_date`` is TEXT in ISO format so
        lexical comparison is correct.
        """
        statement = select(func.count()).select_from(articles).where(
            and_(
                articles.c.topic == topic,
                articles.c.analyzed == True,
                articles.c.publication_date >= start,
                articles.c.publication_date < end,
                articles.c.topic_alignment_score != None,
                articles.c.topic_alignment_score > min_alignment,
            )
        )
        return self._execute_with_rollback(statement).scalar() or 0

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
        # Convert datetime to ISO string for TEXT column comparison
        # publication_date is stored as TEXT in the database
        start_str = start_date.isoformat() if hasattr(start_date, 'isoformat') else str(start_date)
        end_str = end_date.isoformat() if hasattr(end_date, 'isoformat') else str(end_date)

        # Build base query with date filters
        statement = select(articles).where(
            articles.c.publication_date >= start_str,
            articles.c.publication_date <= end_str,
            articles.c.analyzed == True,  # Only include analyzed/relevant articles
        )

        # Only filter by topic if one is specified (not None, empty, or "__all__")
        if topic and topic != "__all__":
            statement = statement.where(articles.c.topic == topic)

        statement = statement.order_by(articles.c.publication_date.desc())

        if limit:
            statement = statement.limit(limit)

        articles_list = self._execute_with_rollback(statement).mappings().fetchall()

        # Return list of dicts for easier consumption
        return [dict(article) for article in articles_list]

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

    def delete_unscored_article_matches(self, group_id: int) -> int:
        """
        Delete article matches that have no relevance score (unscored) for a keyword group.
        These are articles that were collected but never processed for relevance.
        """
        # Join with articles to check for NULL keyword_relevance_score
        statement = delete(keyword_article_matches).where(
            keyword_article_matches.c.group_id == group_id,
            keyword_article_matches.c.article_uri.in_(
                select(articles.c.uri).where(
                    or_(
                        articles.c.keyword_relevance_score == None,
                        articles.c.keyword_relevance_score == 0
                    )
                )
            )
        )
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
            func.coalesce(keyword_monitor_settings.c.default_llm_model, "gpt-5.4-mini").label("default_llm_model"),
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
                default_llm_model="gpt-5.4",
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

    def get_keyword_group_by_id(self, group_id):
        """Get keyword group details by ID"""
        statement = select(
            keyword_groups.c.id,
            keyword_groups.c.name,
            keyword_groups.c.topic
        ).where(
            keyword_groups.c.id == group_id
        )

        result = self._execute_with_rollback(statement).mappings().fetchone()
        return dict(result) if result else None

    def get_all_keyword_groups(self):
        """Get all keyword groups."""
        statement = select(
            keyword_groups.c.id,
            keyword_groups.c.name,
            keyword_groups.c.topic,
            keyword_groups.c.created_at,
            keyword_groups.c.provider,
            keyword_groups.c.source
        ).order_by(keyword_groups.c.name)
        return self._execute_with_rollback(statement).mappings().fetchall()

    def get_articles_for_keyword_group(self, group_id: int, limit: int = 20):
        """Get recent articles matched to a specific keyword group.

        Returns articles with all enrichment fields including explanations.
        """
        query = text("""
            SELECT DISTINCT
                kam.id,
                a.uri,
                a.title,
                a.news_source as source,
                a.publication_date,
                kam.detected_at,
                a.keyword_relevance_score,
                a.topic_alignment_score,
                a.overall_match_explanation,
                a.category,
                a.summary,
                a.sentiment,
                a.sentiment_explanation,
                a.time_to_impact,
                a.time_to_impact_explanation,
                a.driver_type,
                a.driver_type_explanation
            FROM keyword_article_matches kam
            JOIN articles a ON kam.article_uri = a.uri
            WHERE kam.group_id = :group_id
            ORDER BY kam.detected_at DESC
            LIMIT :limit
        """)
        result = self._execute_with_rollback(query, {'group_id': group_id, 'limit': limit})
        return result.mappings().fetchall()

    def get_group_article_stats(self, group_id: int, relevance_threshold: float = 0.39):
        """Get article statistics for a keyword group including time-based counts.

        Returns dict with:
        - total_count: total articles collected for this group
        - relevant_count: articles that passed relevance scoring (>= threshold)
        - irrelevant_count: articles that didn't pass relevance scoring (< threshold)
        - unscored_count: articles without any relevance score (for troubleshooting)
        - articles_past_week: count of articles added in past 7 days
        - articles_past_month: count of articles added in past 30 days
        - daily_counts: list of (date, count) tuples for sparkline (past 30 days)
        """
        query = text("""
            SELECT
                COUNT(*) as total_count,
                COUNT(CASE WHEN a.keyword_relevance_score >= :threshold THEN 1 END) as relevant_count,
                COUNT(CASE WHEN a.keyword_relevance_score IS NOT NULL AND a.keyword_relevance_score < :threshold THEN 1 END) as irrelevant_count,
                COUNT(CASE WHEN a.keyword_relevance_score IS NULL THEN 1 END) as unscored_count,
                COUNT(CASE WHEN kam.detected_at::timestamp >= NOW() - INTERVAL '24 hours' THEN 1 END) as articles_past_24h,
                COUNT(CASE WHEN kam.detected_at::timestamp >= NOW() - INTERVAL '7 days' THEN 1 END) as articles_past_week,
                COUNT(CASE WHEN kam.detected_at::timestamp >= NOW() - INTERVAL '30 days' THEN 1 END) as articles_past_month
            FROM keyword_article_matches kam
            JOIN articles a ON kam.article_uri = a.uri
            WHERE kam.group_id = :group_id
        """)
        result = self._execute_with_rollback(query, {'group_id': group_id, 'threshold': relevance_threshold})
        row = result.mappings().fetchone()

        # Get daily counts for sparkline
        daily_query = text("""
            SELECT
                DATE(kam.detected_at::timestamp) as date,
                COUNT(*) as count
            FROM keyword_article_matches kam
            WHERE kam.group_id = :group_id
              AND kam.detected_at::timestamp >= NOW() - INTERVAL '30 days'
            GROUP BY DATE(kam.detected_at::timestamp)
            ORDER BY date
        """)
        daily_result = self._execute_with_rollback(daily_query, {'group_id': group_id})
        daily_counts = [(str(r['date']), r['count']) for r in daily_result.mappings().fetchall()]

        return {
            'total_count': row['total_count'] if row else 0,
            'relevant_count': row['relevant_count'] if row else 0,
            'irrelevant_count': row['irrelevant_count'] if row else 0,
            'unscored_count': row['unscored_count'] if row else 0,
            'articles_past_24h': row['articles_past_24h'] if row else 0,
            'articles_past_week': row['articles_past_week'] if row else 0,
            'articles_past_month': row['articles_past_month'] if row else 0,
            'daily_counts': daily_counts,
        }

    def get_group_last_run_stats(self, group_id: int):
        """Get stats from the last collection run for a keyword group.

        Returns dict with saved/not_saved counts from the most recent collection.
        """
        # Get the most recent detected_at timestamp for this group
        last_run_query = text("""
            SELECT MAX(detected_at::timestamp) as last_run
            FROM keyword_article_matches
            WHERE group_id = :group_id
        """)
        last_run_result = self._execute_with_rollback(last_run_query, {'group_id': group_id})
        last_run_row = last_run_result.mappings().fetchone()

        if not last_run_row or not last_run_row['last_run']:
            return {'last_run_saved': 0, 'last_run_not_saved': 0}

        # Get articles from the last run (within 1 hour of most recent)
        stats_query = text("""
            SELECT
                COUNT(CASE WHEN a.category IS NOT NULL AND a.category != '' THEN 1 END) as saved_count,
                COUNT(CASE WHEN a.category IS NULL OR a.category = '' THEN 1 END) as not_saved_count
            FROM keyword_article_matches kam
            JOIN articles a ON kam.article_uri = a.uri
            WHERE kam.group_id = :group_id
              AND kam.detected_at::timestamp >= CAST(:last_run AS timestamp) - INTERVAL '1 hour'
        """)
        result = self._execute_with_rollback(stats_query, {
            'group_id': group_id,
            'last_run': last_run_row['last_run']
        })
        row = result.mappings().fetchone()

        return {
            'last_run_saved': row['saved_count'] if row else 0,
            'last_run_not_saved': row['not_saved_count'] if row else 0,
        }

    # =========================================================================
    # Per-Group Collection Settings Methods
    # =========================================================================

    def get_keyword_group_with_settings(self, group_id: int):
        """Get keyword group with all collection settings columns.

        Returns dict with all group fields including per-group settings.
        """
        query = text("""
            SELECT
                id, name, topic, created_at, provider, source,
                is_active, check_interval, interval_unit, search_date_range,
                providers, social_platforms, auto_ingest_enabled, min_relevance_threshold,
                quality_control_enabled, auto_save_approved_only,
                default_llm_model, llm_temperature, llm_max_tokens,
                last_checked_at, next_check_at, last_error, updated_at
            FROM keyword_groups
            WHERE id = :group_id
        """)
        result = self._execute_with_rollback(query, {'group_id': group_id})
        row = result.mappings().fetchone()
        return dict(row) if row else None

    def get_effective_group_settings(self, group_id: int):
        """Get effective settings for a group, merging with global defaults.

        Returns dict with effective settings where NULL values are replaced
        with global defaults. Also indicates which settings are custom vs inherited.
        """
        # Get group settings
        group = self.get_keyword_group_with_settings(group_id)
        if not group:
            return None

        # Get global settings
        global_settings = self.get_or_create_keyword_monitor_settings()

        # Define which settings to merge and their global key mappings
        setting_keys = {
            'check_interval': 'check_interval',
            'interval_unit': 'interval_unit',
            'search_date_range': 'search_date_range',
            'providers': 'providers',
            'social_platforms': 'social_platforms',
            'auto_ingest_enabled': 'auto_ingest_enabled',
            'min_relevance_threshold': 'min_relevance_threshold',
            'quality_control_enabled': 'quality_control_enabled',
            'auto_save_approved_only': 'auto_save_approved_only',
            'default_llm_model': 'default_llm_model',
            'llm_temperature': 'llm_temperature',
            'llm_max_tokens': 'llm_max_tokens',
        }

        # Build effective settings
        effective = {
            'id': group['id'],
            'name': group['name'],
            'topic': group['topic'],
            'is_active': group.get('is_active', True),
            'last_checked_at': group.get('last_checked_at'),
            'next_check_at': group.get('next_check_at'),
            'last_error': group.get('last_error'),
            'updated_at': group.get('updated_at'),
            'settings': {},
            'custom_fields': [],  # List of fields with custom (non-null) values
        }

        for group_key, global_key in setting_keys.items():
            group_value = group.get(group_key)
            global_value = global_settings.get(global_key) if global_settings else None

            # Use group value if set, otherwise fall back to global
            if group_value is not None:
                effective['settings'][group_key] = group_value
                effective['custom_fields'].append(group_key)
            else:
                effective['settings'][group_key] = global_value

        # Determine if group has custom schedule or providers
        effective['has_custom_schedule'] = any(
            group.get(k) is not None for k in ['check_interval', 'interval_unit']
        )
        effective['has_custom_providers'] = group.get('providers') is not None

        return effective

    def update_keyword_group_settings(self, group_id: int, settings: dict):
        """Update per-group collection settings.

        Args:
            group_id: The keyword group ID
            settings: Dict of settings to update. Set values to None to use global defaults.
                      Supports 'use_global_settings': True to reset all to NULL.

        Returns:
            True if update succeeded, False otherwise.
        """
        # If resetting to global defaults
        if settings.get('use_global_settings'):
            query = text("""
                UPDATE keyword_groups
                SET check_interval = NULL,
                    interval_unit = NULL,
                    search_date_range = NULL,
                    providers = NULL,
                    social_platforms = NULL,
                    auto_ingest_enabled = NULL,
                    min_relevance_threshold = NULL,
                    quality_control_enabled = NULL,
                    auto_save_approved_only = NULL,
                    default_llm_model = NULL,
                    llm_temperature = NULL,
                    llm_max_tokens = NULL,
                    updated_at = NOW()
                WHERE id = :group_id
            """)
            self._execute_with_rollback(query, {'group_id': group_id})
            return True

        # Build dynamic update
        allowed_fields = [
            'is_active', 'check_interval', 'interval_unit', 'search_date_range',
            'providers', 'social_platforms', 'auto_ingest_enabled', 'min_relevance_threshold',
            'quality_control_enabled', 'auto_save_approved_only',
            'default_llm_model', 'llm_temperature', 'llm_max_tokens',
        ]

        update_parts = []
        params = {'group_id': group_id}

        for field in allowed_fields:
            if field in settings:
                update_parts.append(f"{field} = :{field}")
                params[field] = settings[field]

        if not update_parts:
            return False

        update_parts.append("updated_at = NOW()")
        query = text(f"""
            UPDATE keyword_groups
            SET {', '.join(update_parts)}
            WHERE id = :group_id
        """)
        self._execute_with_rollback(query, params)
        return True

    def get_due_keyword_groups(self):
        """Get keyword groups that are due for checking based on their schedules.

        Returns list of groups where now >= next_check_at or where next_check_at is NULL
        and enough time has passed since last_checked_at (or never checked).
        Groups must be active.
        """
        query = text("""
            SELECT
                kg.id, kg.name, kg.topic, kg.is_active,
                kg.check_interval, kg.interval_unit, kg.search_date_range,
                kg.providers, kg.social_platforms, kg.auto_ingest_enabled, kg.min_relevance_threshold,
                kg.quality_control_enabled, kg.auto_save_approved_only,
                kg.default_llm_model, kg.llm_temperature, kg.llm_max_tokens,
                kg.last_checked_at, kg.next_check_at, kg.last_error,
                -- Get global defaults for fallback
                kms.check_interval as global_check_interval,
                kms.interval_unit as global_interval_unit
            FROM keyword_groups kg
            CROSS JOIN (SELECT * FROM keyword_monitor_settings WHERE id = 1) kms
            WHERE kg.is_active = TRUE
              AND (
                  -- Group has custom schedule and is due
                  (kg.next_check_at IS NOT NULL AND kg.next_check_at <= NOW())
                  OR
                  -- Group has never been checked
                  (kg.last_checked_at IS NULL)
                  OR
                  -- Group was checked but next_check_at not set - calculate from interval
                  (kg.next_check_at IS NULL AND kg.last_checked_at IS NOT NULL
                   AND kg.last_checked_at + (
                       COALESCE(kg.check_interval, kms.check_interval) *
                       COALESCE(kg.interval_unit, kms.interval_unit) * INTERVAL '1 second'
                   ) <= NOW())
              )
            ORDER BY kg.last_checked_at NULLS FIRST
        """)
        result = self._execute_with_rollback(query)
        return [dict(row) for row in result.mappings().fetchall()]

    def update_keyword_group_check_status(self, group_id: int, error: str = None, next_check_seconds: int = None):
        """Update group's check status after a collection run.

        Args:
            group_id: The keyword group ID
            error: Error message if the check failed, None if successful
            next_check_seconds: Seconds until next check (calculated from group/global interval)

        Updates last_checked_at, next_check_at, and last_error.
        """
        if next_check_seconds is not None:
            query = text("""
                UPDATE keyword_groups
                SET last_checked_at = NOW(),
                    next_check_at = NOW() + (:next_seconds * INTERVAL '1 second'),
                    last_error = :error,
                    updated_at = NOW()
                WHERE id = :group_id
            """)
            params = {
                'group_id': group_id,
                'error': error,
                'next_seconds': next_check_seconds,
            }
        else:
            # Calculate next check from group or global settings
            query = text("""
                UPDATE keyword_groups
                SET last_checked_at = NOW(),
                    next_check_at = NOW() + (
                        COALESCE(check_interval, (SELECT check_interval FROM keyword_monitor_settings WHERE id = 1)) *
                        COALESCE(interval_unit, (SELECT interval_unit FROM keyword_monitor_settings WHERE id = 1)) *
                        INTERVAL '1 second'
                    ),
                    last_error = :error,
                    updated_at = NOW()
                WHERE id = :group_id
            """)
            params = {'group_id': group_id, 'error': error}

        self._execute_with_rollback(query, params)

    def get_all_keyword_groups_with_schedule_info(self):
        """Get all keyword groups with schedule info for API listing.

        Returns groups with has_custom_schedule, has_custom_providers, last_checked_at, next_check_at.
        """
        query = text("""
            SELECT
                kg.id, kg.name, kg.topic, kg.created_at, kg.provider, kg.source,
                kg.is_active, kg.last_checked_at, kg.next_check_at, kg.last_error,
                kg.check_interval IS NOT NULL OR kg.interval_unit IS NOT NULL as has_custom_schedule,
                kg.providers IS NOT NULL as has_custom_providers
            FROM keyword_groups kg
            ORDER BY kg.name
        """)
        result = self._execute_with_rollback(query)
        return [dict(row) for row in result.mappings().fetchall()]

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

    def update_article_fields(self, uri: str, fields: dict) -> int:
        """
        Update specific fields on an article by URI.

        Args:
            uri: Article URI
            fields: Dictionary of field names to values to update

        Returns:
            Number of rows updated
        """
        if not fields:
            return 0

        statement = update(articles).where(articles.c.uri == uri).values(**fields)
        result = self._execute_with_rollback(statement)
        self.connection.commit()
        return result.rowcount

    def get_article_by_uri(self, uri: str):
        """Get article by URI (alias for get_article_by_url)."""
        return self.get_article_by_url(uri)

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
                'ingest_status', 'auto_ingested', 'article_origin',
                'opoint_entities'
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

        # Normalize null/empty categories and sentiments
        for article in articles_list:
            if not article.get('category') or article.get('category') in ('None', 'null', ''):
                article['category'] = 'Uncategorized'
            if not article.get('sentiment') or article.get('sentiment') in ('None', 'null', ''):
                article['sentiment'] = 'Unknown'

        return articles_list, total_count

    def get_recent_articles_by_topic(self, topic_name=None, limit=10, start_date=None, end_date=None):
        """Fetch recent articles for a topic - SQLAlchemy version.

        If topic_name is None (cross-topic mode), returns articles from all topics.
        """
        from sqlalchemy import case, cast, Date
        import logging
        logger = logging.getLogger(__name__)

        if topic_name:
            logger.info(f"Database: Fetching {limit} recent articles for topic {topic_name} (date range: {start_date} to {end_date})")
        else:
            logger.info(f"Database: Fetching {limit} recent articles across ALL topics (date range: {start_date} to {end_date})")

        # Build WHERE conditions (topic filter optional for cross-topic mode)
        conditions = []
        if topic_name:
            conditions.append(articles.c.topic == topic_name)

        # COALESCE for date ordering
        coalesce_date = func.coalesce(articles.c.submission_date, articles.c.publication_date)

        # Cast to DATE for proper comparison (handles timestamps vs date strings)
        if start_date:
            conditions.append(cast(coalesce_date, Date) >= start_date)
        if end_date:
            conditions.append(cast(coalesce_date, Date) <= end_date)

        # Build query
        # Note: PostgreSQL doesn't have rowid, so we only order by date
        if conditions:
            query = select(articles).where(
                and_(*conditions)
            ).order_by(
                desc(coalesce_date)
            ).limit(limit)
        else:
            # No conditions - query all articles (cross-topic mode)
            query = select(articles).order_by(
                desc(coalesce_date)
            ).limit(limit)

        logger.debug(f"Executing query: {query}")
        result = self._execute_with_rollback(query).mappings().fetchall()
        articles_list = [dict(row) for row in result]
        logger.info(f"Found {len(articles_list)} articles in database")

        # Convert tags string back to list and normalize null values
        for article in articles_list:
            if article['tags']:
                article['tags'] = article['tags'].split(',')
            else:
                article['tags'] = []
            # Normalize null/empty categories and sentiments
            if not article.get('category') or article.get('category') in ('None', 'null', ''):
                article['category'] = 'Uncategorized'
            if not article.get('sentiment') or article.get('sentiment') in ('None', 'null', ''):
                article['sentiment'] = 'Unknown'

        return articles_list

    def get_articles_with_bias_data(self, topic_name=None, limit=500, days_back=30):
        """Fetch recent articles that have bias data populated.

        Args:
            topic_name: Optional topic filter. None for cross-topic (all topics).
            limit: Maximum number of articles to return.
            days_back: How many days back to search.

        Returns:
            List of article dicts with bias data.
        """
        from sqlalchemy import cast, Date
        import logging
        logger = logging.getLogger(__name__)

        start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')

        if topic_name:
            logger.info(f"Database: Fetching {limit} articles with bias data for topic {topic_name}")
        else:
            logger.info(f"Database: Fetching {limit} articles with bias data across ALL topics")

        # Build WHERE conditions - must have bias data
        conditions = [
            articles.c.bias.isnot(None),
            articles.c.bias != ''
        ]

        if topic_name:
            conditions.append(articles.c.topic == topic_name)

        # Date filter
        coalesce_date = func.coalesce(articles.c.submission_date, articles.c.publication_date)
        conditions.append(cast(coalesce_date, Date) >= start_date)

        # Build query
        query = select(articles).where(
            and_(*conditions)
        ).order_by(
            desc(coalesce_date)
        ).limit(limit)

        logger.debug(f"Executing bias articles query")
        result = self._execute_with_rollback(query).mappings().fetchall()
        articles_list = [dict(row) for row in result]
        logger.info(f"Found {len(articles_list)} articles with bias data")

        return articles_list

    def get_articles_with_future_signals(self, topic_name=None, limit=500, days_back=30):
        """Fetch articles that have future impact data (future_signal, time_to_impact, strong sentiment).

        Prioritizes articles with:
        - Non-null future_signal values (not 'None' or empty)
        - time_to_impact data
        - Strong sentiment (Negative, Positive, Critical - not just Neutral)

        Args:
            topic_name: Optional topic filter. None for cross-topic (all topics).
            limit: Maximum number of articles to return.
            days_back: How many days back to search.

        Returns:
            List of article dicts with future impact data.
        """
        from sqlalchemy import cast, Date
        import logging
        logger = logging.getLogger(__name__)

        start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')

        if topic_name:
            logger.info(f"Database: Fetching {limit} articles with future signals for topic {topic_name}")
        else:
            logger.info(f"Database: Fetching {limit} articles with future signals across ALL topics")

        # Build WHERE conditions - must have future_signal data
        conditions = [
            articles.c.future_signal.isnot(None),
            articles.c.future_signal != '',
            articles.c.future_signal != 'None'
        ]

        if topic_name:
            conditions.append(articles.c.topic == topic_name)

        # Date filter
        coalesce_date = func.coalesce(articles.c.submission_date, articles.c.publication_date)
        conditions.append(cast(coalesce_date, Date) >= start_date)

        # Build query - order by recency
        query = select(articles).where(
            and_(*conditions)
        ).order_by(
            desc(coalesce_date)
        ).limit(limit)

        logger.debug(f"Executing future signals articles query")
        result = self._execute_with_rollback(query).mappings().fetchall()
        articles_list = [dict(row) for row in result]
        logger.info(f"Found {len(articles_list)} articles with future signal data")

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
        # Filter out NULL and empty string categories
        where_conditions.extend([
            articles.c.category.isnot(None),
            articles.c.category != '',
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
            # IMPORTANT: Topic names can contain commas (e.g., "Religion, Magic and Occultism")
            # Only split on " | " delimiter for multiple topics, NOT on commas
            if ' | ' in topic:
                # Multiple topics separated by " | "
                topics = [t.strip() for t in topic.split(' | ') if t.strip()]
                topic_conditions = []
                for t in topics:
                    topic_pattern = f"%{t}%"
                    topic_conditions.append(
                        or_(
                            articles.c.topic == t,
                            articles.c.title.like(topic_pattern),
                            articles.c.summary.like(topic_pattern)
                        )
                    )
                # Combine all topic conditions with OR
                where_conditions.append(or_(*topic_conditions))
            else:
                # Single topic - treat entire string as one topic
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
            # Sort by date first (newest day first), then by quality within each day
            # This ensures today's articles always appear before yesterday's
            articles.c.publication_date.desc(),
            factual_reporting_order.desc(),
            news_source_order.desc()
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
        # Filter out NULL and empty string categories
        where_conditions.extend([
            articles.c.category.isnot(None),
            articles.c.category != '',
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
            # Handle comma-separated multiple topics
            topics = [t.strip() for t in topic.split(',') if t.strip()]

            if len(topics) == 1:
                # Single topic - use existing logic
                topic_pattern = f"%{topics[0]}%"
                where_conditions.append(
                    or_(
                        articles.c.topic == topics[0],
                        articles.c.title.like(topic_pattern),
                        articles.c.summary.like(topic_pattern)
                    )
                )
            elif len(topics) > 1:
                # Multiple topics - create OR condition for each topic
                topic_conditions = []
                for t in topics:
                    topic_pattern = f"%{t}%"
                    topic_conditions.append(
                        or_(
                            articles.c.topic == t,
                            articles.c.title.like(topic_pattern),
                            articles.c.summary.like(topic_pattern)
                        )
                    )
                # Combine all topic conditions with OR
                where_conditions.append(or_(*topic_conditions))

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

    def get_news_feed_articles_chronological(
        self,
        start_date: str = None,
        end_date: str = None,
        topic: str = None,
        offset: int = 0,
        limit: int = 25
    ) -> List[Dict]:
        """
        Get articles sorted by publication date (newest first) without clustering.

        Returns a flat list of enriched articles sorted chronologically.
        Only returns articles with category and sentiment set.

        Args:
            start_date: Start date string (YYYY-MM-DD HH:MM:SS) or None for all
            end_date: End date string (YYYY-MM-DD HH:MM:SS)
            topic: Optional topic filter
            offset: Number of articles to skip (for pagination)
            limit: Maximum number of articles to return

        Returns:
            List of article dictionaries sorted by publication_date DESC
        """
        # Build WHERE conditions
        where_conditions = []

        # Date range filter
        if start_date and end_date:
            where_conditions.append(
                and_(
                    articles.c.publication_date >= start_date,
                    articles.c.publication_date <= end_date
                )
            )
        elif end_date:
            where_conditions.append(articles.c.publication_date <= end_date)

        # Required filters - only show enriched articles
        where_conditions.extend([
            articles.c.publication_date.isnot(None),
            articles.c.category.isnot(None),
            articles.c.category != '',
            articles.c.sentiment.isnot(None)
        ])

        # Spam/promotional content filters
        where_conditions.extend([
            not_(articles.c.title.like('%Call@%')),
            not_(articles.c.title.like('%+91%')),
            not_(articles.c.title.like('%best%agency%')),
            not_(articles.c.title.like('%#1%')),
            not_(articles.c.summary.like('%Call@%')),
            not_(articles.c.summary.like('%phone%number%')),
            not_(articles.c.news_source.like('%medium.com/@%'))
        ])

        # Topic filter
        if topic:
            if ' | ' in topic:
                # Multiple topics separated by " | "
                topics = [t.strip() for t in topic.split(' | ') if t.strip()]
                topic_conditions = []
                for t in topics:
                    topic_pattern = f"%{t}%"
                    topic_conditions.append(
                        or_(
                            articles.c.topic == t,
                            articles.c.title.like(topic_pattern),
                            articles.c.summary.like(topic_pattern)
                        )
                    )
                where_conditions.append(or_(*topic_conditions))
            else:
                topic_pattern = f"%{topic}%"
                where_conditions.append(
                    or_(
                        articles.c.topic == topic,
                        articles.c.title.like(topic_pattern),
                        articles.c.summary.like(topic_pattern)
                    )
                )

        # Build query - simple ORDER BY publication_date DESC
        statement = select(
            articles.c.uri,
            articles.c.title,
            articles.c.summary,
            articles.c.news_source,
            articles.c.publication_date,
            articles.c.category,
            articles.c.topic,
            articles.c.sentiment,
            articles.c.time_to_impact,
            articles.c.tags,
            articles.c.bias,
            articles.c.factual_reporting,
            articles.c.mbfc_credibility_rating,
            articles.c.bias_country,
            articles.c.user_preference,
        ).where(
            and_(*where_conditions)
        ).order_by(
            articles.c.publication_date.desc()
        ).offset(offset).limit(limit)

        # Execute and return results
        results = self._execute_with_rollback(statement).mappings().fetchall()

        articles_list = []
        for row in results:
            article_dict = dict(row)
            articles_list.append(article_dict)

        return articles_list

    def get_news_feed_articles_chronological_count(
        self,
        start_date: str = None,
        end_date: str = None,
        topic: str = None
    ) -> int:
        """
        Get count of articles for chronological list view.

        Args:
            start_date: Start date string (YYYY-MM-DD HH:MM:SS) or None for all
            end_date: End date string (YYYY-MM-DD HH:MM:SS)
            topic: Optional topic filter

        Returns:
            Integer count of matching articles
        """
        # Build WHERE conditions (same as chronological query)
        where_conditions = []

        if start_date and end_date:
            where_conditions.append(
                and_(
                    articles.c.publication_date >= start_date,
                    articles.c.publication_date <= end_date
                )
            )
        elif end_date:
            where_conditions.append(articles.c.publication_date <= end_date)

        where_conditions.extend([
            articles.c.publication_date.isnot(None),
            articles.c.category.isnot(None),
            articles.c.category != '',
            articles.c.sentiment.isnot(None)
        ])

        where_conditions.extend([
            not_(articles.c.title.like('%Call@%')),
            not_(articles.c.title.like('%+91%')),
            not_(articles.c.title.like('%best%agency%')),
            not_(articles.c.title.like('%#1%')),
            not_(articles.c.summary.like('%Call@%')),
            not_(articles.c.summary.like('%phone%number%')),
            not_(articles.c.news_source.like('%medium.com/@%'))
        ])

        if topic:
            if ' | ' in topic:
                topics = [t.strip() for t in topic.split(' | ') if t.strip()]
                topic_conditions = []
                for t in topics:
                    topic_pattern = f"%{t}%"
                    topic_conditions.append(
                        or_(
                            articles.c.topic == t,
                            articles.c.title.like(topic_pattern),
                            articles.c.summary.like(topic_pattern)
                        )
                    )
                where_conditions.append(or_(*topic_conditions))
            else:
                topic_pattern = f"%{topic}%"
                where_conditions.append(
                    or_(
                        articles.c.topic == topic,
                        articles.c.title.like(topic_pattern),
                        articles.c.summary.like(topic_pattern)
                    )
                )

        statement = select(
            func.count()
        ).select_from(
            articles
        ).where(
            and_(*where_conditions)
        )

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
                # Convert schedule_time to string if it exists
                schedule_time_str = None
                if row.get('schedule_time'):
                    schedule_time_str = row['schedule_time'].strftime('%H:%M') if hasattr(row['schedule_time'], 'strftime') else str(row['schedule_time'])

                instructions.append({
                    'id': row['id'],
                    'name': row['name'],
                    'description': row['description'],
                    'instruction': row['instruction'],
                    'topic': row['topic'],
                    'is_active': bool(row['is_active']),
                    'generate_report': bool(row.get('generate_report', False)),
                    'report_prompt': row.get('report_prompt'),
                    'config': row.get('config'),
                    'created_at': row['created_at'],
                    'updated_at': row['updated_at'],
                    # Schedule fields
                    'schedule_enabled': bool(row.get('schedule_enabled', False)),
                    'schedule_type': row.get('schedule_type'),
                    'schedule_interval': row.get('schedule_interval'),
                    'schedule_unit': row.get('schedule_unit'),
                    'schedule_time': schedule_time_str,
                    'last_run_at': row.get('last_run_at').isoformat() if row.get('last_run_at') else None,
                    'next_run_at': row.get('next_run_at').isoformat() if row.get('next_run_at') else None,
                    'last_run_status': row.get('last_run_status'),
                    'last_run_error': row.get('last_run_error'),
                    'run_count': row.get('run_count', 0)
                })
            return instructions
        except Exception as e:
            self.logger.error(f"Error getting signal instructions: {e}")
            return []

    def save_signal_instruction(self, name: str, description: str, instruction: str,
                               topic: str = None, is_active: bool = True,
                               generate_report: bool = False, report_prompt: str = None,
                               config: dict = None, schedule_enabled: bool = False,
                               schedule_type: str = None, schedule_interval: int = None,
                               schedule_unit: str = None, schedule_time: str = None) -> bool:
        """Save a custom signal instruction for threat hunting.

        Args:
            name: Unique name for the instruction
            description: Description of what the signal detects
            instruction: The instruction text for the AI
            topic: Optional topic to associate with
            is_active: Whether the instruction is active
            generate_report: Whether to generate reports when matches are found
            report_prompt: Custom prompt for report generation
            config: Additional configuration (e.g., model selection)
            schedule_enabled: Whether scheduling is enabled
            schedule_type: 'interval' or 'daily'
            schedule_interval: Interval value
            schedule_unit: 'minutes', 'hours', or 'days'
            schedule_time: Time for daily schedules (HH:MM)

        Returns:
            True if successfully saved, False otherwise
        """
        try:
            # Convert schedule_time string to time object if provided
            schedule_time_obj = None
            if schedule_time:
                try:
                    from datetime import time as dt_time
                    parts = schedule_time.split(':')
                    schedule_time_obj = dt_time(int(parts[0]), int(parts[1]))
                except (ValueError, IndexError):
                    pass

            # Calculate next_run_at if scheduling is enabled
            next_run_at = None
            if schedule_enabled:
                from app.tasks.observer_agent_monitor import calculate_next_run
                next_run_at = calculate_next_run(
                    schedule_type=schedule_type or 'interval',
                    schedule_interval=schedule_interval,
                    schedule_unit=schedule_unit,
                    schedule_time=schedule_time_obj
                )

            # PostgreSQL uses INSERT ... ON CONFLICT instead of INSERT OR REPLACE
            query = """
            INSERT INTO signal_instructions (name, description, instruction, topic, is_active,
                generate_report, report_prompt, config, schedule_enabled, schedule_type,
                schedule_interval, schedule_unit, schedule_time, next_run_at, updated_at)
            VALUES (:name, :description, :instruction, :topic, :is_active,
                :generate_report, :report_prompt, :config, :schedule_enabled, :schedule_type,
                :schedule_interval, :schedule_unit, :schedule_time, :next_run_at, CURRENT_TIMESTAMP)
            ON CONFLICT (name) DO UPDATE SET
                description = :description,
                instruction = :instruction,
                topic = :topic,
                is_active = :is_active,
                generate_report = :generate_report,
                report_prompt = :report_prompt,
                config = :config,
                schedule_enabled = :schedule_enabled,
                schedule_type = :schedule_type,
                schedule_interval = :schedule_interval,
                schedule_unit = :schedule_unit,
                schedule_time = :schedule_time,
                next_run_at = :next_run_at,
                updated_at = CURRENT_TIMESTAMP
            """
            self._execute_with_rollback(text(query), {
                'name': name,
                'description': description,
                'instruction': instruction,
                'topic': topic,
                'is_active': is_active,
                'generate_report': generate_report,
                'report_prompt': report_prompt,
                'config': json.dumps(config) if config else None,
                'schedule_enabled': schedule_enabled,
                'schedule_type': schedule_type,
                'schedule_interval': schedule_interval,
                'schedule_unit': schedule_unit,
                'schedule_time': schedule_time_obj,
                'next_run_at': next_run_at
            })
            self.connection.commit()
            self.logger.info(f"Saved signal instruction: {name}")
            return True
        except Exception as e:
            self.logger.error(f"Error saving signal instruction: {e}")
            return False

    def update_signal_instruction(self, instruction_id: int, name: str = None,
                                  description: str = None, instruction: str = None,
                                  topic: str = None, is_active: bool = None,
                                  generate_report: bool = None, report_prompt: str = None,
                                  config: dict = None, schedule_enabled: bool = None,
                                  schedule_type: str = None, schedule_interval: int = None,
                                  schedule_unit: str = None, schedule_time: str = None) -> bool:
        """Update a signal instruction by ID.

        Args:
            instruction_id: ID of the instruction to update
            name: New name (optional)
            description: New description (optional)
            instruction: New instruction text (optional)
            topic: New topic (optional)
            is_active: New active status (optional)
            generate_report: Whether to generate reports (optional)
            report_prompt: Custom report prompt (optional)
            config: Additional configuration (optional)
            schedule_enabled: Whether scheduling is enabled (optional)
            schedule_type: 'interval' or 'daily' (optional)
            schedule_interval: Interval value (optional)
            schedule_unit: 'minutes', 'hours', or 'days' (optional)
            schedule_time: Time for daily schedules HH:MM (optional)

        Returns:
            True if successfully updated, False otherwise
        """
        try:
            # Build dynamic update query based on provided fields
            updates = []
            params = {'instruction_id': instruction_id}

            if name is not None:
                updates.append("name = :name")
                params['name'] = name
            if description is not None:
                updates.append("description = :description")
                params['description'] = description
            if instruction is not None:
                updates.append("instruction = :instruction")
                params['instruction'] = instruction
            if topic is not None:
                updates.append("topic = :topic")
                params['topic'] = topic if topic else None
            if is_active is not None:
                updates.append("is_active = :is_active")
                params['is_active'] = is_active
            if generate_report is not None:
                updates.append("generate_report = :generate_report")
                params['generate_report'] = generate_report
            if report_prompt is not None:
                updates.append("report_prompt = :report_prompt")
                params['report_prompt'] = report_prompt if report_prompt else None
            if config is not None:
                updates.append("config = :config")
                params['config'] = json.dumps(config) if config else None

            # Schedule fields
            if schedule_enabled is not None:
                updates.append("schedule_enabled = :schedule_enabled")
                params['schedule_enabled'] = schedule_enabled
            if schedule_type is not None:
                updates.append("schedule_type = :schedule_type")
                params['schedule_type'] = schedule_type
            if schedule_interval is not None:
                updates.append("schedule_interval = :schedule_interval")
                params['schedule_interval'] = schedule_interval
            if schedule_unit is not None:
                updates.append("schedule_unit = :schedule_unit")
                params['schedule_unit'] = schedule_unit
            if schedule_time is not None:
                # Convert schedule_time string to time object
                schedule_time_obj = None
                if schedule_time:
                    try:
                        from datetime import time as dt_time
                        parts = schedule_time.split(':')
                        schedule_time_obj = dt_time(int(parts[0]), int(parts[1]))
                    except (ValueError, IndexError):
                        pass
                updates.append("schedule_time = :schedule_time")
                params['schedule_time'] = schedule_time_obj

            # Recalculate next_run_at if scheduling changed
            if schedule_enabled is not None or schedule_type is not None or \
               schedule_interval is not None or schedule_unit is not None or schedule_time is not None:
                # Get current values to calculate next_run
                from app.tasks.observer_agent_monitor import calculate_next_run
                from datetime import time as dt_time

                # Use provided values or get current from DB
                current = self._execute_with_rollback(text(
                    "SELECT schedule_enabled, schedule_type, schedule_interval, schedule_unit, schedule_time FROM signal_instructions WHERE id = :id"
                ), {'id': instruction_id}).mappings().first()

                if current:
                    sch_enabled = schedule_enabled if schedule_enabled is not None else current['schedule_enabled']
                    sch_type = schedule_type if schedule_type is not None else current['schedule_type']
                    sch_interval = schedule_interval if schedule_interval is not None else current['schedule_interval']
                    sch_unit = schedule_unit if schedule_unit is not None else current['schedule_unit']
                    sch_time = params.get('schedule_time') if schedule_time is not None else current['schedule_time']

                    if sch_enabled:
                        next_run_at = calculate_next_run(
                            schedule_type=sch_type or 'interval',
                            schedule_interval=sch_interval,
                            schedule_unit=sch_unit,
                            schedule_time=sch_time
                        )
                        updates.append("next_run_at = :next_run_at")
                        params['next_run_at'] = next_run_at
                    else:
                        updates.append("next_run_at = NULL")

            if not updates:
                return True  # Nothing to update

            updates.append("updated_at = CURRENT_TIMESTAMP")

            query = f"""
            UPDATE signal_instructions
            SET {', '.join(updates)}
            WHERE id = :instruction_id
            """
            result = self._execute_with_rollback(text(query), params)
            self.connection.commit()
            updated = result.rowcount > 0
            if updated:
                self.logger.info(f"Updated signal instruction ID: {instruction_id}")
            return updated
        except Exception as e:
            self.logger.error(f"Error updating signal instruction {instruction_id}: {e}")
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
                         threat_level: str, summary: str,
                         reasoning: str = None) -> Optional[int]:
        """Save a signal alert.

        Args:
            article_uri: URI of the article
            instruction_id: ID of the signal instruction
            instruction_name: Name of the signal instruction
            confidence: Confidence score (0.0 to 1.0)
            threat_level: Threat level (e.g., 'low', 'medium', 'high', 'critical')
            summary: Summary of the alert
            reasoning: Explanation of why this article was flagged

        Returns:
            ID of the created alert, or None if failed
        """
        try:
            query = """
            INSERT INTO signal_alerts
            (article_uri, instruction_id, instruction_name, confidence, threat_level, summary, reasoning)
            VALUES (:article_uri, :instruction_id, :instruction_name, :confidence, :threat_level, :summary, :reasoning)
            ON CONFLICT (article_uri, instruction_id) DO UPDATE SET
                confidence = :confidence,
                threat_level = :threat_level,
                summary = :summary,
                reasoning = :reasoning,
                detected_at = CURRENT_TIMESTAMP
            RETURNING id
            """
            result = self._execute_with_rollback(text(query), {
                'article_uri': article_uri,
                'instruction_id': instruction_id,
                'instruction_name': instruction_name,
                'confidence': confidence,
                'threat_level': threat_level,
                'summary': summary,
                'reasoning': reasoning
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

    def update_auspex_chat_metadata(self, chat_id: int, metadata: dict) -> bool:
        """
        Update metadata for an Auspex chat session.

        Metadata can include compaction stats, context quality metrics, etc.

        Args:
            chat_id: The chat session ID
            metadata: Dictionary of metadata to store/update

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get existing metadata
            result = self._execute_with_rollback(
                select(auspex_chats.c.metadata)
                .where(auspex_chats.c.id == chat_id)
            ).fetchone()

            existing_metadata = {}
            if result and result[0]:
                try:
                    existing_metadata = json.loads(result[0]) if isinstance(result[0], str) else result[0]
                except:
                    existing_metadata = {}

            # Merge with new metadata
            existing_metadata.update(metadata)

            self._execute_with_rollback(
                update(auspex_chats)
                .where(auspex_chats.c.id == chat_id)
                .values(
                    metadata=json.dumps(existing_metadata),
                    updated_at=func.now()
                )
            )
            self.connection.commit()
            return True
        except Exception as e:
            self.logger.error(f"Error updating auspex chat metadata: {e}")
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

    def get_latest_cached_trend_analysis_for_topic(self, topic: str):
        """Get the most recent cached trend analysis for a topic, regardless of cache key."""
        try:
            statement = select(
                analysis_versions_v2.c.version_data,
                analysis_versions_v2.c.created_at
            ).where(
                analysis_versions_v2.c.topic == topic
            ).order_by(
                analysis_versions_v2.c.created_at.desc()
            ).limit(1)

            result = self._execute_with_rollback(statement).mappings().fetchone()
            return result
        except Exception as e:
            self.logger.error(f"Error getting latest cached trend analysis for topic: {e}")
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

    def get_first_user_with_six_articles_config(self) -> Optional[Dict]:
        """Get first user who has a Six Articles configuration saved"""
        try:
            query = text("""
                SELECT DISTINCT u.username
                FROM users u
                INNER JOIN user_preferences up ON u.username = up.username
                WHERE up.preference_key = 'six_articles_config'
                LIMIT 1
            """)

            result = self.connection.execute(query).fetchone()

            if result:
                return {
                    'username': result[0],
                    'user_id': result[0]  # username is the user_id in this schema
                }

            return None

        except Exception as e:
            self.logger.error(f"Error getting first user with Six Articles config: {e}")
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
            if self.db.db_type == 'postgresql':
                query = text("""
                    INSERT INTO user_preferences (username, preference_key, config_value, updated_at)
                    VALUES (:username, 'six_articles_config', CAST(:config_json AS json), NOW())
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
    # Incident Status Methods
    # ==========================================

    def update_incident_status(self, incident_name: str, topic: str, status: str) -> bool:
        """Update or create incident status."""
        conn = None
        try:
            conn = self.connection
            if self.db.db_type == 'postgresql':
                query = text("""
                    INSERT INTO incident_status (incident_name, topic, status, updated_at)
                    VALUES (:incident_name, :topic, :status, NOW())
                    ON CONFLICT (incident_name, topic) DO UPDATE SET
                        status = EXCLUDED.status,
                        updated_at = NOW()
                """)
            else:
                query = text("""
                    INSERT OR REPLACE INTO incident_status (incident_name, topic, status, updated_at)
                    VALUES (:incident_name, :topic, :status, datetime('now'))
                """)

            conn.execute(query, {
                "incident_name": incident_name,
                "topic": topic,
                "status": status
            })
            conn.commit()
            self.logger.info(f"Updated incident status: {incident_name} -> {status}")
            return True
        except Exception as e:
            self.logger.error(f"Error updating incident status: {e}")
            if conn:
                conn.rollback()
            return False

    def get_incident_statuses(self, topic: str) -> Dict[str, str]:
        """Get all incident statuses for a topic. Returns dict of {incident_name: status}."""
        try:
            conn = self.connection
            query = text("""
                SELECT incident_name, status FROM incident_status
                WHERE topic = :topic AND status != 'deleted'
            """)
            result = conn.execute(query, {"topic": topic})
            return {row[0]: row[1] for row in result.fetchall()}
        except Exception as e:
            self.logger.error(f"Error getting incident statuses: {e}")
            return {}

    # ==========================================
    # User Preference Methods
    # ==========================================

    def get_user_preference(self, username: str, preference_key: str) -> Optional[Dict]:
        """Get a user preference value by key."""
        try:
            conn = self.connection
            query = text("""
                SELECT config_value FROM user_preferences
                WHERE username = :username AND preference_key = :preference_key
            """)
            result = conn.execute(query, {
                "username": username,
                "preference_key": preference_key
            })
            row = result.fetchone()
            if row:
                import json
                return json.loads(row[0]) if isinstance(row[0], str) else row[0]
            return None
        except Exception as e:
            self.logger.error(f"Error getting user preference: {e}")
            return None

    def set_user_preference(self, username: str, preference_key: str, value: Dict) -> bool:
        """Set a user preference value."""
        conn = None
        try:
            import json
            conn = self.connection
            json_value = json.dumps(value)

            if self.db.db_type == 'postgresql':
                query = text("""
                    INSERT INTO user_preferences (username, preference_key, config_value, created_at, updated_at)
                    VALUES (:username, :preference_key, :config_value, NOW(), NOW())
                    ON CONFLICT (username, preference_key) DO UPDATE SET
                        config_value = EXCLUDED.config_value,
                        updated_at = NOW()
                """)
            else:
                query = text("""
                    INSERT OR REPLACE INTO user_preferences (username, preference_key, config_value, updated_at)
                    VALUES (:username, :preference_key, :config_value, datetime('now'))
                """)

            conn.execute(query, {
                "username": username,
                "preference_key": preference_key,
                "config_value": json_value
            })
            conn.commit()
            return True
        except Exception as e:
            self.logger.error(f"Error setting user preference: {e}")
            if conn:
                conn.rollback()
            raise  # Re-raise to allow caller to see the actual error

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

    # Forecast Assessment Storage Methods
    def save_forecast_assessment(
        self,
        assessment_id: str,
        run_id: str,
        topic: str,
        evidence_count: int,
        scenarios_count: int,
        ambiguous_count: int,
        unrelated_count: int,
        surprises: list,
        summary: dict,
        status: str = "completed",
        mode: str = "live",
        model_used: str = None,
        runtime_seconds: float = None,
        config: dict = None,
    ) -> bool:
        """Insert a forecast_assessments row.

        Returns True on success, False otherwise. Caller writes scenario and
        article verdict rows separately via the helpers below.
        """
        try:
            from app.database_models import t_forecast_assessments
            from sqlalchemy import insert
            import json

            stmt = insert(t_forecast_assessments).values(
                id=assessment_id,
                run_id=run_id,
                topic=topic,
                evidence_count=evidence_count,
                scenarios_count=scenarios_count,
                ambiguous_count=ambiguous_count,
                unrelated_count=unrelated_count,
                surprises=json.dumps(surprises) if surprises is not None else None,
                summary=json.dumps(summary) if summary is not None else None,
                status=status,
                mode=mode,
                model_used=model_used,
                runtime_seconds=runtime_seconds,
                config=json.dumps(config) if config is not None else None,
            )
            self._execute_with_rollback(stmt)
            self.logger.info(f"Saved forecast assessment {assessment_id} for run {run_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error saving forecast assessment: {e}")
            return False

    def save_forecast_scenario_verdicts(self, assessment_id: str, rows: list) -> bool:
        """Bulk-insert per-scenario verdict rows. `rows` items match the
        forecast_scenario_verdicts column set."""
        if not rows:
            return True
        try:
            from app.database_models import t_forecast_scenario_verdicts
            from sqlalchemy import insert
            import json

            payload = []
            for r in rows:
                top_articles = r.get("top_articles") or {}
                # Stash optional deck_info inside the top_articles JSONB so we
                # don't need an extra column. Keys live alongside supports/
                # contradicts; the UI can look for them.
                if r.get("deck_info"):
                    top_articles = {**top_articles, "deck_info": r["deck_info"]}
                payload.append({
                    "assessment_id": assessment_id,
                    "scenario_idx": r["scenario_idx"],
                    "horizon_type": r["horizon_type"],
                    "scenario_title": r["scenario_title"],
                    "verdict_label": r["verdict_label"],
                    "directional_rate": r.get("directional_rate"),
                    "velocity": r.get("velocity"),
                    "milestone_density": r.get("milestone_density"),
                    "coverage": r.get("coverage"),
                    "supports": r.get("supports", 0),
                    "contradicts": r.get("contradicts", 0),
                    "neutral": r.get("neutral", 0),
                    "summary_md": r.get("summary_md"),
                    "top_articles": json.dumps(top_articles) if top_articles else None,
                    "current_consensus_pct": r.get("current_consensus_pct"),
                    "synthesis": (
                        json.dumps(r["synthesis"]) if r.get("synthesis") else None
                    ),
                })
            self._execute_with_rollback(insert(t_forecast_scenario_verdicts), payload)
            return True
        except Exception as e:
            self.logger.error(f"Error saving scenario verdicts: {e}")
            return False

    def save_forecast_article_verdicts(self, assessment_id: str, rows: list) -> bool:
        """Bulk-insert per-article verdict rows."""
        if not rows:
            return True
        try:
            from app.database_models import t_forecast_article_verdicts
            from sqlalchemy import insert

            payload = []
            for r in rows:
                payload.append({
                    "assessment_id": assessment_id,
                    "article_uri": r["article_uri"],
                    "scenario_idx": r.get("scenario_idx"),
                    "verdict": r["verdict"],
                    "evidence_type": r.get("evidence_type"),
                    "confidence": r.get("confidence"),
                    "rerank_score": r.get("rerank_score"),
                    "margin": r.get("margin"),
                    "best_alt_scenario_idx": r.get("best_alt_scenario_idx"),
                    "rationale": r.get("rationale"),
                    "article_date": r.get("article_date"),
                })
            self._execute_with_rollback(insert(t_forecast_article_verdicts), payload)
            return True
        except Exception as e:
            self.logger.error(f"Error saving article verdicts: {e}")
            return False

    def get_latest_forecast_assessment(self, run_id: str) -> dict:
        """Return the most recent assessment for a horizons run, including
        per-scenario verdicts. Returns {} if none.

        Prefer ``mode='live'`` over ``placebo``: in paired runs the placebo
        is saved second (more recent) but only the live row gets the
        ``baseline_correction`` block patched onto its summary. Picking the
        live row keeps the UI showing the canonical baseline-corrected view.
        """
        try:
            from app.database_models import (
                t_forecast_assessments,
                t_forecast_scenario_verdicts,
            )
            from sqlalchemy import select, case
            import json

            live_priority = case(
                (t_forecast_assessments.c.mode == "live", 0),
                else_=1,
            )
            a_stmt = (
                select(t_forecast_assessments)
                .where(t_forecast_assessments.c.run_id == run_id)
                .order_by(
                    live_priority.asc(),
                    t_forecast_assessments.c.assessed_at.desc(),
                )
                .limit(1)
            )
            row = self._execute_with_rollback(a_stmt).fetchone()
            if not row:
                return {}
            assessment = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)

            for key in ("surprises", "summary", "config"):
                # Loop-parse to survive double-encoded JSONB (see
                # get_prior_live_assessment for the full rationale).
                v = assessment.get(key)
                for _ in range(3):
                    if not isinstance(v, str):
                        break
                    try:
                        v = json.loads(v)
                    except Exception:
                        break
                assessment[key] = v

            v_stmt = (
                select(t_forecast_scenario_verdicts)
                .where(t_forecast_scenario_verdicts.c.assessment_id == assessment["id"])
                .order_by(t_forecast_scenario_verdicts.c.scenario_idx.asc())
            )
            verdicts = []
            for vr in self._execute_with_rollback(v_stmt).fetchall():
                vd = dict(vr._mapping) if hasattr(vr, "_mapping") else dict(vr)
                ta = vd.get("top_articles")
                if isinstance(ta, str):
                    try:
                        vd["top_articles"] = json.loads(ta)
                    except Exception:
                        pass
                verdicts.append(vd)
            assessment["scenario_verdicts"] = verdicts
            return assessment
        except Exception as e:
            self.logger.error(f"Error getting latest forecast assessment for run {run_id}: {e}")
            return {}

    def get_forecast_assessment_snapshots(self, topic: str, mode: str = "live", limit: int = 52) -> list:
        """Return chronological list of assessments for a topic with extracted
        per-scenario ``net_rate`` series. Used by the snapshot history UI to
        plot each scenario's net rate over time across paired-mode reruns.

        Only ``mode='live'`` rows have the ``baseline_correction`` block
        patched into their summary, so we filter to live by default.
        """
        try:
            from app.database_models import t_forecast_assessments
            from sqlalchemy import select
            import json

            stmt = (
                select(
                    t_forecast_assessments.c.id,
                    t_forecast_assessments.c.run_id,
                    t_forecast_assessments.c.assessed_at,
                    t_forecast_assessments.c.evidence_count,
                    t_forecast_assessments.c.summary,
                    t_forecast_assessments.c.surprises,
                )
                .where(t_forecast_assessments.c.topic == topic)
                .where(t_forecast_assessments.c.mode == mode)
                .where(t_forecast_assessments.c.status == "completed")
                .order_by(t_forecast_assessments.c.assessed_at.asc())
                .limit(limit)
            )
            rows = self._execute_with_rollback(stmt).fetchall()
            out = []
            for r in rows:
                rd = dict(r._mapping) if hasattr(r, "_mapping") else dict(r)
                for key in ("summary", "surprises"):
                    v = rd.get(key)
                    if isinstance(v, str):
                        try:
                            rd[key] = json.loads(v)
                        except Exception:
                            pass
                summary = rd.get("summary") or {}
                bc = (summary.get("baseline_correction") or {})
                per = (bc.get("per_scenario") or {})
                # Flatten to ``[{scenario_idx, label, net_rate, live_rate, placebo_rate}]``
                series = [
                    {
                        "scenario_idx": int(k),
                        "label": v.get("label"),
                        "net_rate": v.get("net_rate"),
                        "live_rate": v.get("live_rate"),
                        "placebo_rate": v.get("placebo_rate"),
                        "live_supports": v.get("live_supports"),
                        "placebo_supports": v.get("placebo_supports"),
                    }
                    for k, v in per.items()
                ]
                surprises = rd.get("surprises") or []
                surprises_count = len(surprises) if isinstance(surprises, list) else 0
                out.append(
                    {
                        "assessment_id": rd["id"],
                        "run_id": rd["run_id"],
                        "assessed_at": rd["assessed_at"].isoformat() if hasattr(rd["assessed_at"], "isoformat") else str(rd["assessed_at"]),
                        "evidence_count": rd.get("evidence_count"),
                        "window_weeks": summary.get("window_weeks"),
                        "per_scenario": series,
                        "surprises_count": surprises_count,
                    }
                )
            return out
        except Exception as e:
            self.logger.error(f"Error getting forecast assessment snapshots for topic {topic}: {e}")
            return []

    def get_latest_forecast_assessment_by_topic(self, topic: str) -> dict:
        """Same as get_latest_forecast_assessment but keyed by topic instead of
        run_id. Lets the UI surface assessments tied to an older horizons run
        even when the current trend-convergence page has freshly generated a
        different run for the same topic.

        Skips assessments with zero ``forecast_scenario_verdicts`` rows —
        those are aborted/empty runs (e.g. when a build pipeline returned
        a horizons run with no parseable scenarios) and would render a
        blank Strategic Domains card if picked. The most recent
        *populated* assessment is preferred.
        """
        try:
            from sqlalchemy import text as sa_text

            # Most recent live+completed assessment for this topic that
            # actually has scenario verdicts. Filtering by an EXISTS
            # sub-query keeps the query plan cheap.
            id_stmt = sa_text("""
                SELECT a.run_id
                FROM forecast_assessments a
                WHERE a.topic = :topic
                  AND a.mode = 'live' AND a.status = 'completed'
                  AND EXISTS (
                      SELECT 1 FROM forecast_scenario_verdicts v
                      WHERE v.assessment_id = a.id
                  )
                ORDER BY a.assessed_at DESC
                LIMIT 1
            """)
            row = self._execute_with_rollback(id_stmt, {"topic": topic}).fetchone()
            if not row:
                # Fall back to ANY latest assessment so a topic that's never
                # had a populated run still surfaces something rather than
                # silently disappearing from the bundle. The bundle's empty-
                # state stub will render in that case.
                fallback = sa_text("""
                    SELECT run_id FROM forecast_assessments
                    WHERE topic = :topic
                    ORDER BY (mode = 'live') DESC, assessed_at DESC
                    LIMIT 1
                """)
                row = self._execute_with_rollback(fallback, {"topic": topic}).fetchone()
                if not row:
                    return {}
            run_id = row[0] if not hasattr(row, "_mapping") else row._mapping["run_id"]
            return self.get_latest_forecast_assessment(run_id)
        except Exception as e:
            self.logger.error(f"Error getting latest forecast assessment for topic {topic}: {e}")
            return {}

    def get_forecast_article_verdicts(self, assessment_id: str, scenario_idx: int = None) -> list:
        """Return article verdicts for an assessment, optionally filtered to a single scenario."""
        try:
            from app.database_models import t_forecast_article_verdicts
            from sqlalchemy import select

            stmt = select(t_forecast_article_verdicts).where(
                t_forecast_article_verdicts.c.assessment_id == assessment_id
            )
            if scenario_idx is not None:
                stmt = stmt.where(t_forecast_article_verdicts.c.scenario_idx == scenario_idx)
            rows = self._execute_with_rollback(stmt).fetchall()
            return [dict(r._mapping) if hasattr(r, "_mapping") else dict(r) for r in rows]
        except Exception as e:
            self.logger.error(f"Error getting article verdicts: {e}")
            return []

    def get_prior_live_assessment(self, run_id: str, before_assessed_at,
                                  topic: str = None) -> dict:
        """Return the live-mode assessment immediately preceding
        ``before_assessed_at`` for the topic, including its per-scenario
        verdicts and article verdicts.

        The lookup is keyed by **topic**, not by ``run_id``. Every fresh
        Three Horizons run produces a new ``run_id``, so a run-keyed
        prior-lookup would treat each new horizons run as a clean slate
        and the bundle would emit the "no prior snapshot" stub for every
        topic that has ever had its forecast regenerated. ``run_id``
        remains a fallback when ``topic`` isn't supplied (call sites
        gradually migrating).
        """
        try:
            from app.database_models import (
                t_forecast_assessments,
                t_forecast_scenario_verdicts,
                t_forecast_article_verdicts,
            )
            from sqlalchemy import select
            import json

            # Resolve the topic from the run if the caller didn't pass it.
            # ``run_id`` is preserved as a fallback path so old callers
            # don't break — but new code should pass ``topic`` explicitly.
            if not topic and run_id:
                try:
                    from app.database_models import t_future_horizons_runs
                    run_stmt = select(t_future_horizons_runs.c.topic).where(
                        t_future_horizons_runs.c.id == run_id
                    )
                    run_row = self._execute_with_rollback(run_stmt).fetchone()
                    if run_row:
                        topic = run_row[0]
                except Exception as e:
                    self.logger.warning(
                        "Could not resolve topic for run_id=%s: %s", run_id, e
                    )

            stmt = (
                select(t_forecast_assessments)
                .where(t_forecast_assessments.c.mode == "live")
                .where(t_forecast_assessments.c.status == "completed")
                .where(t_forecast_assessments.c.assessed_at < before_assessed_at)
            )
            if topic:
                stmt = stmt.where(t_forecast_assessments.c.topic == topic)
            else:
                # Last-ditch: filter on run_id alone if no topic could be
                # resolved. This preserves the old behaviour for the rare
                # edge case where the run row is missing.
                stmt = stmt.where(t_forecast_assessments.c.run_id == run_id)
            stmt = (stmt
                    .order_by(t_forecast_assessments.c.assessed_at.desc())
                    .limit(1))
            row = self._execute_with_rollback(stmt).fetchone()
            if not row:
                return {}
            a = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
            for key in ("surprises", "summary", "config"):
                # Loop-parse to survive double-encoded JSONB: a value stored
                # as json.dumps() of an already-stringified object decodes to
                # a *string* on the first json.loads, and a later `.get()` on
                # it raises "'str' object has no attribute 'get'". Decode
                # until it's no longer a string (cap at 3 to avoid loops).
                v = a.get(key)
                for _ in range(3):
                    if not isinstance(v, str):
                        break
                    try:
                        v = json.loads(v)
                    except Exception:
                        break
                a[key] = v

            v_stmt = (
                select(t_forecast_scenario_verdicts)
                .where(t_forecast_scenario_verdicts.c.assessment_id == a["id"])
                .order_by(t_forecast_scenario_verdicts.c.scenario_idx.asc())
            )
            verdicts = []
            for vr in self._execute_with_rollback(v_stmt).fetchall():
                vd = dict(vr._mapping) if hasattr(vr, "_mapping") else dict(vr)
                ta = vd.get("top_articles")
                if isinstance(ta, str):
                    try:
                        vd["top_articles"] = json.loads(ta)
                    except Exception:
                        pass
                verdicts.append(vd)
            a["scenario_verdicts"] = verdicts

            uri_stmt = (
                select(t_forecast_article_verdicts.c.article_uri)
                .where(t_forecast_article_verdicts.c.assessment_id == a["id"])
            )
            a["article_uris"] = [
                (r[0] if not hasattr(r, "_mapping") else r._mapping["article_uri"])
                for r in self._execute_with_rollback(uri_stmt).fetchall()
            ]
            return a
        except Exception as e:
            self.logger.error(f"Error getting prior live assessment for run {run_id}: {e}")
            return {}

    # Forecast user scenarios (addendum scenarios promoted from surprise clusters)
    def save_forecast_user_scenario(
        self,
        run_id: str,
        title: str,
        description: str,
        horizon_type: str,
        timeframe: str = None,
        source_assessment_id: str = None,
        source_surprise_label: str = None,
        source_article_uris: list = None,
    ) -> str:
        """Insert a user-promoted scenario for the given forecast run.

        Returns the new scenario id. The assessment service concatenates
        these with the original ``raw_output['scenarios']`` at run time.
        """
        try:
            from app.database_models import t_forecast_user_scenarios
            from sqlalchemy import insert
            import uuid

            scenario_id = str(uuid.uuid4())
            stmt = insert(t_forecast_user_scenarios).values(
                id=scenario_id,
                run_id=run_id,
                title=title,
                description=description,
                horizon_type=horizon_type,
                timeframe=timeframe,
                source_assessment_id=source_assessment_id,
                source_surprise_label=source_surprise_label,
                source_article_uris=source_article_uris or [],
            )
            self._execute_with_rollback(stmt)
            try:
                self.session.commit()
            except Exception:
                pass
            return scenario_id
        except Exception as e:
            self.logger.error(f"Error saving forecast user scenario for run {run_id}: {e}")
            raise

    def get_forecast_user_scenarios(self, run_id: str) -> list:
        """Return all addendum scenarios for a forecast run, oldest first."""
        try:
            from app.database_models import t_forecast_user_scenarios
            from sqlalchemy import select
            import json

            stmt = (
                select(t_forecast_user_scenarios)
                .where(t_forecast_user_scenarios.c.run_id == run_id)
                .order_by(t_forecast_user_scenarios.c.created_at.asc())
            )
            rows = self._execute_with_rollback(stmt).fetchall()
            out = []
            for r in rows:
                rd = dict(r._mapping) if hasattr(r, "_mapping") else dict(r)
                ua = rd.get("source_article_uris")
                if isinstance(ua, str):
                    try:
                        rd["source_article_uris"] = json.loads(ua)
                    except Exception:
                        pass
                ca = rd.get("created_at")
                if hasattr(ca, "isoformat"):
                    rd["created_at"] = ca.isoformat()
                out.append(rd)
            return out
        except Exception as e:
            self.logger.error(f"Error getting forecast user scenarios for run {run_id}: {e}")
            return []

    # Forecast scenario status (mark-as-done overlay)
    def save_forecast_scenario_status(
        self,
        run_id: str,
        *,
        scenario_idx: int = None,
        user_scenario_id: str = None,
        status: str = "done",
        note: str = None,
    ) -> dict:
        """Upsert a scenario status row.

        Exactly one of ``scenario_idx`` (originals) or ``user_scenario_id``
        (addendums) must be supplied. Returns the persisted row.
        """
        if (scenario_idx is None) == (user_scenario_id is None):
            raise ValueError("Exactly one of scenario_idx or user_scenario_id required")
        try:
            from app.database_models import t_forecast_scenario_status
            from sqlalchemy import select, insert, update
            from datetime import datetime, timezone

            marked_at = datetime.now(timezone.utc) if status == "done" else None

            # Postgres treats NULL as DISTINCT in unique constraints, so
            # ``ON CONFLICT (run_id, scenario_idx, user_scenario_id)`` with one
            # of the columns NULL won't fire. We do an explicit existence
            # check + UPDATE/INSERT instead.
            sel = (
                select(t_forecast_scenario_status)
                .where(t_forecast_scenario_status.c.run_id == run_id)
            )
            if scenario_idx is not None:
                sel = sel.where(
                    t_forecast_scenario_status.c.scenario_idx == scenario_idx,
                    t_forecast_scenario_status.c.user_scenario_id.is_(None),
                )
            else:
                sel = sel.where(
                    t_forecast_scenario_status.c.user_scenario_id == user_scenario_id,
                    t_forecast_scenario_status.c.scenario_idx.is_(None),
                )
            existing = self._execute_with_rollback(sel).fetchone()

            if existing is None:
                stmt = insert(t_forecast_scenario_status).values(
                    run_id=run_id,
                    scenario_idx=scenario_idx,
                    user_scenario_id=user_scenario_id,
                    status=status,
                    marked_done_at=marked_at,
                    note=note,
                )
                self._execute_with_rollback(stmt)
            else:
                ex = dict(existing._mapping) if hasattr(existing, "_mapping") else dict(existing)
                stmt = (
                    update(t_forecast_scenario_status)
                    .where(t_forecast_scenario_status.c.id == ex["id"])
                    .values(status=status, marked_done_at=marked_at, note=note)
                )
                self._execute_with_rollback(stmt)
            try:
                self.session.commit()
            except Exception:
                pass

            row = self._execute_with_rollback(sel).fetchone()
            if not row:
                return {}
            rd = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
            ma = rd.get("marked_done_at")
            if hasattr(ma, "isoformat"):
                rd["marked_done_at"] = ma.isoformat()
            return rd
        except Exception as e:
            self.logger.error(f"Error saving forecast scenario status: {e}")
            raise

    def get_forecast_scenario_statuses(self, run_id: str) -> dict:
        """Return active status overlays for a run.

        Returns ``{"originals": {scenario_idx: status_dict},
                    "addendums": {user_scenario_id: status_dict}}``.
        """
        out = {"originals": {}, "addendums": {}}
        try:
            from app.database_models import t_forecast_scenario_status
            from sqlalchemy import select

            stmt = (
                select(t_forecast_scenario_status)
                .where(t_forecast_scenario_status.c.run_id == run_id)
            )
            for r in self._execute_with_rollback(stmt).fetchall():
                rd = dict(r._mapping) if hasattr(r, "_mapping") else dict(r)
                ma = rd.get("marked_done_at")
                if hasattr(ma, "isoformat"):
                    rd["marked_done_at"] = ma.isoformat()
                if rd.get("scenario_idx") is not None:
                    out["originals"][rd["scenario_idx"]] = rd
                elif rd.get("user_scenario_id"):
                    out["addendums"][rd["user_scenario_id"]] = rd
            return out
        except Exception as e:
            self.logger.error(f"Error getting forecast scenario statuses for run {run_id}: {e}")
            return out

    # Forecast topic delivery config (Wiley monthly/quarterly cadence)
    def get_forecast_topic_delivery_configs(self) -> list:
        """Return all configured delivery topics with cadence + recipient + last sent."""
        try:
            from app.database_models import t_forecast_topic_delivery
            from sqlalchemy import select

            stmt = (
                select(t_forecast_topic_delivery)
                .order_by(t_forecast_topic_delivery.c.topic.asc())
            )
            out = []
            for r in self._execute_with_rollback(stmt).fetchall():
                rd = dict(r._mapping) if hasattr(r, "_mapping") else dict(r)
                for k in ("last_delivered_at", "updated_at"):
                    v = rd.get(k)
                    if hasattr(v, "isoformat"):
                        rd[k] = v.isoformat()
                out.append(rd)
            return out
        except Exception as e:
            self.logger.error(f"Error getting forecast topic delivery configs: {e}")
            return []

    def upsert_forecast_topic_delivery_config(
        self, topic: str, cadence: str, recipient_email: str = None
    ) -> dict:
        """Set cadence + recipient for a topic. Cadence: monthly|quarterly|none."""
        cadence = (cadence or "none").lower()
        if cadence not in ("monthly", "quarterly", "none"):
            raise ValueError(f"Invalid cadence '{cadence}'")
        try:
            from app.database_models import t_forecast_topic_delivery
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            from sqlalchemy import select, text as sa_text

            stmt = pg_insert(t_forecast_topic_delivery).values(
                topic=topic,
                cadence=cadence,
                recipient_email=recipient_email,
            ).on_conflict_do_update(
                index_elements=["topic"],
                set_={
                    "cadence": cadence,
                    "recipient_email": recipient_email,
                    "updated_at": sa_text("NOW()"),
                },
            )
            self._execute_with_rollback(stmt)
            try:
                self.session.commit()
            except Exception:
                pass
            sel = select(t_forecast_topic_delivery).where(
                t_forecast_topic_delivery.c.topic == topic
            )
            row = self._execute_with_rollback(sel).fetchone()
            if not row:
                return {}
            rd = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
            for k in ("last_delivered_at", "updated_at"):
                v = rd.get(k)
                if hasattr(v, "isoformat"):
                    rd[k] = v.isoformat()
            return rd
        except Exception as e:
            self.logger.error(f"Error upserting forecast topic delivery config for {topic}: {e}")
            raise

    # ── Topic metadata (forecast_topic_metadata) ──────────────────────────
    # Sidecar that powers the Topics dashboard. Keyed by topic string to
    # match the rest of the forecast tables; renames remain a known wart
    # (see plan §1).

    def get_forecast_topic_metadata(self, topic: str) -> dict:
        try:
            from app.database_models import t_forecast_topic_metadata
            from sqlalchemy import select

            stmt = select(t_forecast_topic_metadata).where(
                t_forecast_topic_metadata.c.topic == topic
            )
            row = self._execute_with_rollback(stmt).fetchone()
            if not row:
                return {}
            rd = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
            for k in ("created_at", "updated_at"):
                v = rd.get(k)
                if hasattr(v, "isoformat"):
                    rd[k] = v.isoformat()
            return rd
        except Exception as e:
            self.logger.error(f"Error getting topic metadata for {topic}: {e}")
            return {}

    def upsert_forecast_topic_metadata(
        self, topic: str, *,
        display_name: str = None,
        description: str = None,
        owner: str = None,
        status: str = None,
        tags: list = None,
        overlay_status: str = None,
        source_topics: list = None,
    ) -> dict:
        """Upsert a topic metadata row. Only supplied fields are updated;
        omitted fields keep their existing values (or defaults on insert)."""
        try:
            from app.database_models import t_forecast_topic_metadata
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            from sqlalchemy import select, text as sa_text
            import json

            # Validate constrained values when set.
            if status is not None and status not in ("draft", "active", "archived"):
                raise ValueError(f"Invalid status '{status}'")
            if overlay_status is not None and overlay_status not in (
                "missing", "auto_generated", "human_reviewed"
            ):
                raise ValueError(f"Invalid overlay_status '{overlay_status}'")

            insert_values = {"topic": topic}
            for field, value in (
                ("display_name", display_name),
                ("description", description),
                ("owner", owner),
                ("status", status),
                ("overlay_status", overlay_status),
            ):
                if value is not None:
                    insert_values[field] = value
            # tags is JSONB — pass the python list directly so psycopg's
            # JSON adapter stores it as a JSONB array (not a JSONB string).
            if tags is not None:
                insert_values["tags"] = tags
            # source_topics is JSONB too — same direct-list handling.
            if source_topics is not None:
                insert_values["source_topics"] = source_topics

            update_values = {k: v for k, v in insert_values.items() if k != "topic"}
            update_values["updated_at"] = sa_text("NOW()")

            stmt = pg_insert(t_forecast_topic_metadata).values(**insert_values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["topic"], set_=update_values,
            )
            self._execute_with_rollback(stmt)
            try:
                self.session.commit()
            except Exception:
                pass
            return self.get_forecast_topic_metadata(topic)
        except Exception as e:
            self.logger.error(f"Error upserting topic metadata for {topic}: {e}")
            raise

    def list_topics_with_lifecycle(self) -> list:
        """Return one merged row per known topic — joining metadata,
        delivery config, and latest assessment. The dashboard's single
        source of truth.

        Topics are surfaced if they appear in ANY of:
        - forecast_topic_metadata (explicit registration)
        - forecast_topic_delivery (configured for delivery)
        - forecast_assessments mode='live' status='completed' (has data)
        """
        try:
            from sqlalchemy import text as sa_text
            sql = sa_text("""
                WITH topics AS (
                    SELECT topic FROM forecast_topic_metadata
                    UNION
                    SELECT topic FROM forecast_topic_delivery
                    UNION
                    SELECT DISTINCT topic FROM forecast_assessments
                    WHERE mode = 'live' AND status = 'completed'
                ),
                latest_assess AS (
                    SELECT DISTINCT ON (topic)
                        topic,
                        id        AS assessment_id,
                        assessed_at,
                        evidence_count,
                        scenarios_count,
                        surprises,
                        summary,
                        config
                    FROM forecast_assessments
                    WHERE mode = 'live' AND status = 'completed'
                    ORDER BY topic, assessed_at DESC
                )
                SELECT
                    t.topic,
                    m.display_name,
                    m.description,
                    m.owner,
                    COALESCE(m.status, 'active')         AS status,
                    m.tags,
                    m.source_topics,
                    COALESCE(m.overlay_status, 'missing') AS overlay_status,
                    m.created_at,
                    m.updated_at,
                    d.cadence,
                    d.recipient_email,
                    d.last_delivered_at,
                    la.assessment_id,
                    la.assessed_at,
                    la.evidence_count,
                    la.scenarios_count,
                    la.surprises,
                    la.summary
                FROM topics t
                LEFT JOIN forecast_topic_metadata m ON m.topic = t.topic
                LEFT JOIN forecast_topic_delivery  d ON d.topic = t.topic
                LEFT JOIN latest_assess            la ON la.topic = t.topic
                ORDER BY t.topic ASC
            """)
            rows = self._execute_with_rollback(sql).fetchall()
            out = []
            for r in rows:
                rd = dict(r._mapping) if hasattr(r, "_mapping") else dict(r)
                for k in ("created_at", "updated_at", "last_delivered_at", "assessed_at"):
                    v = rd.get(k)
                    if hasattr(v, "isoformat"):
                        rd[k] = v.isoformat()
                out.append(rd)
            return out
        except Exception as e:
            self.logger.error(f"Error listing topics with lifecycle: {e}")
            return []

    # --- Topic Candidates (inbox) ----------------------------------------

    def upsert_topic_candidate(
        self, *,
        emerging_topic_id: int,
        org_profile_id: int,
        relevance_verdict: str,
        relevance_score: float = None,
        relevance_rationale: str = None,
        proposed_topic_name: str = None,
        proposed_description: str = None,
        proposed_tags: list = None,
    ) -> int:
        """Insert (or update on conflict) a candidate row keyed by
        (emerging_topic_id, org_profile_id). off_scope verdicts are
        auto-rejected at insert so they never surface in the inbox.

        Returns the candidate id.
        """
        try:
            from app.database_models import t_topic_candidates
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            from sqlalchemy import text as sa_text, select

            if relevance_verdict not in ("in_scope", "adjacent", "off_scope"):
                raise ValueError(f"Invalid relevance_verdict '{relevance_verdict}'")

            insert_values = {
                "emerging_topic_id": emerging_topic_id,
                "org_profile_id": org_profile_id,
                "relevance_verdict": relevance_verdict,
            }
            for field, value in (
                ("relevance_score", relevance_score),
                ("relevance_rationale", relevance_rationale),
                ("proposed_topic_name", proposed_topic_name),
                ("proposed_description", proposed_description),
            ):
                if value is not None:
                    insert_values[field] = value
            if proposed_tags is not None:
                insert_values["proposed_tags"] = proposed_tags  # python list -> JSONB array

            # off_scope candidates are auto-rejected so they never appear
            # in the analyst inbox. Analysts can still see them via the
            # 'rejected' filter for audit purposes.
            if relevance_verdict == "off_scope":
                insert_values["triage_status"] = "rejected"
                insert_values["rejected_reason"] = "off_scope (auto)"

            update_values = {k: v for k, v in insert_values.items()
                             if k not in ("emerging_topic_id", "org_profile_id")}
            update_values["updated_at"] = sa_text("NOW()")

            stmt = pg_insert(t_topic_candidates).values(**insert_values)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_topic_candidates_topic_profile",
                set_=update_values,
            ).returning(t_topic_candidates.c.id)
            row = self._execute_with_rollback(stmt).fetchone()
            try:
                self.session.commit()
            except Exception:
                pass
            return int(row[0]) if row else None
        except Exception as e:
            self.logger.error(f"Error upserting candidate (et={emerging_topic_id}): {e}")
            raise

    def list_topic_candidates(
        self, *,
        triage_status: str = "pending",
        min_score: float = 0.0,
        org_profile_id: int = None,
        include_emerging: bool = True,
    ) -> list:
        """List candidates joined with their underlying emerging-topic row.
        Ordered by relevance_score * composite_score DESC (best signal first).

        ``triage_status='all'`` returns every row regardless of status.
        """
        try:
            from sqlalchemy import text as sa_text
            where = ["1=1"]
            params = {}
            if triage_status and triage_status != "all":
                where.append("tc.triage_status = :status")
                params["status"] = triage_status
            if min_score is not None and min_score > 0:
                where.append("COALESCE(tc.relevance_score, 0) >= :min_score")
                params["min_score"] = float(min_score)
            if org_profile_id is not None:
                where.append("tc.org_profile_id = :opid")
                params["opid"] = int(org_profile_id)
            # Hide snoozed rows whose snooze window has elapsed only when the
            # caller specifically asked for snoozed — the sweeper unsnoozes
            # them on its own tick.
            sql = sa_text(f"""
                SELECT
                    tc.id,
                    tc.emerging_topic_id,
                    tc.org_profile_id,
                    tc.relevance_verdict,
                    tc.relevance_score,
                    tc.relevance_rationale,
                    tc.proposed_topic_name,
                    tc.proposed_description,
                    tc.proposed_tags,
                    tc.triage_status,
                    tc.snooze_until,
                    tc.rejected_reason,
                    tc.promoted_to_topic,
                    tc.triaged_by,
                    tc.triaged_at,
                    tc.created_at,
                    tc.updated_at,
                    et.topic_label,
                    et.topic_description,
                    et.article_count,
                    et.growth_rate,
                    et.velocity,
                    et.avg_novelty_score,
                    et.confidence_score AS et_confidence,
                    et.key_themes,
                    et.representative_keywords,
                    et.sample_article_uris,
                    et.detection_date,
                    et.detection_type
                FROM topic_candidates tc
                JOIN emerging_topics  et ON et.id = tc.emerging_topic_id
                WHERE {' AND '.join(where)}
                ORDER BY
                    COALESCE(tc.relevance_score, 0) *
                        COALESCE(et.confidence_score, 0.5) DESC,
                    tc.created_at DESC
            """)
            rows = self._execute_with_rollback(sql, params).fetchall()
            out = []
            for r in rows:
                rd = dict(r._mapping) if hasattr(r, "_mapping") else dict(r)
                for k in ("created_at", "updated_at", "triaged_at",
                          "detection_date", "snooze_until"):
                    v = rd.get(k)
                    if hasattr(v, "isoformat"):
                        rd[k] = v.isoformat()
                out.append(rd)
            return out
        except Exception as e:
            self.logger.error(f"Error listing topic candidates: {e}")
            return []

    def get_topic_candidate(self, candidate_id: int) -> dict:
        try:
            from sqlalchemy import text as sa_text
            sql = sa_text("""
                SELECT
                    tc.*,
                    et.topic_label,
                    et.topic_description,
                    et.article_count,
                    et.growth_rate,
                    et.key_themes,
                    et.sample_article_uris,
                    et.article_uris,
                    et.detection_date
                FROM topic_candidates tc
                JOIN emerging_topics  et ON et.id = tc.emerging_topic_id
                WHERE tc.id = :id
            """)
            row = self._execute_with_rollback(sql, {"id": int(candidate_id)}).fetchone()
            if not row:
                return {}
            rd = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
            for k in ("created_at", "updated_at", "triaged_at",
                      "detection_date", "snooze_until"):
                v = rd.get(k)
                if hasattr(v, "isoformat"):
                    rd[k] = v.isoformat()
            return rd
        except Exception as e:
            self.logger.error(f"Error getting candidate {candidate_id}: {e}")
            return {}

    def triage_topic_candidate(
        self, candidate_id: int, *,
        action: str,
        reason: str = None,
        snooze_days: int = None,
        merged_into: str = None,
        promoted_to: str = None,
        triaged_by: str = None,
    ) -> dict:
        """Apply a triage action to a candidate.

        action ∈ {snooze, reject, merge, promote}. The promote action
        only updates the candidate row — the actual horizons + assessment
        pipeline is owned by ``wiley_candidate_pipeline``.
        """
        try:
            from sqlalchemy import text as sa_text
            if action not in ("snooze", "reject", "merge", "promote", "unsnooze"):
                raise ValueError(f"Invalid triage action '{action}'")

            updates = {"id": int(candidate_id)}
            set_clauses = []
            if action == "snooze":
                if not snooze_days or snooze_days <= 0:
                    raise ValueError("snooze_days required for snooze")
                set_clauses.append("triage_status = 'snoozed'")
                set_clauses.append(
                    "snooze_until = (CURRENT_DATE + (:days || ' days')::interval)::date"
                )
                updates["days"] = int(snooze_days)
            elif action == "unsnooze":
                set_clauses.append("triage_status = 'pending'")
                set_clauses.append("snooze_until = NULL")
            elif action == "reject":
                set_clauses.append("triage_status = 'rejected'")
                if reason:
                    set_clauses.append("rejected_reason = :reason")
                    updates["reason"] = reason
            elif action == "merge":
                if not merged_into:
                    raise ValueError("merged_into topic name required for merge")
                set_clauses.append("triage_status = 'merged'")
                set_clauses.append("promoted_to_topic = :merged_into")
                updates["merged_into"] = merged_into
            elif action == "promote":
                if not promoted_to:
                    raise ValueError("promoted_to topic name required for promote")
                set_clauses.append("triage_status = 'promoted'")
                set_clauses.append("promoted_to_topic = :promoted_to")
                updates["promoted_to"] = promoted_to

            if triaged_by:
                set_clauses.append("triaged_by = :triaged_by")
                updates["triaged_by"] = triaged_by
            set_clauses.append("triaged_at = NOW()")
            set_clauses.append("updated_at = NOW()")

            sql = sa_text(
                f"UPDATE topic_candidates SET {', '.join(set_clauses)} "
                f"WHERE id = :id"
            )
            self._execute_with_rollback(sql, updates)
            try:
                self.session.commit()
            except Exception:
                pass
            return self.get_topic_candidate(candidate_id)
        except Exception as e:
            self.logger.error(f"Error triaging candidate {candidate_id} ({action}): {e}")
            raise

    def sweep_snoozed_candidates(self) -> int:
        """Flip any snoozed candidate whose snooze_until is today or
        earlier back to 'pending'. Called daily by the scheduler.
        Returns the number of rows unsnoozed.
        """
        try:
            from sqlalchemy import text as sa_text
            sql = sa_text("""
                UPDATE topic_candidates
                SET triage_status = 'pending', snooze_until = NULL,
                    updated_at = NOW()
                WHERE triage_status = 'snoozed'
                  AND snooze_until IS NOT NULL
                  AND snooze_until <= CURRENT_DATE
            """)
            result = self._execute_with_rollback(sql)
            try:
                self.session.commit()
            except Exception:
                pass
            return int(result.rowcount or 0)
        except Exception as e:
            self.logger.error(f"Error sweeping snoozed candidates: {e}")
            return 0

    def get_organizational_profile_by_name(self, name: str) -> dict:
        """Look up an organizational_profiles row by exact name match.
        Used by the candidate pipeline to load the Wiley brief for the
        relevance judge.
        """
        try:
            from sqlalchemy import text as sa_text
            sql = sa_text(
                "SELECT * FROM organizational_profiles WHERE name = :name LIMIT 1"
            )
            row = self._execute_with_rollback(sql, {"name": name}).fetchone()
            if not row:
                return {}
            return dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
        except Exception as e:
            self.logger.error(f"Error loading org profile '{name}': {e}")
            return {}

    # Bundle-level synthesis cache (cross-topic LLM artefacts)
    def get_forecast_bundle_synthesis(self, cadence: str, period_label: str) -> dict:
        """Return cached cross-topic LLM synthesis for a bundle period, or {}."""
        try:
            from app.database_models import t_forecast_bundle_synthesis
            from sqlalchemy import select
            import json

            stmt = (
                select(t_forecast_bundle_synthesis)
                .where(t_forecast_bundle_synthesis.c.cadence == cadence)
                .where(t_forecast_bundle_synthesis.c.period_label == period_label)
            )
            row = self._execute_with_rollback(stmt).fetchone()
            if not row:
                return {}
            rd = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
            for k in ("payload", "topics"):
                v = rd.get(k)
                if isinstance(v, str):
                    try:
                        rd[k] = json.loads(v)
                    except Exception:
                        pass
            for k in ("created_at", "updated_at"):
                v = rd.get(k)
                if hasattr(v, "isoformat"):
                    rd[k] = v.isoformat()
            return rd
        except Exception as e:
            self.logger.error(f"Error getting bundle synthesis ({cadence}/{period_label}): {e}")
            return {}

    def save_forecast_bundle_synthesis(
        self, cadence: str, period_label: str, payload: dict, topics: list = None,
    ):
        """Upsert the cross-topic synth payload for a bundle period.

        Use raw SQL with explicit ``CAST(... AS jsonb)`` so the dict gets
        stored as a JSONB object, not a JSONB string. Going through
        ``pg_insert(...).values(payload=json.dumps(...))`` double-encodes
        because psycopg2 wraps the already-stringified value once more —
        the resulting row's ``payload`` is a JSONB *string*, breaking the
        ``payload->>'key'`` accessor used by the slide builders.
        """
        try:
            from sqlalchemy import text as sa_text
            import json

            stmt = sa_text(
                "INSERT INTO forecast_bundle_synthesis "
                "(cadence, period_label, payload, topics) "
                "VALUES (:cadence, :period_label, CAST(:payload AS jsonb), CAST(:topics AS jsonb)) "
                "ON CONFLICT (cadence, period_label) DO UPDATE "
                "SET payload = CAST(:payload AS jsonb), "
                "    topics = CAST(:topics AS jsonb), "
                "    updated_at = NOW()"
            )
            self._execute_with_rollback(stmt, {
                "cadence": cadence,
                "period_label": period_label,
                "payload": json.dumps(payload or {}),
                "topics": json.dumps(topics or []),
            })
            try:
                self.session.commit()
            except Exception:
                pass
        except Exception as e:
            self.logger.error(f"Error saving bundle synthesis ({cadence}/{period_label}): {e}")

    # Bundle review gate (forecast_bundle_review) — backs the human-in-the-loop
    # review step in the WileyBundleSupervisor pipeline.
    def get_forecast_bundle_review(self, cadence: str, period_label: str) -> dict:
        try:
            from app.database_models import t_forecast_bundle_review
            from sqlalchemy import select
            import json

            stmt = (
                select(t_forecast_bundle_review)
                .where(t_forecast_bundle_review.c.cadence == cadence)
                .where(t_forecast_bundle_review.c.period_label == period_label)
            )
            row = self._execute_with_rollback(stmt).fetchone()
            if not row:
                return {}
            rd = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
            f = rd.get("reviewer_findings")
            if isinstance(f, str):
                try:
                    rd["reviewer_findings"] = json.loads(f)
                except Exception:
                    pass
            for k in ("approved_at", "shipped_at", "created_at", "updated_at"):
                v = rd.get(k)
                if hasattr(v, "isoformat"):
                    rd[k] = v.isoformat()
            return rd
        except Exception as e:
            self.logger.error(f"Error getting bundle review ({cadence}/{period_label}): {e}")
            return {}

    def upsert_forecast_bundle_review(
        self, cadence: str, period_label: str,
        *,
        status: str = None,
        reviewer_findings: list = None,
        reviewer_model: str = None,
        approved_by: str = None,
        approved_at=None,
        shipped_at=None,
    ) -> dict:
        """Upsert the review row. Pass only the fields you want to change —
        unset ones won't be overwritten.

        Same JSONB-double-encoding hazard as save_forecast_bundle_synthesis:
        we use raw SQL with explicit CAST so reviewer_findings stores as a
        JSONB array, not a JSONB string.
        """
        try:
            from sqlalchemy import text as sa_text
            import json

            findings_json = json.dumps(reviewer_findings) if reviewer_findings is not None else None

            stmt = sa_text(
                "INSERT INTO forecast_bundle_review "
                "(cadence, period_label, status, reviewer_findings, reviewer_model, approved_by, approved_at, shipped_at) "
                "VALUES (:cadence, :period_label, COALESCE(:status, 'awaiting_synth'), "
                "        CASE WHEN :findings IS NULL THEN NULL ELSE CAST(:findings AS jsonb) END, "
                "        :reviewer_model, :approved_by, :approved_at, :shipped_at) "
                "ON CONFLICT (cadence, period_label) DO UPDATE SET "
                "  status = COALESCE(:status, forecast_bundle_review.status), "
                "  reviewer_findings = COALESCE(CASE WHEN :findings IS NULL THEN NULL ELSE CAST(:findings AS jsonb) END, forecast_bundle_review.reviewer_findings), "
                "  reviewer_model = COALESCE(:reviewer_model, forecast_bundle_review.reviewer_model), "
                "  approved_by = COALESCE(:approved_by, forecast_bundle_review.approved_by), "
                "  approved_at = COALESCE(:approved_at, forecast_bundle_review.approved_at), "
                "  shipped_at = COALESCE(:shipped_at, forecast_bundle_review.shipped_at), "
                "  updated_at = NOW()"
            )
            self._execute_with_rollback(stmt, {
                "cadence": cadence,
                "period_label": period_label,
                "status": status,
                "findings": findings_json,
                "reviewer_model": reviewer_model,
                "approved_by": approved_by,
                "approved_at": approved_at,
                "shipped_at": shipped_at,
            })
            try:
                self.session.commit()
            except Exception:
                pass
            return self.get_forecast_bundle_review(cadence, period_label)
        except Exception as e:
            self.logger.error(f"Error upserting bundle review ({cadence}/{period_label}): {e}")
            raise

    # ------------------------------------------------------------------
    # Quarterly Brief Editor helpers — back the QuarterlyBriefEditor page
    # (ui/src/pages/QuarterlyBriefEditor.tsx) and the editor endpoints in
    # forecast_assessment_routes.py.
    # ------------------------------------------------------------------

    def get_brief_payload(self, cadence: str, period_label: str) -> dict:
        """Return the editable bundle state in one shot.

        Combines synthesis payload + locked_keys + edit_history + review
        state + per-topic summaries. Single GET feeds the whole editor
        page.
        """
        try:
            synth = self.get_forecast_bundle_synthesis(cadence, period_label) or {}
            review = self.get_forecast_bundle_review(cadence, period_label) or {}

            topics = synth.get("topics") or []
            per_topic = []
            for t in topics:
                topic_name = t.get("topic") if isinstance(t, dict) else t
                if not topic_name:
                    continue
                latest = self.get_latest_forecast_assessment_by_topic(topic_name) or {}
                per_topic.append({
                    "topic": topic_name,
                    "assessment_id": latest.get("id"),
                    "assessed_at": latest.get("assessed_at"),
                    "summary": latest.get("summary") or {},
                    "summary_locked_keys": latest.get("summary_locked_keys") or [],
                })

            return {
                "cadence": cadence,
                "period_label": period_label,
                "payload": synth.get("payload") or {},
                "topics": topics,
                "locked_keys": synth.get("locked_keys") or [],
                "edit_history": synth.get("edit_history") or [],
                "updated_at": synth.get("updated_at"),
                "review": review,
                "per_topic": per_topic,
            }
        except Exception as e:
            self.logger.error(f"Error get_brief_payload ({cadence}/{period_label}): {e}")
            return {}

    @staticmethod
    def _split_path(path: str) -> list:
        """Parse a dot-path like 'cross_cutting_themes[2].body' into a list
        of (kind, key) tuples: [('key','cross_cutting_themes'),('idx',2),('key','body')].

        Used for the jsonb_set parameter array and for in-Python walks.
        """
        if not path:
            return []
        out = []
        token = ""
        i = 0
        while i < len(path):
            ch = path[i]
            if ch == ".":
                if token:
                    out.append(("key", token))
                    token = ""
            elif ch == "[":
                if token:
                    out.append(("key", token))
                    token = ""
                j = path.find("]", i)
                if j == -1:
                    raise ValueError(f"Unclosed bracket in path: {path}")
                out.append(("idx", int(path[i + 1:j])))
                i = j
            else:
                token += ch
            i += 1
        if token:
            out.append(("key", token))
        return out

    @classmethod
    def _path_to_jsonb_array(cls, path: str) -> list:
        """Convert 'cross_cutting_themes[2].body' → ['cross_cutting_themes','2','body']
        for use with PostgreSQL's jsonb_set(target, path, value) text[] argument.
        """
        return [str(tok) for _, tok in cls._split_path(path)]

    @classmethod
    def _walk_path(cls, obj, path: str):
        """Return the subtree at `path` in `obj`, or None if missing."""
        try:
            cur = obj
            for kind, tok in cls._split_path(path):
                if kind == "key":
                    if not isinstance(cur, dict):
                        return None
                    cur = cur.get(tok)
                else:  # idx
                    if not isinstance(cur, list) or tok >= len(cur) or tok < 0:
                        return None
                    cur = cur[tok]
            return cur
        except Exception:
            return None

    def patch_brief_field(
        self, cadence: str, period_label: str,
        *, path: str, value, edited_by: str = None,
        lock: bool = None,
    ) -> dict:
        """Update a single field inside `payload` by dot-path. Appends an
        entry to `edit_history`. Optionally toggles the path's lock.

        Returns the refreshed brief payload.
        """
        try:
            import hashlib
            import json
            from sqlalchemy import text as sa_text

            row = self.get_forecast_bundle_synthesis(cadence, period_label) or {}
            payload = row.get("payload") or {}
            prev_subtree = self._walk_path(payload, path)

            def _hash(o):
                try:
                    return hashlib.sha256(
                        json.dumps(o, sort_keys=True, default=str).encode()
                    ).hexdigest()[:16]
                except Exception:
                    return None

            path_array = self._path_to_jsonb_array(path)
            # jsonb_set expects a text[] like {a,b,2}; psycopg2 maps Python
            # list[str] → text[] automatically when sent as a bound param.
            stmt = sa_text(
                "UPDATE forecast_bundle_synthesis "
                "SET payload = jsonb_set(payload, :path, CAST(:value AS jsonb), true), "
                "    edit_history = edit_history || CAST(:hist AS jsonb), "
                "    updated_at = NOW() "
                "WHERE cadence = :cadence AND period_label = :period_label"
            )
            hist_entry = [{
                "key": path,
                "prev_hash": _hash(prev_subtree),
                "next_hash": _hash(value),
                "edited_by": edited_by or "unknown",
                "edited_at": datetime.utcnow().isoformat(),
            }]
            self._execute_with_rollback(stmt, {
                "cadence": cadence,
                "period_label": period_label,
                "path": "{" + ",".join(path_array) + "}",
                "value": json.dumps(value),
                "hist": json.dumps(hist_entry),
            })

            if lock is not None:
                self.toggle_brief_lock(cadence, period_label, path=path, locked=lock)

            try:
                self.session.commit()
            except Exception:
                pass

            return self.get_brief_payload(cadence, period_label)
        except Exception as e:
            self.logger.error(
                f"Error patch_brief_field({cadence}/{period_label}, {path}): {e}"
            )
            raise

    def toggle_brief_lock(
        self, cadence: str, period_label: str,
        *, path: str, locked: bool,
    ) -> dict:
        """Add/remove a path from locked_keys."""
        try:
            import json
            from sqlalchemy import text as sa_text

            row = self.get_forecast_bundle_synthesis(cadence, period_label) or {}
            keys = list(row.get("locked_keys") or [])
            if locked and path not in keys:
                keys.append(path)
            elif not locked and path in keys:
                keys.remove(path)

            stmt = sa_text(
                "UPDATE forecast_bundle_synthesis "
                "SET locked_keys = CAST(:keys AS jsonb), updated_at = NOW() "
                "WHERE cadence = :cadence AND period_label = :period_label"
            )
            self._execute_with_rollback(stmt, {
                "cadence": cadence,
                "period_label": period_label,
                "keys": json.dumps(keys),
            })
            try:
                self.session.commit()
            except Exception:
                pass
            return {"path": path, "locked": locked, "locked_keys": keys}
        except Exception as e:
            self.logger.error(
                f"Error toggle_brief_lock({cadence}/{period_label}, {path}): {e}"
            )
            raise

    def get_brief_locked_keys(self, cadence: str, period_label: str) -> list:
        try:
            row = self.get_forecast_bundle_synthesis(cadence, period_label) or {}
            return list(row.get("locked_keys") or [])
        except Exception:
            return []

    def patch_topic_summary_field(
        self, *, topic: str, assessment_id: str,
        path: str, value, edited_by: str = None, lock: bool = None,
    ) -> dict:
        """Per-topic equivalent of patch_brief_field. Edits
        `forecast_assessments.summary` for `assessment_id` via jsonb_set;
        appends to a per-topic edit history (kept inline in summary for
        simplicity)."""
        try:
            import hashlib
            import json
            from sqlalchemy import text as sa_text

            latest = self.get_latest_forecast_assessment_by_topic(topic) or {}
            summary = latest.get("summary") or {}
            prev_subtree = self._walk_path(summary, path)

            def _hash(o):
                try:
                    return hashlib.sha256(
                        json.dumps(o, sort_keys=True, default=str).encode()
                    ).hexdigest()[:16]
                except Exception:
                    return None

            path_array = self._path_to_jsonb_array(path)
            stmt = sa_text(
                "UPDATE forecast_assessments "
                "SET summary = jsonb_set(summary, :path, CAST(:value AS jsonb), true) "
                "WHERE id = :assessment_id"
            )
            self._execute_with_rollback(stmt, {
                "assessment_id": assessment_id,
                "path": "{" + ",".join(path_array) + "}",
                "value": json.dumps(value),
            })

            if lock is not None:
                self.toggle_topic_summary_lock(
                    assessment_id=assessment_id, path=path, locked=lock,
                )

            try:
                self.session.commit()
            except Exception:
                pass

            return {
                "topic": topic,
                "assessment_id": assessment_id,
                "path": path,
                "prev_hash": _hash(prev_subtree),
                "next_hash": _hash(value),
                "edited_by": edited_by or "unknown",
                "edited_at": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            self.logger.error(
                f"Error patch_topic_summary_field({topic}, {path}): {e}"
            )
            raise

    def toggle_topic_summary_lock(
        self, *, assessment_id: str, path: str, locked: bool,
    ) -> dict:
        try:
            import json
            from sqlalchemy import text as sa_text

            row = self._execute_with_rollback(
                sa_text(
                    "SELECT summary_locked_keys FROM forecast_assessments "
                    "WHERE id = :id"
                ),
                {"id": assessment_id},
            ).fetchone()
            if not row:
                return {"path": path, "locked": locked, "summary_locked_keys": []}
            keys = list(row[0] or [])
            if locked and path not in keys:
                keys.append(path)
            elif not locked and path in keys:
                keys.remove(path)

            stmt = sa_text(
                "UPDATE forecast_assessments "
                "SET summary_locked_keys = CAST(:keys AS jsonb) "
                "WHERE id = :id"
            )
            self._execute_with_rollback(stmt, {
                "id": assessment_id,
                "keys": json.dumps(keys),
            })
            try:
                self.session.commit()
            except Exception:
                pass
            return {"path": path, "locked": locked, "summary_locked_keys": keys}
        except Exception as e:
            self.logger.error(
                f"Error toggle_topic_summary_lock({assessment_id}, {path}): {e}"
            )
            raise

    # ------------------------------------------------------------------
    # extracted_events CRUD — backs the Events tab in the editor + the
    # supervisor's events stage runner.
    # ------------------------------------------------------------------

    def list_extracted_events(
        self, *, topic: str = None, cadence: str = None,
        period_label: str = None, include_excluded: bool = True,
    ) -> list:
        try:
            from sqlalchemy import text as sa_text

            where = []
            params = {}
            if topic:
                where.append("topic = :topic")
                params["topic"] = topic
            if cadence:
                where.append("cadence = :cadence")
                params["cadence"] = cadence
            if period_label:
                where.append("period_label = :period_label")
                params["period_label"] = period_label
            if not include_excluded:
                where.append("include_in_deck = true")
            sql = "SELECT * FROM extracted_events"
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY event_date DESC NULLS LAST, id DESC"

            rows = self._execute_with_rollback(sa_text(sql), params).fetchall()
            out = []
            for r in rows:
                rd = dict(r._mapping) if hasattr(r, "_mapping") else dict(r)
                for k in ("event_date", "created_at", "updated_at"):
                    v = rd.get(k)
                    if hasattr(v, "isoformat"):
                        rd[k] = v.isoformat()
                out.append(rd)
            return out
        except Exception as e:
            self.logger.error(f"Error list_extracted_events: {e}")
            return []

    def upsert_extracted_event(self, event: dict) -> int:
        """Insert an event, idempotent on the dedupe key. If a row already
        exists, merges source_urls[] and keeps the higher confidence value.

        Returns the row id.
        """
        try:
            import json
            from sqlalchemy import text as sa_text

            stmt = sa_text(
                "INSERT INTO extracted_events ("
                "  assessment_id, topic, cadence, period_label, "
                "  actor, actor_normalized, action, subject, subject_normalized, "
                "  magnitude_value, magnitude_unit, event_date, "
                "  source_urls, confidence, requires_review, include_in_deck, "
                "  scenario_relevance, origin, edited_by) "
                "VALUES ("
                "  :assessment_id, :topic, :cadence, :period_label, "
                "  :actor, :actor_normalized, :action, :subject, :subject_normalized, "
                "  :magnitude_value, :magnitude_unit, :event_date, "
                "  CAST(:source_urls AS jsonb), :confidence, :requires_review, "
                "  :include_in_deck, "
                "  CAST(:scenario_relevance AS jsonb), :origin, :edited_by) "
                "ON CONFLICT ON CONSTRAINT uq_extracted_events_dedupe DO UPDATE SET "
                "  source_urls = ("
                "    SELECT to_jsonb(array_agg(DISTINCT u)) FROM ("
                "      SELECT jsonb_array_elements_text(extracted_events.source_urls) AS u "
                "      UNION SELECT jsonb_array_elements_text(CAST(:source_urls AS jsonb)) AS u "
                "    ) deduped"
                "  ), "
                "  confidence = GREATEST(extracted_events.confidence, COALESCE(:confidence, 0)), "
                "  requires_review = extracted_events.requires_review AND :requires_review, "
                "  updated_at = NOW() "
                "RETURNING id"
            )
            # Events default to in-deck. Quality is controlled upstream now
            # (topic_alignment_score floor in get_relevant_articles_for_topic
            # removes off-topic feed noise) plus the requires_review flag and
            # the top-N deck-cap ranking. The analyst can still exclude any
            # event from the editor's Events tab.
            default_in_deck = True
            params = {
                "assessment_id": event.get("assessment_id"),
                "topic": event.get("topic"),
                "cadence": event.get("cadence"),
                "period_label": event.get("period_label"),
                "actor": event.get("actor"),
                "actor_normalized": event.get("actor_normalized"),
                "action": event.get("action"),
                "subject": event.get("subject"),
                "subject_normalized": event.get("subject_normalized"),
                "magnitude_value": event.get("magnitude_value"),
                "magnitude_unit": event.get("magnitude_unit"),
                "event_date": event.get("event_date"),
                "source_urls": json.dumps(event.get("source_urls") or []),
                "confidence": event.get("confidence"),
                "requires_review": bool(event.get("requires_review", False)),
                "include_in_deck": bool(event.get("include_in_deck", default_in_deck)),
                "scenario_relevance": json.dumps(event.get("scenario_relevance") or []),
                "origin": event.get("origin", "auto"),
                "edited_by": event.get("edited_by"),
            }
            row = self._execute_with_rollback(stmt, params).fetchone()
            try:
                self.session.commit()
            except Exception:
                pass
            return int(row[0]) if row else None
        except Exception as e:
            self.logger.error(f"Error upsert_extracted_event: {e}")
            raise

    def patch_extracted_event(self, event_id: int, fields: dict) -> dict:
        """Patch any editable field on an extracted_events row. Whitelist
        of fields prevents the editor from poking dedupe-key columns."""
        try:
            import json
            from sqlalchemy import text as sa_text

            allowed = {
                "actor", "action", "subject",
                "magnitude_value", "magnitude_unit", "event_date",
                "confidence", "requires_review", "include_in_deck",
                "scenario_relevance", "edited_by",
            }
            sets = []
            params = {"id": event_id}
            for k, v in fields.items():
                if k not in allowed:
                    continue
                if k == "scenario_relevance":
                    sets.append("scenario_relevance = CAST(:scenario_relevance AS jsonb)")
                    params["scenario_relevance"] = json.dumps(v or [])
                else:
                    sets.append(f"{k} = :{k}")
                    params[k] = v
            if not sets:
                return self.get_extracted_event(event_id)
            sets.append("updated_at = NOW()")
            stmt = sa_text(
                "UPDATE extracted_events SET " + ", ".join(sets) +
                " WHERE id = :id"
            )
            self._execute_with_rollback(stmt, params)
            try:
                self.session.commit()
            except Exception:
                pass
            return self.get_extracted_event(event_id)
        except Exception as e:
            self.logger.error(f"Error patch_extracted_event({event_id}): {e}")
            raise

    def get_extracted_event(self, event_id: int) -> dict:
        try:
            from sqlalchemy import text as sa_text
            row = self._execute_with_rollback(
                sa_text("SELECT * FROM extracted_events WHERE id = :id"),
                {"id": event_id},
            ).fetchone()
            if not row:
                return {}
            rd = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
            for k in ("event_date", "created_at", "updated_at"):
                v = rd.get(k)
                if hasattr(v, "isoformat"):
                    rd[k] = v.isoformat()
            return rd
        except Exception as e:
            self.logger.error(f"Error get_extracted_event({event_id}): {e}")
            return {}

    def delete_extracted_event(self, event_id: int) -> bool:
        try:
            from sqlalchemy import text as sa_text
            self._execute_with_rollback(
                sa_text("DELETE FROM extracted_events WHERE id = :id"),
                {"id": event_id},
            )
            try:
                self.session.commit()
            except Exception:
                pass
            return True
        except Exception as e:
            self.logger.error(f"Error delete_extracted_event({event_id}): {e}")
            return False

    def set_forecast_topic_last_delivered(self, topic: str, when=None):
        """Bump ``last_delivered_at`` after a successful email send."""
        try:
            from app.database_models import t_forecast_topic_delivery
            from sqlalchemy import update
            from datetime import datetime, timezone

            ts = when or datetime.now(timezone.utc)
            stmt = (
                update(t_forecast_topic_delivery)
                .where(t_forecast_topic_delivery.c.topic == topic)
                .values(last_delivered_at=ts)
            )
            self._execute_with_rollback(stmt)
            try:
                self.session.commit()
            except Exception:
                pass
        except Exception as e:
            self.logger.error(f"Error setting last_delivered for topic {topic}: {e}")

    # Future Horizons Executive Summary Storage Methods
    def save_horizons_executive_summary(
        self,
        analysis_id: str,
        topic: str,
        summary_data: dict
    ) -> bool:
        """Save an executive summary for a Future Horizons analysis.

        Uses the analysis_versions_v2 cache table with a specific key format.
        """
        try:
            import json
            from datetime import datetime
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            cache_key = f"horizons_exec_summary_{analysis_id}"

            statement = pg_insert(analysis_versions_v2).values(
                cache_key=cache_key,
                topic=topic,
                version_data=json.dumps(summary_data),
                cache_metadata=json.dumps({
                    "analysis_id": analysis_id,
                    "type": "executive_summary"
                }),
                created_at=datetime.now().isoformat()
            ).on_conflict_do_update(
                index_elements=['cache_key'],
                set_={
                    'topic': topic,
                    'version_data': json.dumps(summary_data),
                    'cache_metadata': json.dumps({
                        "analysis_id": analysis_id,
                        "type": "executive_summary"
                    }),
                    'created_at': datetime.now().isoformat()
                }
            )

            self._execute_with_rollback(statement)
            self.connection.commit()
            self.logger.info(f"Saved executive summary for horizons analysis {analysis_id}")
            return True

        except Exception as e:
            self.logger.error(f"Error saving horizons executive summary: {e}")
            self.connection.rollback()
            return False

    def get_horizons_executive_summary(self, analysis_id: str) -> dict:
        """Retrieve an executive summary for a Future Horizons analysis.

        Returns None if no summary exists.
        """
        try:
            import json

            cache_key = f"horizons_exec_summary_{analysis_id}"

            statement = select(
                analysis_versions_v2.c.version_data,
                analysis_versions_v2.c.created_at
            ).where(
                analysis_versions_v2.c.cache_key == cache_key
            ).order_by(
                analysis_versions_v2.c.created_at.desc()
            ).limit(1)

            result = self._execute_with_rollback(statement).mappings().fetchone()

            if result and result.get('version_data'):
                data = result['version_data']
                return json.loads(data) if isinstance(data, str) else data

            return None

        except Exception as e:
            self.logger.error(f"Error retrieving horizons executive summary for {analysis_id}: {e}")
            return None

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
        notifications = []
        for row in result:
            notif = dict(row._mapping)
            # Ensure created_at is serialized as ISO format with timezone
            if 'created_at' in notif and notif['created_at']:
                from datetime import timezone
                dt = notif['created_at']
                # If datetime is naive (no timezone), assume it's in UTC and add timezone info
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                notif['created_at'] = dt.isoformat()
            notifications.append(notif)
        return notifications

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
                or_(
                    t_notifications.c.username == username,
                    t_notifications.c.username.is_(None)
                ),
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

    # =============================================================================
    # Background Tasks - Database persistence for task tracking
    # =============================================================================

    def save_background_task(self, task_id: str, name: str, status: str, created_at, started_at,
                            completed_at, progress: float, total_items: int, processed_items: int,
                            current_item: str, result: str, error: str, metadata: str):
        """Save or update a background task in the database"""
        from sqlalchemy import text

        query = text("""
            INSERT INTO background_tasks (
                id, name, status, created_at, started_at, completed_at,
                progress, total_items, processed_items, current_item,
                result, error, metadata
            ) VALUES (
                :id, :name, :status, :created_at, :started_at, :completed_at,
                :progress, :total_items, :processed_items, :current_item,
                :result, :error, :metadata
            )
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                status = EXCLUDED.status,
                started_at = EXCLUDED.started_at,
                completed_at = EXCLUDED.completed_at,
                progress = EXCLUDED.progress,
                total_items = EXCLUDED.total_items,
                processed_items = EXCLUDED.processed_items,
                current_item = EXCLUDED.current_item,
                result = EXCLUDED.result,
                error = EXCLUDED.error,
                metadata = EXCLUDED.metadata
        """)

        self._execute_with_rollback(query, {
            'id': task_id,
            'name': name,
            'status': status,
            'created_at': created_at,
            'started_at': started_at,
            'completed_at': completed_at,
            'progress': progress,
            'total_items': total_items,
            'processed_items': processed_items,
            'current_item': current_item,
            'result': result,
            'error': error,
            'metadata': metadata
        })
        self.connection.commit()

    def get_background_task(self, task_id: str):
        """Retrieve a background task from the database"""
        from sqlalchemy import text

        query = text("""
            SELECT id, name, status, created_at, started_at, completed_at,
                   progress, total_items, processed_items, current_item,
                   result, error, metadata
            FROM background_tasks
            WHERE id = :task_id
        """)

        result = self._execute_with_rollback(query, {'task_id': task_id})
        return result.fetchone()

    # =============================================================================
    # Trend Convergence Dashboard Reference Articles
    # =============================================================================

    def save_consensus_reference_articles(self, consensus_id: str, article_uris: List[str], topic: str) -> bool:
        """Save reference articles for consensus analysis

        Args:
            consensus_id: Unique identifier for the consensus analysis run
            article_uris: List of article URIs to store as references
            topic: Topic name for this analysis

        Returns:
            True if successful, False otherwise
        """
        try:
            from app.database_models import t_consensus_reference_articles

            # Insert all article references
            for uri in article_uris:
                stmt = insert(t_consensus_reference_articles).values(
                    consensus_id=consensus_id,
                    article_uri=uri,
                    topic=topic
                )
                self._execute_with_rollback(stmt)

            self.logger.info(f"Saved {len(article_uris)} reference articles for consensus {consensus_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error saving consensus reference articles: {e}")
            return False

    def get_consensus_reference_articles(self, consensus_id: str, topic: str) -> List[Dict]:
        """Retrieve reference articles for consensus analysis with full article details

        Args:
            consensus_id: Unique identifier for the consensus analysis run
            topic: Topic name for this analysis

        Returns:
            List of article dictionaries with full metadata
        """
        try:
            from app.database_models import t_consensus_reference_articles, t_articles

            stmt = select(
                t_articles.c.uri,
                t_articles.c.title,
                t_articles.c.news_source.label('source'),
                t_articles.c.publication_date.label('published_at'),
                t_consensus_reference_articles.c.retrieved_at
            ).select_from(
                t_consensus_reference_articles.join(
                    t_articles,
                    t_consensus_reference_articles.c.article_uri == t_articles.c.uri
                )
            ).where(
                t_consensus_reference_articles.c.consensus_id == consensus_id,
                t_consensus_reference_articles.c.topic == topic
            )

            results = self._execute_with_rollback(stmt).fetchall()
            articles = []
            for idx, row in enumerate(results, 1):
                article_dict = dict(row._mapping) if hasattr(row, '_mapping') else dict(row)
                article_dict['id'] = idx  # Add sequential ID for frontend
                articles.append(article_dict)
            return articles
        except Exception as e:
            self.logger.error(f"Error retrieving consensus reference articles: {e}")
            return []

    def save_strategic_recommendation_articles(self, recommendation_id: str, article_uris: List[str], topic: str) -> bool:
        """Save reference articles for strategic recommendation

        Args:
            recommendation_id: Unique identifier for the strategic recommendations run
            article_uris: List of article URIs to store as references
            topic: Topic name for this analysis

        Returns:
            True if successful, False otherwise
        """
        try:
            from app.database_models import t_strategic_recommendation_articles

            for uri in article_uris:
                stmt = insert(t_strategic_recommendation_articles).values(
                    recommendation_id=recommendation_id,
                    article_uri=uri,
                    topic=topic
                )
                self._execute_with_rollback(stmt)

            self.logger.info(f"Saved {len(article_uris)} reference articles for recommendation {recommendation_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error saving strategic recommendation articles: {e}")
            return False

    def get_strategic_recommendation_articles(self, recommendation_id: str, topic: str) -> List[Dict]:
        """Retrieve reference articles for strategic recommendation with full details

        Args:
            recommendation_id: Unique identifier for the strategic recommendations run
            topic: Topic name for this analysis

        Returns:
            List of article dictionaries with full metadata
        """
        try:
            from app.database_models import t_strategic_recommendation_articles, t_articles

            stmt = select(
                t_articles.c.uri,
                t_articles.c.title,
                t_articles.c.news_source.label('source'),
                t_articles.c.publication_date.label('published_at'),
                t_strategic_recommendation_articles.c.retrieved_at
            ).select_from(
                t_strategic_recommendation_articles.join(
                    t_articles,
                    t_strategic_recommendation_articles.c.article_uri == t_articles.c.uri
                )
            ).where(
                t_strategic_recommendation_articles.c.recommendation_id == recommendation_id,
                t_strategic_recommendation_articles.c.topic == topic
            )

            results = self._execute_with_rollback(stmt).fetchall()
            articles = []
            for idx, row in enumerate(results, 1):
                article_dict = dict(row._mapping) if hasattr(row, '_mapping') else dict(row)
                article_dict['id'] = idx  # Add sequential ID for frontend
                articles.append(article_dict)
            return articles
        except Exception as e:
            self.logger.error(f"Error retrieving strategic recommendation articles: {e}")
            return []

    def save_market_signal_articles(self, signal_id: str, article_uris: List[str], topic: str) -> bool:
        """Save reference articles for market signals

        Args:
            signal_id: Unique identifier for the market signals run
            article_uris: List of article URIs to store as references
            topic: Topic name for this analysis

        Returns:
            True if successful, False otherwise
        """
        try:
            from app.database_models import t_market_signal_articles

            for uri in article_uris:
                stmt = insert(t_market_signal_articles).values(
                    signal_id=signal_id,
                    article_uri=uri,
                    topic=topic
                )
                self._execute_with_rollback(stmt)

            self.logger.info(f"Saved {len(article_uris)} reference articles for signal {signal_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error saving market signal articles: {e}")
            return False

    def get_market_signal_articles(self, signal_id: str, topic: str) -> List[Dict]:
        """Retrieve reference articles for market signals with full details

        Args:
            signal_id: Unique identifier for the market signals run
            topic: Topic name for this analysis

        Returns:
            List of article dictionaries with full metadata
        """
        try:
            from app.database_models import t_market_signal_articles, t_articles

            stmt = select(
                t_articles.c.uri,
                t_articles.c.title,
                t_articles.c.news_source.label('source'),
                t_articles.c.publication_date.label('published_at'),
                t_market_signal_articles.c.retrieved_at
            ).select_from(
                t_market_signal_articles.join(
                    t_articles,
                    t_market_signal_articles.c.article_uri == t_articles.c.uri
                )
            ).where(
                t_market_signal_articles.c.signal_id == signal_id,
                t_market_signal_articles.c.topic == topic
            )

            results = self._execute_with_rollback(stmt).fetchall()
            articles = []
            for idx, row in enumerate(results, 1):
                article_dict = dict(row._mapping) if hasattr(row, '_mapping') else dict(row)
                article_dict['id'] = idx  # Add sequential ID for frontend
                articles.append(article_dict)
            return articles
        except Exception as e:
            self.logger.error(f"Error retrieving market signal articles: {e}")
            return []

    def save_impact_timeline_articles(self, timeline_id: str, article_uris: List[str], topic: str) -> bool:
        """Save reference articles for impact timeline

        Args:
            timeline_id: Unique identifier for the impact timeline run
            article_uris: List of article URIs to store as references
            topic: Topic name for this analysis

        Returns:
            True if successful, False otherwise
        """
        try:
            from app.database_models import t_impact_timeline_articles

            for uri in article_uris:
                stmt = insert(t_impact_timeline_articles).values(
                    timeline_id=timeline_id,
                    article_uri=uri,
                    topic=topic
                )
                self._execute_with_rollback(stmt)

            self.logger.info(f"Saved {len(article_uris)} reference articles for timeline {timeline_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error saving impact timeline articles: {e}")
            return False

    def get_impact_timeline_articles(self, timeline_id: str, topic: str) -> List[Dict]:
        """Retrieve reference articles for impact timeline with full details

        Args:
            timeline_id: Unique identifier for the impact timeline run
            topic: Topic name for this analysis

        Returns:
            List of article dictionaries with full metadata
        """
        try:
            from app.database_models import t_impact_timeline_articles, t_articles

            stmt = select(
                t_articles.c.uri,
                t_articles.c.title,
                t_articles.c.news_source.label('source'),
                t_articles.c.publication_date.label('published_at'),
                t_impact_timeline_articles.c.retrieved_at
            ).select_from(
                t_impact_timeline_articles.join(
                    t_articles,
                    t_impact_timeline_articles.c.article_uri == t_articles.c.uri
                )
            ).where(
                t_impact_timeline_articles.c.timeline_id == timeline_id,
                t_impact_timeline_articles.c.topic == topic
            )

            results = self._execute_with_rollback(stmt).fetchall()
            articles = []
            for idx, row in enumerate(results, 1):
                article_dict = dict(row._mapping) if hasattr(row, '_mapping') else dict(row)
                article_dict['id'] = idx  # Add sequential ID for frontend
                articles.append(article_dict)
            return articles
        except Exception as e:
            self.logger.error(f"Error retrieving impact timeline articles: {e}")
            return []

    def save_future_horizon_articles(self, horizon_id: str, article_uris: List[str], topic: str) -> bool:
        """Save reference articles for future horizons

        Args:
            horizon_id: Unique identifier for the future horizons run
            article_uris: List of article URIs to store as references
            topic: Topic name for this analysis

        Returns:
            True if successful, False otherwise
        """
        try:
            from app.database_models import t_future_horizon_articles

            for uri in article_uris:
                stmt = insert(t_future_horizon_articles).values(
                    horizon_id=horizon_id,
                    article_uri=uri,
                    topic=topic
                )
                self._execute_with_rollback(stmt)

            self.logger.info(f"Saved {len(article_uris)} reference articles for horizon {horizon_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error saving future horizon articles: {e}")
            return False

    def get_future_horizon_articles(self, horizon_id: str, topic: str) -> List[Dict]:
        """Retrieve reference articles for future horizons with full details

        Args:
            horizon_id: Unique identifier for the future horizons run
            topic: Topic name for this analysis

        Returns:
            List of article dictionaries with full metadata
        """
        try:
            from app.database_models import t_future_horizon_articles, t_articles

            stmt = select(
                t_articles.c.uri,
                t_articles.c.title,
                t_articles.c.news_source.label('source'),
                t_articles.c.publication_date.label('published_at'),
                t_future_horizon_articles.c.retrieved_at
            ).select_from(
                t_future_horizon_articles.join(
                    t_articles,
                    t_future_horizon_articles.c.article_uri == t_articles.c.uri
                )
            ).where(
                t_future_horizon_articles.c.horizon_id == horizon_id,
                t_future_horizon_articles.c.topic == topic
            )

            results = self._execute_with_rollback(stmt).fetchall()
            articles = []
            for idx, row in enumerate(results, 1):
                article_dict = dict(row._mapping) if hasattr(row, '_mapping') else dict(row)
                article_dict['id'] = idx  # Add sequential ID for frontend
                articles.append(article_dict)
            return articles
        except Exception as e:
            self.logger.error(f"Error retrieving future horizon articles: {e}")
            return []

    # ==================== Saved Dashboards Methods ====================

    def create_saved_dashboard(
        self,
        topic: str,
        username: str,
        name: str,
        config: dict,
        article_uris: list,
        tab_data: dict,
        profile_snapshot: dict = None,
        description: str = None,
        articles_analyzed: int = None,
        model_used: str = None,
        auto_generated: bool = False
    ) -> int:
        """Create a new saved dashboard with PostgreSQL-native types.

        Args:
            topic: Topic name
            username: Username
            name: Dashboard name
            config: Configuration dict (stored as JSONB)
            article_uris: List of article URIs (stored as TEXT[])
            tab_data: Dict with keys: consensus, strategic, timeline, signals, horizons
            profile_snapshot: Organizational profile snapshot (stored as JSONB)
            description: Optional description
            articles_analyzed: Number of articles analyzed
            model_used: AI model used

        Returns:
            Dashboard ID
        """
        try:
            from app.database_models import t_saved_dashboards
            from sqlalchemy import insert

            statement = insert(t_saved_dashboards).values(
                topic=topic,
                username=username,
                name=name,
                description=description,
                config=config,
                article_uris=article_uris,
                consensus_data=tab_data.get('consensus'),
                strategic_data=tab_data.get('strategic'),
                timeline_data=tab_data.get('timeline'),
                signals_data=tab_data.get('signals'),
                horizons_data=tab_data.get('horizons'),
                profile_snapshot=profile_snapshot,
                articles_analyzed=articles_analyzed,
                model_used=model_used,
                auto_generated=auto_generated
            ).returning(t_saved_dashboards.c.id)

            result = self._execute_with_rollback(statement)
            dashboard_id = result.scalar()
            self.logger.info(f"Created saved dashboard '{name}' (ID: {dashboard_id}) for user '{username}'")
            return dashboard_id
        except Exception as e:
            self.logger.error(f"Error creating saved dashboard: {e}")
            raise

    def upsert_auto_generated_dashboard(
        self,
        topic: str,
        username: str,
        config: dict,
        article_uris: list,
        tab_data: dict,
        profile_snapshot: dict = None,
        articles_analyzed: int = None,
        model_used: str = None
    ) -> int:
        """Create or update auto-generated dashboard for a topic.

        Updates existing auto-generated dashboard if found, otherwise creates new one.
        Auto-generated dashboards have fixed naming: "Auto-Generated: {topic}"

        Args:
            topic: Topic name
            username: Username (typically admin)
            config: Configuration dict
            article_uris: List of article URIs
            tab_data: Dict with keys: consensus, strategic, timeline, signals, horizons
            profile_snapshot: Organizational profile snapshot
            articles_analyzed: Number of articles analyzed
            model_used: AI model used

        Returns:
            Dashboard ID
        """
        try:
            from app.database_models import t_saved_dashboards
            from sqlalchemy import select, update, text

            dashboard_name = f"Auto-Generated: {topic}"

            # Check if auto-generated dashboard already exists
            stmt = select(t_saved_dashboards.c.id).where(
                t_saved_dashboards.c.topic == topic,
                t_saved_dashboards.c.username == username,
                t_saved_dashboards.c.auto_generated == True
            )

            result = self._execute_with_rollback(stmt).fetchone()

            if result:
                # Update existing dashboard
                dashboard_id = result[0]
                update_stmt = update(t_saved_dashboards).where(
                    t_saved_dashboards.c.id == dashboard_id
                ).values(
                    config=config,
                    article_uris=article_uris,
                    consensus_data=tab_data.get('consensus'),
                    strategic_data=tab_data.get('strategic'),
                    timeline_data=tab_data.get('timeline'),
                    signals_data=tab_data.get('signals'),
                    horizons_data=tab_data.get('horizons'),
                    profile_snapshot=profile_snapshot,
                    articles_analyzed=articles_analyzed,
                    model_used=model_used,
                    updated_at=text('NOW()')
                )
                self._execute_with_rollback(update_stmt)
                self.logger.info(f"Updated auto-generated dashboard '{dashboard_name}' (ID: {dashboard_id})")
                return dashboard_id
            else:
                # Create new auto-generated dashboard
                return self.create_saved_dashboard(
                    topic=topic,
                    username=username,
                    name=dashboard_name,
                    config=config,
                    article_uris=article_uris,
                    tab_data=tab_data,
                    profile_snapshot=profile_snapshot,
                    description=f"Automatically generated by keyword alert auto-collect",
                    articles_analyzed=articles_analyzed,
                    model_used=model_used,
                    auto_generated=True
                )
        except Exception as e:
            self.logger.error(f"Error upserting auto-generated dashboard: {e}")
            raise

    def get_admin_user(self) -> Optional[dict]:
        """Get first admin user from database.

        Returns:
            Dict with user info (username, role, etc.) or None if no admin found
        """
        try:
            from app.database_models import t_users
            from sqlalchemy import select

            stmt = select(t_users).where(
                t_users.c.role == 'admin'
            ).limit(1)

            result = self._execute_with_rollback(stmt).fetchone()
            if result:
                return dict(result._mapping) if hasattr(result, '_mapping') else dict(result)
            return None
        except Exception as e:
            self.logger.error(f"Error getting admin user: {e}")
            return None

    def get_saved_dashboards_for_topic(
        self,
        topic: str,
        username: str
    ) -> list:
        """Get all saved dashboards for a topic (user-scoped).

        Returns list of dashboard summaries with metadata.
        """
        try:
            from app.database_models import t_saved_dashboards
            from sqlalchemy import select

            statement = select(
                t_saved_dashboards.c.id,
                t_saved_dashboards.c.name,
                t_saved_dashboards.c.description,
                t_saved_dashboards.c.created_at,
                t_saved_dashboards.c.updated_at,
                t_saved_dashboards.c.last_accessed_at,
                t_saved_dashboards.c.articles_analyzed,
                t_saved_dashboards.c.model_used,
                t_saved_dashboards.c.auto_generated
            ).where(
                (t_saved_dashboards.c.topic == topic) &
                (t_saved_dashboards.c.username == username)
            ).order_by(t_saved_dashboards.c.last_accessed_at.desc())

            results = self._execute_with_rollback(statement).fetchall()
            dashboards = [dict(row._mapping) for row in results]
            return dashboards
        except Exception as e:
            self.logger.error(f"Error retrieving saved dashboards for topic '{topic}': {e}")
            return []

    def get_saved_dashboard_by_id(
        self,
        dashboard_id: int,
        username: str
    ) -> dict:
        """Load a specific saved dashboard with all JSONB data."""
        try:
            from app.database_models import t_saved_dashboards
            from sqlalchemy import select

            statement = select(t_saved_dashboards).where(
                (t_saved_dashboards.c.id == dashboard_id) &
                (t_saved_dashboards.c.username == username)
            )

            result = self._execute_with_rollback(statement).fetchone()
            if result:
                return dict(result._mapping)
            return None
        except Exception as e:
            self.logger.error(f"Error retrieving saved dashboard {dashboard_id}: {e}")
            return None

    def update_saved_dashboard(
        self,
        dashboard_id: int,
        name: str = None,
        description: str = None,
        tab_data: dict = None
    ) -> bool:
        """Update saved dashboard metadata or cached data.
        Note: updated_at is automatically updated by PostgreSQL trigger.
        """
        try:
            from app.database_models import t_saved_dashboards
            from sqlalchemy import update

            update_values = {}
            if name is not None:
                update_values['name'] = name
            if description is not None:
                update_values['description'] = description
            if tab_data:
                if 'consensus' in tab_data:
                    update_values['consensus_data'] = tab_data['consensus']
                if 'strategic' in tab_data:
                    update_values['strategic_data'] = tab_data['strategic']
                if 'timeline' in tab_data:
                    update_values['timeline_data'] = tab_data['timeline']
                if 'signals' in tab_data:
                    update_values['signals_data'] = tab_data['signals']
                if 'horizons' in tab_data:
                    update_values['horizons_data'] = tab_data['horizons']

            if not update_values:
                return True  # Nothing to update

            statement = update(t_saved_dashboards).where(
                t_saved_dashboards.c.id == dashboard_id
            ).values(**update_values)

            self._execute_with_rollback(statement)
            self.logger.info(f"Updated saved dashboard {dashboard_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error updating saved dashboard {dashboard_id}: {e}")
            return False

    def delete_saved_dashboard(
        self,
        dashboard_id: int,
        username: str
    ) -> bool:
        """Delete a saved dashboard (user-scoped)."""
        try:
            from app.database_models import t_saved_dashboards
            from sqlalchemy import delete

            statement = delete(t_saved_dashboards).where(
                (t_saved_dashboards.c.id == dashboard_id) &
                (t_saved_dashboards.c.username == username)
            )

            result = self._execute_with_rollback(statement)
            deleted = result.rowcount > 0
            if deleted:
                self.logger.info(f"Deleted saved dashboard {dashboard_id} for user '{username}'")
            return deleted
        except Exception as e:
            self.logger.error(f"Error deleting saved dashboard {dashboard_id}: {e}")
            return False

    def update_dashboard_access_time(
        self,
        dashboard_id: int
    ) -> bool:
        """Update last_accessed_at timestamp."""
        try:
            from app.database_models import t_saved_dashboards
            from sqlalchemy import update, text

            statement = update(t_saved_dashboards).where(
                t_saved_dashboards.c.id == dashboard_id
            ).values(last_accessed_at=text('NOW()'))

            self._execute_with_rollback(statement)
            return True
        except Exception as e:
            self.logger.error(f"Error updating dashboard access time {dashboard_id}: {e}")
            return False

    def get_recent_saved_dashboards(
        self,
        username: str,
        limit: int = 10
    ) -> list:
        """Get recently accessed dashboards across all topics."""
        try:
            from app.database_models import t_saved_dashboards
            from sqlalchemy import select

            statement = select(
                t_saved_dashboards.c.id,
                t_saved_dashboards.c.topic,
                t_saved_dashboards.c.name,
                t_saved_dashboards.c.description,
                t_saved_dashboards.c.created_at,
                t_saved_dashboards.c.updated_at,
                t_saved_dashboards.c.last_accessed_at,
                t_saved_dashboards.c.articles_analyzed,
                t_saved_dashboards.c.model_used
            ).where(
                t_saved_dashboards.c.username == username
            ).order_by(
                t_saved_dashboards.c.last_accessed_at.desc()
            ).limit(limit)

            results = self._execute_with_rollback(statement).fetchall()
            dashboards = [dict(row._mapping) for row in results]
            return dashboards
        except Exception as e:
            self.logger.error(f"Error retrieving recent saved dashboards: {e}")
            return []

    def search_saved_dashboards(
        self,
        username: str,
        search_query: str
    ) -> list:
        """Search saved dashboards using PostgreSQL full-text search.
        Leverages the GIN full-text index on name and description.
        """
        try:
            from app.database_models import t_saved_dashboards
            from sqlalchemy import select, func, text

            statement = select(
                t_saved_dashboards.c.id,
                t_saved_dashboards.c.topic,
                t_saved_dashboards.c.name,
                t_saved_dashboards.c.description,
                t_saved_dashboards.c.created_at,
                t_saved_dashboards.c.updated_at,
                t_saved_dashboards.c.last_accessed_at,
                t_saved_dashboards.c.articles_analyzed,
                t_saved_dashboards.c.model_used
            ).where(
                (t_saved_dashboards.c.username == username) &
                (text("to_tsvector('english', coalesce(name, '') || ' ' || coalesce(description, ''))").op('@@')(
                    func.plainto_tsquery('english', search_query)
                ))
            ).order_by(t_saved_dashboards.c.last_accessed_at.desc())

            results = self._execute_with_rollback(statement).fetchall()
            dashboards = [dict(row._mapping) for row in results]
            return dashboards
        except Exception as e:
            self.logger.error(f"Error searching saved dashboards: {e}")
            return []

    def get_dashboard_stats(self, username: str) -> dict:
        """Get aggregate statistics using PostgreSQL window functions.
        Returns: {total_dashboards, unique_topics, total_articles, last_activity}
        """
        try:
            from app.database_models import t_saved_dashboards
            from sqlalchemy import select, func

            statement = select(
                func.count(t_saved_dashboards.c.id).label('total_dashboards'),
                func.count(func.distinct(t_saved_dashboards.c.topic)).label('unique_topics'),
                func.sum(t_saved_dashboards.c.articles_analyzed).label('total_articles'),
                func.max(t_saved_dashboards.c.last_accessed_at).label('last_activity')
            ).where(t_saved_dashboards.c.username == username)

            result = self._execute_with_rollback(statement).fetchone()
            if result:
                return dict(result._mapping)
            return {
                'total_dashboards': 0,
                'unique_topics': 0,
                'total_articles': 0,
                'last_activity': None
            }
        except Exception as e:
            self.logger.error(f"Error getting dashboard stats: {e}")
            return {
                'total_dashboards': 0,
                'unique_topics': 0,
                'total_articles': 0,
                'last_activity': None
            }

    # ============================================================================
    # LLM Error Handling and Circuit Breaker Methods
    # ============================================================================

    def log_llm_processing_error(self, params: dict) -> Optional[int]:
        """
        Log LLM processing errors to database for monitoring and debugging.

        Args:
            params: dict containing:
                - article_id: ID of article being processed (optional)
                - error_type: Exception class name (e.g., "RateLimitError")
                - error_message: Error message string
                - severity: Error severity ("fatal", "recoverable", "skippable", "degraded")
                - model_name: LLM model that generated the error
                - retry_count: Number of retry attempts made
                - will_retry: Boolean indicating if retry will be attempted
                - context: dict with additional context (will be converted to JSON)
                - timestamp: datetime object or ISO format timestamp string

        Returns:
            int: The ID of the inserted error log, or None if logging failed
        """
        # Validate required fields
        required_fields = ['error_type', 'error_message', 'severity', 'model_name', 'timestamp']
        missing_fields = [f for f in required_fields if f not in params]
        if missing_fields:
            self.logger.error(f"Missing required fields for error logging: {missing_fields}")
            return None

        try:
            # Build insert values
            insert_values = {
                'article_id': params.get('article_id'),
                'error_type': params['error_type'],
                'error_message': params['error_message'],
                'severity': params['severity'],
                'model_name': params['model_name'],
                'retry_count': params.get('retry_count', 0),
                'will_retry': params.get('will_retry', False),
                'context': params.get('context', {}),
                'timestamp': params['timestamp']
            }

            # Insert error log and get ID
            statement = insert(llm_processing_errors).values(**insert_values).returning(llm_processing_errors.c.id)
            result = self._execute_with_rollback(statement)
            row = result.fetchone()

            if row:
                return row[0]
            return None

        except Exception as e:
            self.logger.error(f"Failed to log LLM processing error: {e}")
            return None

    def update_article_llm_status(self, params: dict) -> bool:
        """
        Update article status when LLM processing completes or fails.

        Args:
            params: dict containing:
                - article_id: ID of article (required)
                - llm_status: Status string ("processing", "completed", "error", "skipped") (required)
                - error_type: Error type if status is "error" (optional)
                - error_message: Error message if status is "error" (optional)
                - processing_metadata: dict with processing details (optional)

        Returns:
            bool: True if update successful, False otherwise
        """
        # Validate required fields
        if 'article_id' not in params or 'llm_status' not in params:
            self.logger.error("Missing required fields: article_id and llm_status are required")
            return False

        # Validate status value
        valid_statuses = ['processing', 'completed', 'error', 'skipped']
        if params['llm_status'] not in valid_statuses:
            self.logger.error(f"Invalid llm_status: {params['llm_status']}. Must be one of {valid_statuses}")
            return False

        try:
            # Build update values
            update_values = {
                'llm_status': params['llm_status'],
                'llm_status_updated_at': datetime.utcnow()
            }

            if 'error_type' in params and params['error_type']:
                update_values['llm_error_type'] = params['error_type']

            if 'error_message' in params and params['error_message']:
                update_values['llm_error_message'] = params['error_message']

            if 'processing_metadata' in params and params['processing_metadata']:
                update_values['llm_processing_metadata'] = params['processing_metadata']

            # Execute update
            statement = update(articles).where(
                articles.c.id == params['article_id']
            ).values(**update_values)

            self._execute_with_rollback(statement)
            return True

        except Exception as e:
            self.logger.error(f"Failed to update article LLM status: {e}")
            return False

    def get_llm_retry_state(self, model_name: str) -> Optional[dict]:
        """
        Get current retry/failure state for a model.

        Args:
            model_name: Name of the LLM model

        Returns:
            dict: Retry state data, or None if no state exists
        """
        try:
            statement = select(llm_retry_state).where(
                llm_retry_state.c.model_name == model_name
            )

            result = self._execute_with_rollback(statement)
            row = result.fetchone()

            if row:
                return dict(row._mapping)
            return None

        except Exception as e:
            self.logger.error(f"Failed to get LLM retry state for {model_name}: {e}")
            return None

    def update_llm_retry_state(self, params: dict) -> bool:
        """
        Update retry/failure state for a model (for circuit breaker pattern).

        Args:
            params: dict with keys:
                - model_name: str (required)
                - consecutive_failures: int (optional)
                - last_failure_time: datetime (optional)
                - last_success_time: datetime (optional)
                - circuit_state: str ('closed', 'open', 'half_open') (optional)
                - circuit_opened_at: datetime (optional)
                - failure_rate: float (optional)
                - metadata: dict (optional)

        Returns:
            bool: True if update successful, False otherwise
        """
        if 'model_name' not in params:
            self.logger.error("model_name is required for update_llm_retry_state")
            return False

        try:
            # Check if state exists first
            existing = self.get_llm_retry_state(params['model_name'])

            # Build update values
            update_values = {
                'last_updated': datetime.utcnow()
            }

            # Add optional fields if provided
            optional_fields = [
                'consecutive_failures', 'last_failure_time', 'last_success_time',
                'circuit_state', 'circuit_opened_at', 'failure_rate', 'metadata'
            ]
            for field in optional_fields:
                if field in params:
                    update_values[field] = params[field]

            if existing:
                # Update existing record
                statement = update(llm_retry_state).where(
                    llm_retry_state.c.model_name == params['model_name']
                ).values(**update_values)
            else:
                # Insert new record
                update_values['model_name'] = params['model_name']
                statement = insert(llm_retry_state).values(**update_values)

            self._execute_with_rollback(statement)
            return True

        except Exception as e:
            self.logger.error(f"Failed to update LLM retry state: {e}")
            return False

    def reset_llm_retry_state(self, model_name: str) -> bool:
        """
        Reset retry state for a model (after successful recovery).

        Args:
            model_name: Name of the LLM model

        Returns:
            bool: True if reset successful, False otherwise
        """
        return self.update_llm_retry_state({
            'model_name': model_name,
            'consecutive_failures': 0,
            'last_success_time': datetime.utcnow(),
            'circuit_state': 'closed',
            'circuit_opened_at': None,
            'failure_rate': 0.0
        })

    # ==================== AUSPEX RESEARCH SESSIONS ====================

    def create_research_session(self, params: Dict) -> Optional[int]:
        """
        Create a new research session.

        Args:
            params: Dict with keys:
                - username (required): Username of the user
                - query (required): Research query text
                - topic (required): Topic for the research
                - chat_id (optional): Associated chat ID
                - status (optional): Initial status (default: 'pending')
                - objectives (optional): JSONB objectives
                - metadata (optional): JSONB metadata

        Returns:
            int: ID of created session, or None on failure
        """
        required_fields = ['username', 'query', 'topic']
        for field in required_fields:
            if field not in params:
                self.logger.error(f"Missing required field '{field}' for create_research_session")
                return None

        try:
            values = {
                'username': params['username'],
                'query': params['query'],
                'topic': params['topic'],
                'status': params.get('status', 'pending'),
            }

            if 'chat_id' in params:
                values['chat_id'] = params['chat_id']
            if 'objectives' in params:
                values['objectives'] = json.dumps(params['objectives']) if isinstance(params['objectives'], dict) else params['objectives']
            if 'metadata' in params:
                values['metadata'] = json.dumps(params['metadata']) if isinstance(params['metadata'], dict) else params['metadata']

            result = self._execute_with_rollback(
                insert(auspex_research_sessions).values(**values).returning(auspex_research_sessions.c.id),
                operation_name="create_research_session"
            )
            row = result.fetchone()
            return row[0] if row else None

        except Exception as e:
            self.logger.error(f"Failed to create research session: {e}")
            return None

    def get_research_session(self, session_id: int) -> Optional[Dict]:
        """
        Get a research session by ID.

        Args:
            session_id: ID of the research session

        Returns:
            Dict with session data, or None if not found
        """
        try:
            result = self._execute_with_rollback(
                select(auspex_research_sessions).where(
                    auspex_research_sessions.c.id == session_id
                ),
                operation_name="get_research_session"
            )
            row = result.mappings().fetchone()
            return dict(row) if row else None

        except Exception as e:
            self.logger.error(f"Failed to get research session {session_id}: {e}")
            return None

    def get_research_sessions_by_user(self, username: str, limit: int = 50) -> List[Dict]:
        """
        Get research sessions for a user.

        Args:
            username: Username to filter by
            limit: Maximum number of sessions to return

        Returns:
            List of session dicts
        """
        try:
            result = self._execute_with_rollback(
                select(auspex_research_sessions).where(
                    auspex_research_sessions.c.username == username
                ).order_by(
                    desc(auspex_research_sessions.c.created_at)
                ).limit(limit),
                operation_name="get_research_sessions_by_user"
            )
            return [dict(row) for row in result.mappings().fetchall()]

        except Exception as e:
            self.logger.error(f"Failed to get research sessions for user {username}: {e}")
            return []

    def update_research_session(self, session_id: int, params: Dict) -> bool:
        """
        Update a research session.

        Args:
            session_id: ID of the session to update
            params: Dict with fields to update (status, objectives, findings, report, metadata, completed_at)

        Returns:
            bool: True if update successful
        """
        try:
            update_values = {}

            allowed_fields = ['status', 'objectives', 'findings', 'report', 'metadata', 'completed_at']
            for field in allowed_fields:
                if field in params:
                    value = params[field]
                    # Convert dicts to JSON strings for JSONB fields
                    if field in ['objectives', 'findings', 'metadata'] and isinstance(value, dict):
                        value = json.dumps(value)
                    update_values[field] = value

            if not update_values:
                self.logger.warning("No valid fields to update for research session")
                return False

            self._execute_with_rollback(
                update(auspex_research_sessions).where(
                    auspex_research_sessions.c.id == session_id
                ).values(**update_values),
                operation_name="update_research_session"
            )
            return True

        except Exception as e:
            self.logger.error(f"Failed to update research session {session_id}: {e}")
            return False

    def delete_research_session(self, session_id: int) -> bool:
        """
        Delete a research session.

        Args:
            session_id: ID of the session to delete

        Returns:
            bool: True if deletion successful
        """
        try:
            self._execute_with_rollback(
                delete(auspex_research_sessions).where(
                    auspex_research_sessions.c.id == session_id
                ),
                operation_name="delete_research_session"
            )
            return True

        except Exception as e:
            self.logger.error(f"Failed to delete research session {session_id}: {e}")
            return False

    # ==================== AUSPEX TOOL USAGE ====================

    def log_tool_usage(self, params: Dict) -> Optional[int]:
        """
        Log a tool usage event.

        Args:
            params: Dict with keys:
                - tool_name (required): Name of the tool used
                - chat_id (optional): Associated chat ID
                - tool_version (optional): Version of the tool
                - parameters (optional): JSONB parameters passed to the tool
                - result_summary (optional): JSONB summary of results
                - execution_ms (optional): Execution time in milliseconds

        Returns:
            int: ID of created log entry, or None on failure
        """
        if 'tool_name' not in params:
            self.logger.error("tool_name is required for log_tool_usage")
            return None

        try:
            values = {'tool_name': params['tool_name']}

            optional_fields = ['chat_id', 'tool_version', 'execution_ms']
            for field in optional_fields:
                if field in params:
                    values[field] = params[field]

            # Handle JSONB fields
            for field in ['parameters', 'result_summary']:
                if field in params:
                    value = params[field]
                    values[field] = json.dumps(value) if isinstance(value, dict) else value

            result = self._execute_with_rollback(
                insert(auspex_tool_usage).values(**values).returning(auspex_tool_usage.c.id),
                operation_name="log_tool_usage"
            )
            row = result.fetchone()
            return row[0] if row else None

        except Exception as e:
            self.logger.error(f"Failed to log tool usage: {e}")
            return None

    def get_tool_usage_stats(self, tool_name: Optional[str] = None, days: int = 30) -> Dict:
        """
        Get tool usage statistics.

        Args:
            tool_name: Optional specific tool to filter by
            days: Number of days to look back (default: 30)

        Returns:
            Dict with usage statistics
        """
        try:
            since = datetime.utcnow() - timedelta(days=days)

            query = select(
                auspex_tool_usage.c.tool_name,
                func.count(auspex_tool_usage.c.id).label('usage_count'),
                func.avg(auspex_tool_usage.c.execution_ms).label('avg_execution_ms'),
                func.max(auspex_tool_usage.c.execution_ms).label('max_execution_ms'),
                func.min(auspex_tool_usage.c.execution_ms).label('min_execution_ms')
            ).where(
                auspex_tool_usage.c.created_at >= since
            ).group_by(
                auspex_tool_usage.c.tool_name
            )

            if tool_name:
                query = query.where(auspex_tool_usage.c.tool_name == tool_name)

            result = self._execute_with_rollback(query, operation_name="get_tool_usage_stats")
            rows = result.mappings().fetchall()

            return {
                "period_days": days,
                "tools": [dict(row) for row in rows]
            }

        except Exception as e:
            self.logger.error(f"Failed to get tool usage stats: {e}")
            return {"period_days": days, "tools": []}

    # ==================== AUSPEX SEARCH ROUTING ====================

    def log_search_routing(self, params: Dict) -> Optional[int]:
        """
        Log a search routing decision.

        Args:
            params: Dict with keys:
                - query (required): The search query
                - recommended_source (required): Source recommended by router
                - actual_source (required): Source actually used
                - topic (optional): Topic context
                - confidence (optional): Router confidence score
                - signals (optional): JSONB signals used in decision
                - result_quality (optional): Quality score for feedback

        Returns:
            int: ID of created log entry, or None on failure
        """
        required_fields = ['query', 'recommended_source', 'actual_source']
        for field in required_fields:
            if field not in params:
                self.logger.error(f"Missing required field '{field}' for log_search_routing")
                return None

        try:
            values = {
                'query': params['query'],
                'recommended_source': params['recommended_source'],
                'actual_source': params['actual_source']
            }

            optional_fields = ['topic', 'confidence', 'result_quality']
            for field in optional_fields:
                if field in params:
                    values[field] = params[field]

            if 'signals' in params:
                value = params['signals']
                values['signals'] = json.dumps(value) if isinstance(value, dict) else value

            result = self._execute_with_rollback(
                insert(auspex_search_routing).values(**values).returning(auspex_search_routing.c.id),
                operation_name="log_search_routing"
            )
            row = result.fetchone()
            return row[0] if row else None

        except Exception as e:
            self.logger.error(f"Failed to log search routing: {e}")
            return None

    def get_search_routing_accuracy(self, days: int = 30) -> Dict:
        """
        Get search routing accuracy statistics.

        Args:
            days: Number of days to look back

        Returns:
            Dict with routing accuracy stats
        """
        try:
            since = datetime.utcnow() - timedelta(days=days)

            # Count total and matches
            result = self._execute_with_rollback(
                select(
                    func.count(auspex_search_routing.c.id).label('total'),
                    func.count(
                        case(
                            (auspex_search_routing.c.recommended_source == auspex_search_routing.c.actual_source, 1),
                            else_=None
                        )
                    ).label('matches'),
                    func.avg(auspex_search_routing.c.confidence).label('avg_confidence'),
                    func.avg(auspex_search_routing.c.result_quality).label('avg_quality')
                ).where(
                    auspex_search_routing.c.created_at >= since
                ),
                operation_name="get_search_routing_accuracy"
            )
            row = result.mappings().fetchone()

            total = row['total'] or 0
            matches = row['matches'] or 0
            accuracy = (matches / total * 100) if total > 0 else 0.0

            return {
                "period_days": days,
                "total_queries": total,
                "matches": matches,
                "accuracy_pct": round(accuracy, 2),
                "avg_confidence": round(float(row['avg_confidence'] or 0), 3),
                "avg_quality": round(float(row['avg_quality'] or 0), 3)
            }

        except Exception as e:
            self.logger.error(f"Failed to get search routing accuracy: {e}")
            return {"period_days": days, "total_queries": 0, "accuracy_pct": 0.0}

    # ==================== Saved Newsletters Methods ====================

    def create_saved_newsletter(
        self,
        topic: str,
        username: str,
        name: str,
        newsletter_content: str,
        config: dict = None,
        days_back: int = None,
        deep_dive_topic: str = None,
        deep_dive_analysis: str = None,
        articles_used: int = None,
        article_uris: list = None,
        model_used: str = None,
        description: str = None
    ) -> int:
        """Create a new saved newsletter.

        Args:
            topic: Topic name
            username: Username
            name: Newsletter name
            newsletter_content: The generated newsletter content (markdown)
            config: Configuration dict used to generate (stored as JSONB)
            days_back: Days back setting used
            deep_dive_topic: Deep dive topic if specified
            deep_dive_analysis: Deep dive analysis content if generated
            articles_used: Number of articles used
            article_uris: List of article URIs used
            model_used: AI model used
            description: Optional description

        Returns:
            Newsletter ID
        """
        try:
            from app.database_models import t_saved_newsletters
            from sqlalchemy import insert

            statement = insert(t_saved_newsletters).values(
                topic=topic,
                username=username,
                name=name,
                description=description,
                config=config,
                days_back=days_back,
                deep_dive_topic=deep_dive_topic,
                newsletter_content=newsletter_content,
                deep_dive_analysis=deep_dive_analysis,
                articles_used=articles_used,
                article_uris=article_uris,
                model_used=model_used
            ).returning(t_saved_newsletters.c.id)

            result = self._execute_with_rollback(statement)
            newsletter_id = result.scalar()
            self.logger.info(f"Created saved newsletter '{name}' (ID: {newsletter_id}) for user '{username}'")
            return newsletter_id
        except Exception as e:
            self.logger.error(f"Error creating saved newsletter: {e}")
            raise

    def get_saved_newsletters_for_topic(
        self,
        topic: str,
        username: str
    ) -> list:
        """Get all saved newsletters for a topic (user-scoped).

        Returns list of newsletter summaries sorted by creation date desc.
        """
        try:
            from app.database_models import t_saved_newsletters
            from sqlalchemy import select

            statement = select(
                t_saved_newsletters.c.id,
                t_saved_newsletters.c.name,
                t_saved_newsletters.c.description,
                t_saved_newsletters.c.created_at,
                t_saved_newsletters.c.updated_at,
                t_saved_newsletters.c.articles_used,
                t_saved_newsletters.c.model_used,
                t_saved_newsletters.c.days_back,
                t_saved_newsletters.c.deep_dive_topic
            ).where(
                (t_saved_newsletters.c.topic == topic) &
                (t_saved_newsletters.c.username == username)
            ).order_by(
                t_saved_newsletters.c.created_at.desc()
            )

            results = self._execute_with_rollback(statement).fetchall()
            newsletters = [dict(row._mapping) for row in results]
            return newsletters
        except Exception as e:
            self.logger.error(f"Error retrieving saved newsletters for topic '{topic}': {e}")
            return []

    def get_saved_newsletter_by_id(
        self,
        newsletter_id: int,
        username: str
    ) -> dict:
        """Get a specific saved newsletter by ID (user-scoped).

        Returns full newsletter data or None if not found.
        """
        try:
            from app.database_models import t_saved_newsletters
            from sqlalchemy import select

            statement = select(t_saved_newsletters).where(
                (t_saved_newsletters.c.id == newsletter_id) &
                (t_saved_newsletters.c.username == username)
            )

            result = self._execute_with_rollback(statement).fetchone()
            if result:
                return dict(result._mapping)
            return None
        except Exception as e:
            self.logger.error(f"Error retrieving saved newsletter {newsletter_id}: {e}")
            return None

    def delete_saved_newsletter(
        self,
        newsletter_id: int,
        username: str
    ) -> bool:
        """Delete a saved newsletter (user-scoped)."""
        try:
            from app.database_models import t_saved_newsletters
            from sqlalchemy import delete

            statement = delete(t_saved_newsletters).where(
                (t_saved_newsletters.c.id == newsletter_id) &
                (t_saved_newsletters.c.username == username)
            )

            result = self._execute_with_rollback(statement)
            deleted = result.rowcount > 0
            if deleted:
                self.logger.info(f"Deleted saved newsletter {newsletter_id} for user '{username}'")
            return deleted
        except Exception as e:
            self.logger.error(f"Error deleting saved newsletter {newsletter_id}: {e}")
            return False

    def update_saved_newsletter(
        self,
        newsletter_id: int,
        username: str,
        name: str = None,
        description: str = None,
        newsletter_content: str = None
    ) -> bool:
        """Update a saved newsletter (user-scoped)."""
        try:
            from app.database_models import t_saved_newsletters
            from sqlalchemy import update

            update_values = {}
            if name is not None:
                update_values['name'] = name
            if description is not None:
                update_values['description'] = description
            if newsletter_content is not None:
                update_values['newsletter_content'] = newsletter_content

            if not update_values:
                return True  # Nothing to update

            statement = update(t_saved_newsletters).where(
                (t_saved_newsletters.c.id == newsletter_id) &
                (t_saved_newsletters.c.username == username)
            ).values(**update_values)

            result = self._execute_with_rollback(statement)
            updated = result.rowcount > 0
            if updated:
                self.logger.info(f"Updated saved newsletter {newsletter_id}")
            return updated
        except Exception as e:
            self.logger.error(f"Error updating saved newsletter {newsletter_id}: {e}")
            return False

    # ========================================================================
    # Saved EOS (Extreme Outlier Scenarios) Methods
    # ========================================================================

    def create_saved_eos(
        self,
        topic: str,
        username: str,
        name: str,
        scenarios: list,
        config: dict = None,
        metadata: dict = None,
        articles_used: int = None,
        article_uris: list = None,
        model_used: str = None,
        time_horizon: str = None,
        scenario_count: int = None,
        description: str = None
    ) -> int:
        """Create a new saved EOS analysis.

        Args:
            topic: Topic name
            username: Username
            name: EOS analysis name
            scenarios: List of generated scenarios (stored as JSONB)
            config: Configuration dict used to generate (stored as JSONB)
            metadata: Analysis metadata (stored as JSONB)
            articles_used: Number of articles used
            article_uris: List of article URIs used
            model_used: AI model used
            time_horizon: Time horizon setting (near/mid/long)
            scenario_count: Number of scenarios generated
            description: Optional description

        Returns:
            ID of the created saved EOS analysis
        """
        try:
            from app.database_models import t_saved_eos
            from sqlalchemy import insert
            import json

            # Ensure scenarios is JSON-serializable
            scenarios_json = json.loads(json.dumps(scenarios, default=str)) if scenarios else []

            statement = insert(t_saved_eos).values(
                topic=topic,
                username=username,
                name=name,
                scenarios=scenarios_json,
                config=config,
                metadata=metadata,
                articles_used=articles_used,
                article_uris=article_uris,
                model_used=model_used,
                time_horizon=time_horizon,
                scenario_count=scenario_count,
                description=description
            ).returning(t_saved_eos.c.id)

            result = self._execute_with_rollback(statement)
            row = result.fetchone()
            self.logger.info(f"Created saved EOS '{name}' for user '{username}' (ID: {row[0]})")
            return row[0]
        except Exception as e:
            self.logger.error(f"Error creating saved EOS: {e}")
            raise

    def get_latest_saved_eos_for_topic(
        self,
        topic: str,
        max_age_days: int = 90,
    ) -> dict:
        """Return the most recent saved EOS scan for a topic, regardless of
        author, IF it's newer than ``max_age_days``. Used by the bundle
        generator to decide whether to reuse a recent scan or trigger a
        fresh one.

        Returns the full row including ``scenarios`` JSONB, or {} if none."""
        try:
            from app.database_models import t_saved_eos
            from sqlalchemy import select
            from datetime import datetime, timezone, timedelta
            import json

            cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
            stmt = (
                select(t_saved_eos)
                .where(t_saved_eos.c.topic == topic)
                .where(t_saved_eos.c.created_at >= cutoff)
                .order_by(t_saved_eos.c.created_at.desc())
                .limit(1)
            )
            row = self._execute_with_rollback(stmt).fetchone()
            if not row:
                return {}
            rd = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
            v = rd.get("scenarios")
            if isinstance(v, str):
                try:
                    rd["scenarios"] = json.loads(v)
                except Exception:
                    pass
            return rd
        except Exception as e:
            self.logger.error(f"Error getting latest EOS for topic {topic}: {e}")
            return {}

    def get_saved_eos_for_topic(
        self,
        topic: str,
        username: str
    ) -> list:
        """Get all saved EOS analyses for a topic (user-scoped).

        Returns list of EOS summaries sorted by creation date desc.
        """
        try:
            from app.database_models import t_saved_eos
            from sqlalchemy import select

            statement = select(
                t_saved_eos.c.id,
                t_saved_eos.c.name,
                t_saved_eos.c.description,
                t_saved_eos.c.created_at,
                t_saved_eos.c.updated_at,
                t_saved_eos.c.articles_used,
                t_saved_eos.c.model_used,
                t_saved_eos.c.time_horizon,
                t_saved_eos.c.scenario_count
            ).where(
                (t_saved_eos.c.topic == topic) &
                (t_saved_eos.c.username == username)
            ).order_by(
                t_saved_eos.c.created_at.desc()
            )

            results = self._execute_with_rollback(statement).fetchall()
            return [dict(r._mapping) for r in results]
        except Exception as e:
            self.logger.error(f"Error getting saved EOS for topic {topic}: {e}")
            return []

    def get_saved_eos_by_id(
        self,
        eos_id: int,
        username: str
    ) -> dict:
        """Get a specific saved EOS analysis by ID (user-scoped).

        Returns full EOS data or None if not found.
        """
        try:
            from app.database_models import t_saved_eos
            from sqlalchemy import select

            statement = select(t_saved_eos).where(
                (t_saved_eos.c.id == eos_id) &
                (t_saved_eos.c.username == username)
            )

            result = self._execute_with_rollback(statement).fetchone()
            if result:
                return dict(result._mapping)
            return None
        except Exception as e:
            self.logger.error(f"Error retrieving saved EOS {eos_id}: {e}")
            return None

    def delete_saved_eos(
        self,
        eos_id: int,
        username: str
    ) -> bool:
        """Delete a saved EOS analysis (user-scoped)."""
        try:
            from app.database_models import t_saved_eos
            from sqlalchemy import delete

            statement = delete(t_saved_eos).where(
                (t_saved_eos.c.id == eos_id) &
                (t_saved_eos.c.username == username)
            )

            result = self._execute_with_rollback(statement)
            deleted = result.rowcount > 0
            if deleted:
                self.logger.info(f"Deleted saved EOS {eos_id} for user '{username}'")
            return deleted
        except Exception as e:
            self.logger.error(f"Error deleting saved EOS {eos_id}: {e}")
            return False

    # ========================================================================
    # SAVED FOCUS GROUPS CRUD
    # ========================================================================

    def create_saved_focus_group(
        self,
        topic: str,
        username: str,
        name: str,
        personas: list,
        focus_group_summary: str = None,
        interaction_dynamics: dict = None,
        config: dict = None,
        metadata: dict = None,
        articles_used: int = None,
        article_uris: list = None,
        model_used: str = None,
        persona_count: int = None,
        description: str = None
    ) -> int:
        """Create a new saved focus group.

        Args:
            topic: Topic name
            username: Username
            name: Focus group name
            personas: List of persona objects (stored as JSONB)
            focus_group_summary: Generated narrative summary
            interaction_dynamics: Consensus areas, tension points, diversity score
            config: Configuration dict used to generate (stored as JSONB)
            metadata: Generation metadata (stored as JSONB)
            articles_used: Number of articles used
            article_uris: List of article URIs used
            model_used: AI model used
            persona_count: Number of personas generated
            description: Optional description

        Returns:
            ID of the created saved focus group
        """
        try:
            from app.database_models import t_saved_focus_groups
            from sqlalchemy import insert
            import json

            # Ensure personas is JSON-serializable
            personas_json = json.loads(json.dumps(personas, default=str)) if personas else []

            statement = insert(t_saved_focus_groups).values(
                topic=topic,
                username=username,
                name=name,
                personas=personas_json,
                focus_group_summary=focus_group_summary,
                interaction_dynamics=interaction_dynamics,
                config=config,
                metadata=metadata,
                articles_used=articles_used,
                article_uris=article_uris,
                model_used=model_used,
                persona_count=persona_count,
                description=description
            ).returning(t_saved_focus_groups.c.id)

            result = self._execute_with_rollback(statement)
            row = result.fetchone()
            self.logger.info(f"Created saved focus group '{name}' for user '{username}' (ID: {row[0]})")
            return row[0]
        except Exception as e:
            self.logger.error(f"Error creating saved focus group: {e}")
            raise

    def get_saved_focus_groups_for_topic(
        self,
        topic: str,
        username: str
    ) -> list:
        """Get all saved focus groups for a topic (user-scoped).

        Returns list of focus group summaries sorted by creation date desc.
        """
        try:
            from app.database_models import t_saved_focus_groups
            from sqlalchemy import select

            statement = select(
                t_saved_focus_groups.c.id,
                t_saved_focus_groups.c.name,
                t_saved_focus_groups.c.description,
                t_saved_focus_groups.c.created_at,
                t_saved_focus_groups.c.updated_at,
                t_saved_focus_groups.c.articles_used,
                t_saved_focus_groups.c.model_used,
                t_saved_focus_groups.c.persona_count
            ).where(
                (t_saved_focus_groups.c.topic == topic) &
                (t_saved_focus_groups.c.username == username)
            ).order_by(
                t_saved_focus_groups.c.created_at.desc()
            )

            results = self._execute_with_rollback(statement).fetchall()
            return [dict(r._mapping) for r in results]
        except Exception as e:
            self.logger.error(f"Error getting saved focus groups for topic {topic}: {e}")
            return []

    def get_saved_focus_group_by_id(
        self,
        focus_group_id: int,
        username: str
    ) -> dict:
        """Get a specific saved focus group by ID (user-scoped).

        Returns full focus group data or None if not found.
        """
        try:
            from app.database_models import t_saved_focus_groups
            from sqlalchemy import select

            statement = select(t_saved_focus_groups).where(
                (t_saved_focus_groups.c.id == focus_group_id) &
                (t_saved_focus_groups.c.username == username)
            )

            result = self._execute_with_rollback(statement).fetchone()
            if result:
                return dict(result._mapping)
            return None
        except Exception as e:
            self.logger.error(f"Error retrieving saved focus group {focus_group_id}: {e}")
            return None

    def delete_saved_focus_group(
        self,
        focus_group_id: int,
        username: str
    ) -> bool:
        """Delete a saved focus group (user-scoped)."""
        try:
            from app.database_models import t_saved_focus_groups
            from sqlalchemy import delete

            statement = delete(t_saved_focus_groups).where(
                (t_saved_focus_groups.c.id == focus_group_id) &
                (t_saved_focus_groups.c.username == username)
            )

            result = self._execute_with_rollback(statement)
            deleted = result.rowcount > 0
            if deleted:
                self.logger.info(f"Deleted saved focus group {focus_group_id} for user '{username}'")
            return deleted
        except Exception as e:
            self.logger.error(f"Error deleting saved focus group {focus_group_id}: {e}")
            return False

    def update_focus_group_persona(
        self,
        focus_group_id: int,
        username: str,
        persona_id: str,
        persona_updates: dict
    ) -> bool:
        """Update a specific persona within a saved focus group.

        Args:
            focus_group_id: Focus group ID
            username: Username (for ownership check)
            persona_id: ID of the persona to update
            persona_updates: Dict of fields to update in the persona

        Returns:
            True if updated, False otherwise
        """
        try:
            from app.database_models import t_saved_focus_groups
            from sqlalchemy import select, update
            from datetime import datetime
            import json

            # First get the current focus group
            statement = select(t_saved_focus_groups.c.personas).where(
                (t_saved_focus_groups.c.id == focus_group_id) &
                (t_saved_focus_groups.c.username == username)
            )
            result = self._execute_with_rollback(statement).fetchone()
            if not result:
                return False

            personas = result[0] if result[0] else []

            # Find and update the persona
            persona_found = False
            for i, persona in enumerate(personas):
                if persona.get('id') == persona_id:
                    personas[i] = {**persona, **persona_updates, 'user_edited': True}
                    persona_found = True
                    break

            if not persona_found:
                self.logger.warning(f"Persona {persona_id} not found in focus group {focus_group_id}")
                return False

            # Update the focus group with modified personas
            update_stmt = update(t_saved_focus_groups).where(
                (t_saved_focus_groups.c.id == focus_group_id) &
                (t_saved_focus_groups.c.username == username)
            ).values(
                personas=json.loads(json.dumps(personas, default=str)),
                updated_at=datetime.utcnow()
            )

            self._execute_with_rollback(update_stmt)
            self.logger.info(f"Updated persona {persona_id} in focus group {focus_group_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error updating persona in focus group {focus_group_id}: {e}")
            return False

    # ========================================================================
    # SAVED EXECUTIVE BRIEFINGS CRUD
    # ========================================================================

    def create_saved_executive_briefing(
        self,
        topic: str,
        username: str,
        name: str,
        persona: str,
        article_count: int,
        articles: list,
        briefing_summary: str = None,
        themes: list = None,
        priority_actions: list = None,
        config: dict = None,
        metadata: dict = None,
        articles_used: int = None,
        article_uris: list = None,
        model_used: str = None,
        description: str = None
    ) -> int:
        """Create a new saved executive briefing.

        Args:
            topic: Topic name
            username: Username
            name: Briefing name
            persona: Executive persona (CEO/CMO/CTO/CISO/Custom)
            article_count: Number of articles requested
            articles: List of analyzed article objects (stored as JSONB)
            briefing_summary: Generated synthesis narrative
            themes: Cross-article themes (list)
            priority_actions: Recommended actions (list)
            config: Configuration dict used to generate (stored as JSONB)
            metadata: Generation metadata (stored as JSONB)
            articles_used: Number of articles actually used
            article_uris: List of article URIs used
            model_used: AI model used
            description: Optional description

        Returns:
            ID of the created saved executive briefing
        """
        try:
            from app.database_models import t_saved_executive_briefings
            from sqlalchemy import insert
            import json

            # Ensure articles is JSON-serializable
            articles_json = json.loads(json.dumps(articles, default=str)) if articles else []

            statement = insert(t_saved_executive_briefings).values(
                topic=topic,
                username=username,
                name=name,
                persona=persona,
                article_count=article_count,
                articles=articles_json,
                briefing_summary=briefing_summary,
                themes=themes,
                priority_actions=priority_actions,
                config=config,
                metadata=metadata,
                articles_used=articles_used,
                article_uris=article_uris,
                model_used=model_used,
                description=description
            ).returning(t_saved_executive_briefings.c.id)

            result = self._execute_with_rollback(statement)
            row = result.fetchone()
            self.logger.info(f"Created saved executive briefing '{name}' for user '{username}' (ID: {row[0]})")
            return row[0]
        except Exception as e:
            self.logger.error(f"Error creating saved executive briefing: {e}")
            raise

    def get_saved_executive_briefings_for_topic(
        self,
        topic: str,
        username: str
    ) -> list:
        """Get all saved executive briefings for a topic (user-scoped).

        Returns list of briefing summaries sorted by creation date desc.
        """
        try:
            from app.database_models import t_saved_executive_briefings
            from sqlalchemy import select

            statement = select(
                t_saved_executive_briefings.c.id,
                t_saved_executive_briefings.c.name,
                t_saved_executive_briefings.c.description,
                t_saved_executive_briefings.c.persona,
                t_saved_executive_briefings.c.article_count,
                t_saved_executive_briefings.c.created_at,
                t_saved_executive_briefings.c.updated_at,
                t_saved_executive_briefings.c.articles_used,
                t_saved_executive_briefings.c.model_used
            ).where(
                (t_saved_executive_briefings.c.topic == topic) &
                (t_saved_executive_briefings.c.username == username)
            ).order_by(
                t_saved_executive_briefings.c.created_at.desc()
            )

            results = self._execute_with_rollback(statement).fetchall()
            return [dict(r._mapping) for r in results]
        except Exception as e:
            self.logger.error(f"Error getting saved executive briefings for topic {topic}: {e}")
            return []

    def get_saved_executive_briefing_by_id(
        self,
        briefing_id: int,
        username: str
    ) -> dict:
        """Get a specific saved executive briefing by ID (user-scoped).

        Returns full briefing data or None if not found.
        """
        try:
            from app.database_models import t_saved_executive_briefings
            from sqlalchemy import select

            statement = select(t_saved_executive_briefings).where(
                (t_saved_executive_briefings.c.id == briefing_id) &
                (t_saved_executive_briefings.c.username == username)
            )

            result = self._execute_with_rollback(statement).fetchone()
            if result:
                return dict(result._mapping)
            return None
        except Exception as e:
            self.logger.error(f"Error retrieving saved executive briefing {briefing_id}: {e}")
            return None

    def delete_saved_executive_briefing(
        self,
        briefing_id: int,
        username: str
    ) -> bool:
        """Delete a saved executive briefing (user-scoped)."""
        try:
            from app.database_models import t_saved_executive_briefings
            from sqlalchemy import delete

            statement = delete(t_saved_executive_briefings).where(
                (t_saved_executive_briefings.c.id == briefing_id) &
                (t_saved_executive_briefings.c.username == username)
            )

            result = self._execute_with_rollback(statement)
            deleted = result.rowcount > 0
            if deleted:
                self.logger.info(f"Deleted saved executive briefing {briefing_id} for user '{username}'")
            return deleted
        except Exception as e:
            self.logger.error(f"Error deleting saved executive briefing {briefing_id}: {e}")
            return False

    def update_executive_briefing_article(
        self,
        briefing_id: int,
        username: str,
        article_index: int,
        article_updates: dict
    ) -> bool:
        """Update a specific article within a saved executive briefing.

        Args:
            briefing_id: Briefing ID
            username: Username (for ownership check)
            article_index: Index of the article to update
            article_updates: Dict of fields to update in the article

        Returns:
            True if updated, False otherwise
        """
        try:
            from app.database_models import t_saved_executive_briefings
            from sqlalchemy import select, update
            from datetime import datetime
            import json

            # First get the current briefing
            statement = select(t_saved_executive_briefings.c.articles).where(
                (t_saved_executive_briefings.c.id == briefing_id) &
                (t_saved_executive_briefings.c.username == username)
            )
            result = self._execute_with_rollback(statement).fetchone()
            if not result:
                return False

            articles = result[0] if result[0] else []

            # Check if article index is valid
            if article_index < 0 or article_index >= len(articles):
                self.logger.warning(f"Article index {article_index} out of range for briefing {briefing_id}")
                return False

            # Update the article
            articles[article_index] = {**articles[article_index], **article_updates, 'user_edited': True}

            # Update the briefing with modified articles
            update_stmt = update(t_saved_executive_briefings).where(
                (t_saved_executive_briefings.c.id == briefing_id) &
                (t_saved_executive_briefings.c.username == username)
            ).values(
                articles=json.loads(json.dumps(articles, default=str)),
                updated_at=datetime.utcnow()
            )

            self._execute_with_rollback(update_stmt)
            self.logger.info(f"Updated article {article_index} in briefing {briefing_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error updating article in briefing {briefing_id}: {e}")
            return False

    def get_eb_config(self, topic: str) -> dict:
        """Get Executive Briefing configuration for a topic.

        Returns default config if none exists.
        """
        try:
            from app.database_models import t_user_preferences
            from sqlalchemy import select
            import json

            # Look for EB config in user_preferences with key 'eb_config_{topic}'
            pref_key = f"eb_config_{topic}"
            statement = select(t_user_preferences.c.config_value).where(
                t_user_preferences.c.preference_key == pref_key
            )
            result = self._execute_with_rollback(statement).fetchone()

            if result and result[0]:
                return result[0]

            # Return default config
            return self._get_default_eb_config()
        except Exception as e:
            self.logger.error(f"Error getting EB config for topic {topic}: {e}")
            return self._get_default_eb_config()

    def update_eb_config(self, topic: str, username: str, config: dict) -> bool:
        """Update Executive Briefing configuration for a topic.

        Args:
            topic: Topic name
            username: Username
            config: Configuration dict

        Returns:
            True if successful, False otherwise
        """
        try:
            from app.database_models import t_user_preferences
            from sqlalchemy import insert
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            from datetime import datetime

            pref_key = f"eb_config_{topic}"

            # Upsert the config
            statement = pg_insert(t_user_preferences).values(
                username=username,
                preference_key=pref_key,
                config_value=config,
                updated_at=datetime.utcnow()
            ).on_conflict_do_update(
                constraint='uq_user_preference_key',
                set_={
                    'config_value': config,
                    'updated_at': datetime.utcnow()
                }
            )

            self._execute_with_rollback(statement)
            self.logger.info(f"Updated EB config for topic {topic} by user {username}")
            return True
        except Exception as e:
            self.logger.error(f"Error updating EB config for topic {topic}: {e}")
            return False

    def _get_default_eb_config(self) -> dict:
        """Return default Executive Briefing configuration."""
        return {
            "personas": {
                "CEO": {
                    "priorities": "Regulation, enterprise adoption, scaling limits, market dynamics, security/safety, workforce impact, strategic partnerships",
                    "risk_appetite": "moderate",
                    "focus": "business strategy, market positioning, competitive advantage, and regulatory compliance"
                },
                "CMO": {
                    "priorities": "Market trends, customer behavior, brand impact, advertising innovation, customer experience, competitive positioning",
                    "risk_appetite": "high",
                    "focus": "marketing strategies, customer engagement, brand differentiation, and market opportunities"
                },
                "CTO": {
                    "priorities": "Technical breakthroughs, infrastructure, scalability, development tools, architecture patterns, security vulnerabilities",
                    "risk_appetite": "high",
                    "focus": "technical architecture, development practices, technology stack decisions, and engineering excellence"
                },
                "CISO": {
                    "priorities": "Security threats, vulnerabilities, compliance requirements, risk management, data protection, incident response",
                    "risk_appetite": "low",
                    "focus": "security risks, compliance requirements, threat mitigation, and data protection"
                }
            },
            "default_persona": "CEO",
            "default_article_count": 6,
            "default_days_back": 1,
            "include_bias_analysis": True,
            "include_synthesis": True,
            "agents": {
                "selection": {
                    "model": None,
                    "temperature": 0.3
                },
                "analysis": {
                    "model": None,
                    "temperature": 0.4
                },
                "synthesis": {
                    "model": None,
                    "temperature": 0.5
                }
            }
        }

    # ========================================================================
    # SAVED SIGNAL REPORTS CRUD
    # ========================================================================

    def create_saved_signal_report(
        self,
        instruction_id: int,
        instruction_name: str,
        name: str,
        username: str = None,
        topic: str = None,
        description: str = None,
        report_prompt: str = None,
        report_content: str = None,
        alerts_data: list = None,
        article_uris: list = None,
        articles_used: int = None,
        config: dict = None,
        model_used: str = None
    ) -> int:
        """Create a new saved signal report.

        Args:
            instruction_id: Signal instruction ID
            instruction_name: Name of the signal instruction
            name: Report name
            username: Optional username
            topic: Optional topic
            description: Optional description
            report_prompt: The prompt used to generate the report
            report_content: Generated report content (markdown)
            alerts_data: Signal alerts that triggered this report
            article_uris: List of article URIs analyzed
            articles_used: Number of articles used
            config: Generation config
            model_used: AI model used

        Returns:
            ID of the created saved signal report
        """
        try:
            from app.database_models import t_saved_signal_reports
            from sqlalchemy import insert
            import json

            # Ensure alerts_data is JSON-serializable
            alerts_json = json.loads(json.dumps(alerts_data, default=str)) if alerts_data else []

            statement = insert(t_saved_signal_reports).values(
                instruction_id=instruction_id,
                instruction_name=instruction_name,
                name=name,
                username=username,
                topic=topic,
                description=description,
                report_prompt=report_prompt,
                report_content=report_content,
                alerts_data=alerts_json,
                article_uris=article_uris,
                articles_used=articles_used,
                config=config,
                model_used=model_used
            ).returning(t_saved_signal_reports.c.id)

            result = self._execute_with_rollback(statement)
            row = result.fetchone()
            self.logger.info(f"Created saved signal report '{name}' (ID: {row[0]})")
            return row[0]
        except Exception as e:
            self.logger.error(f"Error creating saved signal report: {e}")
            raise

    def get_saved_signal_reports(
        self,
        topic: str = None,
        username: str = None,
        instruction_id: int = None,
        limit: int = 100
    ) -> list:
        """Get saved signal reports with optional filters.

        Returns list of report summaries sorted by creation date desc.
        """
        try:
            from app.database_models import t_saved_signal_reports
            from sqlalchemy import select

            statement = select(
                t_saved_signal_reports.c.id,
                t_saved_signal_reports.c.instruction_id,
                t_saved_signal_reports.c.instruction_name,
                t_saved_signal_reports.c.name,
                t_saved_signal_reports.c.description,
                t_saved_signal_reports.c.topic,
                t_saved_signal_reports.c.articles_used,
                t_saved_signal_reports.c.model_used,
                t_saved_signal_reports.c.created_at
            )

            # Apply filters
            conditions = []
            if topic:
                conditions.append(t_saved_signal_reports.c.topic == topic)
            if username:
                conditions.append(t_saved_signal_reports.c.username == username)
            if instruction_id:
                conditions.append(t_saved_signal_reports.c.instruction_id == instruction_id)

            if conditions:
                from sqlalchemy import and_
                statement = statement.where(and_(*conditions))

            statement = statement.order_by(
                t_saved_signal_reports.c.created_at.desc()
            ).limit(limit)

            results = self._execute_with_rollback(statement).fetchall()
            return [dict(r._mapping) for r in results]
        except Exception as e:
            self.logger.error(f"Error getting saved signal reports: {e}")
            return []

    def get_saved_signal_report_by_id(
        self,
        report_id: int,
        username: str = None
    ) -> dict:
        """Get a specific saved signal report by ID.

        Returns full report data or None if not found.
        """
        try:
            from app.database_models import t_saved_signal_reports
            from sqlalchemy import select

            statement = select(t_saved_signal_reports).where(
                t_saved_signal_reports.c.id == report_id
            )

            # Optionally filter by username
            if username:
                statement = statement.where(
                    t_saved_signal_reports.c.username == username
                )

            result = self._execute_with_rollback(statement).fetchone()
            if result:
                return dict(result._mapping)
            return None
        except Exception as e:
            self.logger.error(f"Error retrieving saved signal report {report_id}: {e}")
            return None

    def delete_saved_signal_report(
        self,
        report_id: int,
        username: str = None
    ) -> bool:
        """Delete a saved signal report."""
        try:
            from app.database_models import t_saved_signal_reports
            from sqlalchemy import delete

            statement = delete(t_saved_signal_reports).where(
                t_saved_signal_reports.c.id == report_id
            )

            # Optionally filter by username
            if username:
                statement = statement.where(
                    t_saved_signal_reports.c.username == username
                )

            result = self._execute_with_rollback(statement)
            deleted = result.rowcount > 0
            if deleted:
                self.logger.info(f"Deleted saved signal report {report_id}")
            return deleted
        except Exception as e:
            self.logger.error(f"Error deleting saved signal report {report_id}: {e}")
            return False

    def update_saved_signal_report_content(
        self,
        report_id: int,
        report_content: str
    ) -> bool:
        """Update the content of a saved signal report.

        Args:
            report_id: ID of the report to update
            report_content: New report content (markdown)

        Returns:
            True if update was successful
        """
        try:
            from app.database_models import t_saved_signal_reports
            from sqlalchemy import update

            statement = update(t_saved_signal_reports).where(
                t_saved_signal_reports.c.id == report_id
            ).values(report_content=report_content)

            result = self._execute_with_rollback(statement)
            updated = result.rowcount > 0
            if updated:
                self.logger.info(f"Updated saved signal report {report_id} content")
            return updated
        except Exception as e:
            self.logger.error(f"Error updating saved signal report {report_id}: {e}")
            return False

    def get_signal_report_count(
        self,
        topic: str = None,
        username: str = None
    ) -> int:
        """Get count of saved signal reports."""
        try:
            from app.database_models import t_saved_signal_reports
            from sqlalchemy import select, func

            statement = select(func.count(t_saved_signal_reports.c.id))

            conditions = []
            if topic:
                conditions.append(t_saved_signal_reports.c.topic == topic)
            if username:
                conditions.append(t_saved_signal_reports.c.username == username)

            if conditions:
                from sqlalchemy import and_
                statement = statement.where(and_(*conditions))

            result = self._execute_with_rollback(statement).scalar()
            return result or 0
        except Exception as e:
            self.logger.error(f"Error getting signal report count: {e}")
            return 0

    # =====================================================
    # Keyword Relevance Analysis Methods
    # =====================================================

    def get_keyword_relevance_stats(self):
        """Get relevance statistics for all keywords across all groups.

        Returns aggregated stats including:
        - keyword_id, keyword, group_id, group_name, topic
        - total_matches, avg_relevance, avg_topic_alignment, avg_confidence
        - high_relevance_count (>=0.7), low_relevance_count (<0.4)
        """
        query = text("""
            WITH keyword_matches AS (
                -- Expand keyword_ids to individual keywords
                SELECT
                    kam.article_uri,
                    kam.group_id,
                    unnest(string_to_array(kam.keyword_ids, ','))::int as keyword_id
                FROM keyword_article_matches kam
            )
            SELECT
                mk.id as keyword_id,
                mk.keyword,
                kg.id as group_id,
                kg.name as group_name,
                kg.topic,
                COUNT(DISTINCT km.article_uri) as total_matches,
                ROUND(AVG(a.keyword_relevance_score)::numeric, 3) as avg_relevance,
                ROUND(AVG(a.topic_alignment_score)::numeric, 3) as avg_topic_alignment,
                ROUND(AVG(a.confidence_score)::numeric, 3) as avg_confidence,
                COUNT(DISTINCT CASE WHEN a.keyword_relevance_score >= 0.7 THEN km.article_uri END) as high_relevance_count,
                COUNT(DISTINCT CASE WHEN a.keyword_relevance_score < 0.4 THEN km.article_uri END) as low_relevance_count
            FROM monitored_keywords mk
            JOIN keyword_groups kg ON mk.group_id = kg.id
            LEFT JOIN keyword_matches km ON km.keyword_id = mk.id AND km.group_id = kg.id
            LEFT JOIN articles a ON km.article_uri = a.uri AND a.keyword_relevance_score IS NOT NULL
            GROUP BY mk.id, mk.keyword, kg.id, kg.name, kg.topic
            ORDER BY avg_relevance DESC NULLS LAST
        """)

        result = self._execute_with_rollback(query)
        return result.mappings().fetchall()

    def get_articles_for_keyword(self, keyword_id: int, group_id: int, relevance_filter: str = 'all', limit: int = 50):
        """Get articles matched to a specific keyword with relevance data.

        Args:
            keyword_id: The monitored_keywords.id
            group_id: The keyword_groups.id
            relevance_filter: 'all', 'high' (>=0.7), or 'low' (<0.4)
            limit: Maximum number of articles to return

        Returns articles with uri, title, news_source, publication_date,
        keyword_relevance_score, topic_alignment_score, confidence_score,
        overall_match_explanation, extracted_article_keywords
        """
        # Build relevance filter condition
        relevance_condition = ""
        if relevance_filter == 'high':
            relevance_condition = "AND a.keyword_relevance_score >= 0.7"
        elif relevance_filter == 'low':
            relevance_condition = "AND a.keyword_relevance_score < 0.4"

        query = text(f"""
            WITH keyword_matches AS (
                SELECT
                    kam.article_uri,
                    kam.group_id,
                    unnest(string_to_array(kam.keyword_ids, ','))::int as keyword_id
                FROM keyword_article_matches kam
                WHERE kam.group_id = :group_id
            )
            SELECT DISTINCT
                a.uri,
                a.title,
                a.news_source,
                a.publication_date,
                a.keyword_relevance_score,
                a.topic_alignment_score,
                a.confidence_score,
                a.overall_match_explanation,
                a.extracted_article_keywords
            FROM keyword_matches km
            JOIN articles a ON km.article_uri = a.uri
            WHERE km.keyword_id = :keyword_id
            AND a.keyword_relevance_score IS NOT NULL
            {relevance_condition}
            ORDER BY a.keyword_relevance_score DESC
            LIMIT :limit
        """)

        result = self._execute_with_rollback(query, {
            'keyword_id': keyword_id,
            'group_id': group_id,
            'limit': limit
        })
        return result.mappings().fetchall()

    def get_source_distribution_by_relevance(self, group_id: int = None):
        """Get news source distribution split by high/low relevance.

        Args:
            group_id: Optional group_id to filter by. If None, returns all sources.

        Returns sources with:
        - news_source, total_count, high_relevance_count, low_relevance_count
        - avg_relevance, bias
        """
        group_filter = "WHERE kam.group_id = :group_id" if group_id else ""

        query = text(f"""
            SELECT
                a.news_source,
                COUNT(DISTINCT a.uri) as total_count,
                COUNT(DISTINCT CASE WHEN a.keyword_relevance_score >= 0.7 THEN a.uri END) as high_relevance_count,
                COUNT(DISTINCT CASE WHEN a.keyword_relevance_score < 0.4 THEN a.uri END) as low_relevance_count,
                ROUND(AVG(a.keyword_relevance_score)::numeric, 3) as avg_relevance,
                MAX(a.bias) as bias
            FROM keyword_article_matches kam
            JOIN articles a ON kam.article_uri = a.uri
            {group_filter}
            AND a.keyword_relevance_score IS NOT NULL
            AND a.news_source IS NOT NULL
            AND a.news_source != ''
            GROUP BY a.news_source
            ORDER BY total_count DESC
            LIMIT 50
        """)

        params = {'group_id': group_id} if group_id else {}
        result = self._execute_with_rollback(query, params)
        return result.mappings().fetchall()

    def get_low_relevance_article_titles_for_keyword(self, keyword_id: int, threshold: float = 0.4, limit: int = 10):
        """Get sample low-relevance article titles for a keyword (for LLM analysis).

        Args:
            keyword_id: ID of the monitored keyword
            threshold: Relevance score threshold (default 0.4)
            limit: Maximum number of titles to return

        Returns list of titles from articles with keyword_relevance_score < threshold
        """
        query = text("""
            WITH keyword_matches AS (
                SELECT
                    kam.article_uri,
                    kam.group_id,
                    unnest(string_to_array(kam.keyword_ids, ','))::int as keyword_id
                FROM keyword_article_matches kam
            )
            SELECT a.title
            FROM keyword_matches km
            JOIN articles a ON km.article_uri = a.uri
            WHERE km.keyword_id = :keyword_id
            AND a.keyword_relevance_score IS NOT NULL
            AND a.keyword_relevance_score < :threshold
            ORDER BY a.keyword_relevance_score ASC
            LIMIT :limit
        """)

        result = self._execute_with_rollback(query, {
            'keyword_id': keyword_id,
            'threshold': threshold,
            'limit': limit
        })
        return [row['title'] for row in result.mappings().fetchall()]

    def get_low_relevance_articles_for_keyword(self, keyword_id: int, threshold: float = 0.4, limit: int = 10):
        """Get sample low-relevance articles with title and URL for a keyword.

        Args:
            keyword_id: ID of the monitored keyword
            threshold: Relevance score threshold (default 0.4)
            limit: Maximum number of articles to return

        Returns list of dicts with title and url from articles with keyword_relevance_score < threshold
        """
        query = text("""
            WITH keyword_matches AS (
                SELECT
                    kam.article_uri,
                    kam.group_id,
                    unnest(string_to_array(kam.keyword_ids, ','))::int as keyword_id
                FROM keyword_article_matches kam
            )
            SELECT a.title, a.url, a.keyword_relevance_score
            FROM keyword_matches km
            JOIN articles a ON km.article_uri = a.uri
            WHERE km.keyword_id = :keyword_id
            AND a.keyword_relevance_score IS NOT NULL
            AND a.keyword_relevance_score < :threshold
            ORDER BY a.keyword_relevance_score ASC
            LIMIT :limit
        """)

        result = self._execute_with_rollback(query, {
            'keyword_id': keyword_id,
            'threshold': threshold,
            'limit': limit
        })
        return [dict(row) for row in result.mappings().fetchall()]

    # =====================================================
    # Keyword Suggestion/Improvement Methods
    # =====================================================

    def get_monitored_keyword_by_id(self, keyword_id: int):
        """Get a monitored keyword by its ID.

        Returns dict with id, keyword, group_id, last_checked, topic, group_name
        """
        query = text("""
            SELECT
                mk.id,
                mk.keyword,
                mk.group_id,
                mk.last_checked,
                kg.topic,
                kg.name as group_name
            FROM monitored_keywords mk
            JOIN keyword_groups kg ON mk.group_id = kg.id
            WHERE mk.id = :keyword_id
        """)
        result = self._execute_with_rollback(query, {'keyword_id': keyword_id})
        row = result.mappings().fetchone()
        return dict(row) if row else None

    def get_keyword_relevance_stats_single(self, keyword_id: int):
        """Get relevance statistics for a single keyword.

        Returns dict with total_matches, avg_relevance, high_relevance_count, low_relevance_count
        """
        query = text("""
            WITH keyword_matches AS (
                SELECT
                    kam.article_uri,
                    kam.group_id,
                    unnest(string_to_array(kam.keyword_ids, ','))::int as keyword_id
                FROM keyword_article_matches kam
            )
            SELECT
                COUNT(DISTINCT km.article_uri) as total_matches,
                ROUND(AVG(a.keyword_relevance_score)::numeric, 3) as avg_relevance,
                COUNT(DISTINCT CASE WHEN a.keyword_relevance_score >= 0.7 THEN km.article_uri END) as high_relevance_count,
                COUNT(DISTINCT CASE WHEN a.keyword_relevance_score < 0.4 THEN km.article_uri END) as low_relevance_count
            FROM keyword_matches km
            JOIN articles a ON km.article_uri = a.uri
            WHERE km.keyword_id = :keyword_id
            AND a.keyword_relevance_score IS NOT NULL
        """)
        result = self._execute_with_rollback(query, {'keyword_id': keyword_id})
        row = result.mappings().fetchone()
        return dict(row) if row else None

    def get_keyword_group_by_id(self, group_id: int):
        """Get a keyword group by its ID.

        Returns dict with id, name, topic, created_at, provider, source
        """
        query = text("""
            SELECT id, name, topic, created_at, provider, source
            FROM keyword_groups
            WHERE id = :group_id
        """)
        result = self._execute_with_rollback(query, {'group_id': group_id})
        row = result.mappings().fetchone()
        return dict(row) if row else None

    def get_keywords_for_group(self, group_id: int):
        """Get all keywords in a group.

        Returns list of dicts with id, keyword, last_checked
        """
        query = text("""
            SELECT id, keyword, last_checked
            FROM monitored_keywords
            WHERE group_id = :group_id
            ORDER BY keyword
        """)
        result = self._execute_with_rollback(query, {'group_id': group_id})
        return [dict(row) for row in result.mappings().fetchall()]

    def update_monitored_keyword_text(self, keyword_id: int, new_keyword: str):
        """Update the text of a monitored keyword.

        Args:
            keyword_id: ID of the keyword to update
            new_keyword: New keyword text
        """
        query = text("""
            UPDATE monitored_keywords
            SET keyword = :new_keyword
            WHERE id = :keyword_id
        """)
        self._execute_with_rollback(query, {
            'keyword_id': keyword_id,
            'new_keyword': new_keyword
        })

    def save_keyword_suggestion(
        self,
        keyword_id: int,
        group_id: int,
        suggestion_type: str,
        suggested_keyword: str,
        reason: str,
        confidence: float,
        analyzed_articles: int,
        avg_relevance: float
    ) -> int:
        """Save a keyword improvement suggestion.

        Args:
            keyword_id: ID of the original keyword
            group_id: ID of the keyword group
            suggestion_type: 'replace', 'add', or 'exclude'
            suggested_keyword: The suggested keyword text
            reason: Explanation for the suggestion
            confidence: Confidence score (0-1)
            analyzed_articles: Number of articles analyzed
            avg_relevance: Average relevance at time of suggestion

        Returns:
            ID of the created suggestion
        """
        query = text("""
            INSERT INTO keyword_suggestions
                (keyword_id, group_id, suggestion_type, suggested_keyword, reason,
                 confidence, analyzed_articles, avg_relevance_at_creation)
            VALUES
                (:keyword_id, :group_id, :suggestion_type, :suggested_keyword, :reason,
                 :confidence, :analyzed_articles, :avg_relevance)
            RETURNING id
        """)
        result = self._execute_with_rollback(query, {
            'keyword_id': keyword_id,
            'group_id': group_id,
            'suggestion_type': suggestion_type,
            'suggested_keyword': suggested_keyword,
            'reason': reason,
            'confidence': confidence,
            'analyzed_articles': analyzed_articles,
            'avg_relevance': avg_relevance
        })
        row = result.fetchone()
        return row[0] if row else None

    def get_keyword_suggestion_by_id(self, suggestion_id: int):
        """Get a keyword suggestion by its ID.

        Returns dict with all suggestion fields
        """
        query = text("""
            SELECT
                id, keyword_id, group_id, suggestion_type, suggested_keyword,
                reason, confidence, status, analyzed_articles,
                avg_relevance_at_creation, created_at, resolved_at, resolved_by
            FROM keyword_suggestions
            WHERE id = :suggestion_id
        """)
        result = self._execute_with_rollback(query, {'suggestion_id': suggestion_id})
        row = result.mappings().fetchone()
        return dict(row) if row else None

    def update_keyword_suggestion_status(
        self,
        suggestion_id: int,
        status: str,
        resolved_by: str = None
    ):
        """Update the status of a keyword suggestion.

        Args:
            suggestion_id: ID of the suggestion to update
            status: New status ('pending', 'approved', 'rejected', 'expired')
            resolved_by: Username of the person who resolved it
        """
        query = text("""
            UPDATE keyword_suggestions
            SET status = :status,
                resolved_at = NOW(),
                resolved_by = :resolved_by
            WHERE id = :suggestion_id
        """)
        self._execute_with_rollback(query, {
            'suggestion_id': suggestion_id,
            'status': status,
            'resolved_by': resolved_by
        })

    def get_pending_suggestions_for_group(self, group_id: int):
        """Get all pending keyword suggestions for a group.

        Returns list of suggestion dicts
        """
        query = text("""
            SELECT
                ks.id, ks.keyword_id, ks.group_id, ks.suggestion_type,
                ks.suggested_keyword, ks.reason, ks.confidence, ks.status,
                ks.analyzed_articles, ks.avg_relevance_at_creation, ks.created_at,
                mk.keyword as original_keyword
            FROM keyword_suggestions ks
            JOIN monitored_keywords mk ON ks.keyword_id = mk.id
            WHERE ks.group_id = :group_id
            AND ks.status = 'pending'
            ORDER BY ks.created_at DESC
        """)
        result = self._execute_with_rollback(query, {'group_id': group_id})
        return [dict(row) for row in result.mappings().fetchall()]

    def get_suggestion_history_for_keyword(self, keyword_id: int, limit: int = 10):
        """Get suggestion history for a keyword.

        Returns list of suggestion dicts
        """
        query = text("""
            SELECT
                id, keyword_id, group_id, suggestion_type, suggested_keyword,
                reason, confidence, status, analyzed_articles,
                avg_relevance_at_creation, created_at, resolved_at, resolved_by
            FROM keyword_suggestions
            WHERE keyword_id = :keyword_id
            ORDER BY created_at DESC
            LIMIT :limit
        """)
        result = self._execute_with_rollback(query, {
            'keyword_id': keyword_id,
            'limit': limit
        })
        return [dict(row) for row in result.mappings().fetchall()]

    def get_article_filter_options(self, start_date: str = None, end_date: str = None, topic: str = None):
        """Get available filter options (sources, factuality, bias) for article list.

        Args:
            start_date: Optional start date filter (YYYY-MM-DD)
            end_date: Optional end date filter (YYYY-MM-DD HH:MM:SS)
            topic: Optional topic filter

        Returns:
            Dict with sources, factuality, and bias lists
        """
        # Build WHERE conditions
        conditions = [
            "sentiment IS NOT NULL",
            "publication_date IS NOT NULL",
            "title NOT LIKE '%Call@%'",
            "title NOT LIKE '%+91%'",
            "title NOT LIKE '%best%agency%'",
            "title NOT LIKE '%#1%'",
            "summary NOT LIKE '%Call@%'",
            "summary NOT LIKE '%phone%number%'",
            "news_source NOT LIKE '%medium.com/@%'"
        ]

        params = {}

        if start_date and end_date:
            conditions.append("publication_date >= :start_date")
            conditions.append("publication_date <= :end_date")
            params['start_date'] = start_date
            params['end_date'] = end_date

        if topic:
            conditions.append("""(
                topic = :topic
                OR title LIKE :topic_pattern
                OR summary LIKE :topic_pattern
            )""")
            params['topic'] = topic
            params['topic_pattern'] = f'%{topic}%'

        where_clause = " AND ".join(conditions)

        # Query for distinct sources with counts
        sources_query = text(f"""
            SELECT news_source as name, COUNT(*) as count
            FROM articles
            WHERE {where_clause}
            AND news_source IS NOT NULL
            AND news_source != ''
            GROUP BY news_source
            ORDER BY count DESC
            LIMIT 100
        """)

        # Query for distinct factuality levels with counts
        factuality_query = text(f"""
            SELECT factual_reporting as level, COUNT(*) as count
            FROM articles
            WHERE {where_clause}
            AND factual_reporting IS NOT NULL
            AND factual_reporting != ''
            GROUP BY factual_reporting
            ORDER BY count DESC
        """)

        # Query for distinct bias values with counts
        bias_query = text(f"""
            SELECT bias as level, COUNT(*) as count
            FROM articles
            WHERE {where_clause}
            AND bias IS NOT NULL
            AND bias != ''
            GROUP BY bias
            ORDER BY count DESC
        """)

        sources_result = self._execute_with_rollback(sources_query, params)
        sources = [{"name": row['name'], "count": row['count']} for row in sources_result.mappings().fetchall()]

        factuality_result = self._execute_with_rollback(factuality_query, params)
        factuality = [{"level": row['level'], "count": row['count']} for row in factuality_result.mappings().fetchall()]

        bias_result = self._execute_with_rollback(bias_query, params)
        bias = [{"level": row['level'], "count": row['count']} for row in bias_result.mappings().fetchall()]

        return {
            "sources": sources,
            "factuality": factuality,
            "bias": bias
        }

    # ========================================================================
    # DESK BRIEFINGS CRUD (Briefing Desk Feature)
    # ========================================================================

    def create_desk_briefing(
        self,
        name: str,
        username: str,
        description: str = None,
        topic: str = None
    ) -> int:
        """Create a new desk briefing.

        Args:
            name: Briefing name (required)
            username: Username (required)
            description: Optional description
            topic: Optional topic (briefings can be cross-topic)

        Returns:
            ID of the created briefing
        """
        try:
            from app.database_models import t_desk_briefings
            from sqlalchemy import insert

            statement = insert(t_desk_briefings).values(
                name=name,
                username=username,
                description=description,
                topic=topic,
                status='draft',
                articles_count=0,
                incidents_count=0
            ).returning(t_desk_briefings.c.id)

            result = self._execute_with_rollback(statement)
            row = result.fetchone()
            self.logger.info(f"Created desk briefing '{name}' for user '{username}' (ID: {row[0]})")
            return row[0]
        except Exception as e:
            self.logger.error(f"Error creating desk briefing: {e}")
            raise

    def get_desk_briefings_for_user(self, username: str) -> list:
        """Get all desk briefings for a user.

        Returns list of briefing summaries sorted by update date desc.
        """
        try:
            from app.database_models import t_desk_briefings
            from sqlalchemy import select

            statement = select(
                t_desk_briefings.c.id,
                t_desk_briefings.c.name,
                t_desk_briefings.c.description,
                t_desk_briefings.c.topic,
                t_desk_briefings.c.status,
                t_desk_briefings.c.articles_count,
                t_desk_briefings.c.incidents_count,
                t_desk_briefings.c.model_used,
                t_desk_briefings.c.created_at,
                t_desk_briefings.c.updated_at,
                t_desk_briefings.c.finalized_at
            ).where(
                t_desk_briefings.c.username == username
            ).order_by(
                t_desk_briefings.c.updated_at.desc()
            )

            results = self._execute_with_rollback(statement).fetchall()
            return [dict(r._mapping) for r in results]
        except Exception as e:
            self.logger.error(f"Error getting desk briefings for user {username}: {e}")
            return []

    def get_desk_briefing_by_id(self, briefing_id: int, username: str) -> dict:
        """Get a specific desk briefing by ID (user-scoped).

        Returns full briefing data or None if not found.
        """
        try:
            from app.database_models import t_desk_briefings
            from sqlalchemy import select

            statement = select(t_desk_briefings).where(
                (t_desk_briefings.c.id == briefing_id) &
                (t_desk_briefings.c.username == username)
            )

            result = self._execute_with_rollback(statement).fetchone()
            if result:
                return dict(result._mapping)
            return None
        except Exception as e:
            self.logger.error(f"Error retrieving desk briefing {briefing_id}: {e}")
            return None

    def update_desk_briefing(
        self,
        briefing_id: int,
        username: str,
        name: str = None,
        description: str = None
    ) -> bool:
        """Update desk briefing name/description.

        Args:
            briefing_id: Briefing ID
            username: Username (for ownership check)
            name: New name (optional)
            description: New description (optional)

        Returns:
            True if updated, False otherwise
        """
        try:
            from app.database_models import t_desk_briefings
            from sqlalchemy import update
            from datetime import datetime

            updates = {'updated_at': datetime.utcnow()}
            if name is not None:
                updates['name'] = name
            if description is not None:
                updates['description'] = description

            statement = update(t_desk_briefings).where(
                (t_desk_briefings.c.id == briefing_id) &
                (t_desk_briefings.c.username == username)
            ).values(**updates)

            result = self._execute_with_rollback(statement)
            updated = result.rowcount > 0
            if updated:
                self.logger.info(f"Updated desk briefing {briefing_id}")
            return updated
        except Exception as e:
            self.logger.error(f"Error updating desk briefing {briefing_id}: {e}")
            return False

    def delete_desk_briefing(self, briefing_id: int, username: str) -> bool:
        """Delete a desk briefing (user-scoped)."""
        try:
            from app.database_models import t_desk_briefings
            from sqlalchemy import delete

            statement = delete(t_desk_briefings).where(
                (t_desk_briefings.c.id == briefing_id) &
                (t_desk_briefings.c.username == username)
            )

            result = self._execute_with_rollback(statement)
            deleted = result.rowcount > 0
            if deleted:
                self.logger.info(f"Deleted desk briefing {briefing_id} for user '{username}'")
            return deleted
        except Exception as e:
            self.logger.error(f"Error deleting desk briefing {briefing_id}: {e}")
            return False

    def add_article_to_desk_briefing(
        self,
        briefing_id: int,
        username: str,
        article_data: dict
    ) -> bool:
        """Add an article to a desk briefing.

        Args:
            briefing_id: Briefing ID
            username: Username (for ownership check)
            article_data: Article data dict (must include 'uri')

        Returns:
            True if added, False otherwise
        """
        try:
            from app.database_models import t_desk_briefings
            from sqlalchemy import select, update
            from datetime import datetime
            import json

            # Get current briefing
            statement = select(
                t_desk_briefings.c.articles,
                t_desk_briefings.c.status
            ).where(
                (t_desk_briefings.c.id == briefing_id) &
                (t_desk_briefings.c.username == username)
            )
            result = self._execute_with_rollback(statement).fetchone()
            if not result:
                return False

            # Don't allow adding to finalized briefings
            if result[1] == 'finalized':
                self.logger.warning(f"Cannot add article to finalized briefing {briefing_id}")
                return False

            articles = result[0] if result[0] else []

            # Check for duplicate URI
            article_uri = article_data.get('uri') or article_data.get('url')
            if any(a.get('uri') == article_uri for a in articles):
                self.logger.info(f"Article {article_uri} already in briefing {briefing_id}")
                return True  # Already exists, consider success

            # Add the article
            articles.append(article_data)

            # Update briefing
            update_stmt = update(t_desk_briefings).where(
                (t_desk_briefings.c.id == briefing_id) &
                (t_desk_briefings.c.username == username)
            ).values(
                articles=json.loads(json.dumps(articles, default=str)),
                articles_count=len(articles),
                updated_at=datetime.utcnow()
            )

            self._execute_with_rollback(update_stmt)
            self.logger.info(f"Added article to briefing {briefing_id}, total: {len(articles)}")
            return True
        except Exception as e:
            self.logger.error(f"Error adding article to briefing {briefing_id}: {e}")
            return False

    def remove_article_from_desk_briefing(
        self,
        briefing_id: int,
        username: str,
        article_uri: str
    ) -> bool:
        """Remove an article from a desk briefing.

        Args:
            briefing_id: Briefing ID
            username: Username (for ownership check)
            article_uri: URI of the article to remove

        Returns:
            True if removed, False otherwise
        """
        try:
            from app.database_models import t_desk_briefings
            from sqlalchemy import select, update
            from datetime import datetime
            import json

            # Get current briefing
            statement = select(
                t_desk_briefings.c.articles,
                t_desk_briefings.c.status
            ).where(
                (t_desk_briefings.c.id == briefing_id) &
                (t_desk_briefings.c.username == username)
            )
            result = self._execute_with_rollback(statement).fetchone()
            if not result:
                return False

            # Don't allow modifying finalized briefings
            if result[1] == 'finalized':
                self.logger.warning(f"Cannot remove article from finalized briefing {briefing_id}")
                return False

            articles = result[0] if result[0] else []

            # Remove the article
            original_count = len(articles)
            articles = [a for a in articles if a.get('uri') != article_uri]

            if len(articles) == original_count:
                self.logger.warning(f"Article {article_uri} not found in briefing {briefing_id}")
                return False

            # Update briefing
            update_stmt = update(t_desk_briefings).where(
                (t_desk_briefings.c.id == briefing_id) &
                (t_desk_briefings.c.username == username)
            ).values(
                articles=json.loads(json.dumps(articles, default=str)),
                articles_count=len(articles),
                updated_at=datetime.utcnow()
            )

            self._execute_with_rollback(update_stmt)
            self.logger.info(f"Removed article from briefing {briefing_id}, remaining: {len(articles)}")
            return True
        except Exception as e:
            self.logger.error(f"Error removing article from briefing {briefing_id}: {e}")
            return False

    def add_incident_to_desk_briefing(
        self,
        briefing_id: int,
        username: str,
        incident_data: dict
    ) -> bool:
        """Add an incident to a desk briefing.

        Args:
            briefing_id: Briefing ID
            username: Username (for ownership check)
            incident_data: Incident data dict (must include 'name')

        Returns:
            True if added, False otherwise
        """
        try:
            from app.database_models import t_desk_briefings
            from sqlalchemy import select, update
            from datetime import datetime
            import json

            # Get current briefing
            statement = select(
                t_desk_briefings.c.incidents,
                t_desk_briefings.c.status
            ).where(
                (t_desk_briefings.c.id == briefing_id) &
                (t_desk_briefings.c.username == username)
            )
            result = self._execute_with_rollback(statement).fetchone()
            if not result:
                return False

            # Don't allow adding to finalized briefings
            if result[1] == 'finalized':
                self.logger.warning(f"Cannot add incident to finalized briefing {briefing_id}")
                return False

            incidents = result[0] if result[0] else []

            # Check for duplicate name
            incident_name = incident_data.get('name')
            if any(i.get('name') == incident_name for i in incidents):
                self.logger.info(f"Incident {incident_name} already in briefing {briefing_id}")
                return True  # Already exists, consider success

            # Add the incident
            incidents.append(incident_data)

            # Update briefing
            update_stmt = update(t_desk_briefings).where(
                (t_desk_briefings.c.id == briefing_id) &
                (t_desk_briefings.c.username == username)
            ).values(
                incidents=json.loads(json.dumps(incidents, default=str)),
                incidents_count=len(incidents),
                updated_at=datetime.utcnow()
            )

            self._execute_with_rollback(update_stmt)
            self.logger.info(f"Added incident to briefing {briefing_id}, total: {len(incidents)}")
            return True
        except Exception as e:
            self.logger.error(f"Error adding incident to briefing {briefing_id}: {e}")
            return False

    def remove_incident_from_desk_briefing(
        self,
        briefing_id: int,
        username: str,
        incident_name: str
    ) -> bool:
        """Remove an incident from a desk briefing.

        Args:
            briefing_id: Briefing ID
            username: Username (for ownership check)
            incident_name: Name of the incident to remove

        Returns:
            True if removed, False otherwise
        """
        try:
            from app.database_models import t_desk_briefings
            from sqlalchemy import select, update
            from datetime import datetime
            import json

            # Get current briefing
            statement = select(
                t_desk_briefings.c.incidents,
                t_desk_briefings.c.status
            ).where(
                (t_desk_briefings.c.id == briefing_id) &
                (t_desk_briefings.c.username == username)
            )
            result = self._execute_with_rollback(statement).fetchone()
            if not result:
                return False

            # Don't allow modifying finalized briefings
            if result[1] == 'finalized':
                self.logger.warning(f"Cannot remove incident from finalized briefing {briefing_id}")
                return False

            incidents = result[0] if result[0] else []

            # Remove the incident
            original_count = len(incidents)
            incidents = [i for i in incidents if i.get('name') != incident_name]

            if len(incidents) == original_count:
                self.logger.warning(f"Incident {incident_name} not found in briefing {briefing_id}")
                return False

            # Update briefing
            update_stmt = update(t_desk_briefings).where(
                (t_desk_briefings.c.id == briefing_id) &
                (t_desk_briefings.c.username == username)
            ).values(
                incidents=json.loads(json.dumps(incidents, default=str)),
                incidents_count=len(incidents),
                updated_at=datetime.utcnow()
            )

            self._execute_with_rollback(update_stmt)
            self.logger.info(f"Removed incident from briefing {briefing_id}, remaining: {len(incidents)}")
            return True
        except Exception as e:
            self.logger.error(f"Error removing incident from briefing {briefing_id}: {e}")
            return False

    def add_emerging_topic_to_desk_briefing(
        self,
        briefing_id: int,
        username: str,
        topic_data: dict
    ) -> bool:
        """Add an emerging topic to a desk briefing.

        Args:
            briefing_id: Briefing ID
            username: Username (for ownership check)
            topic_data: Emerging topic data dict (must include 'name')

        Returns:
            True if added, False otherwise
        """
        try:
            from app.database_models import t_desk_briefings
            from sqlalchemy import select, update
            from datetime import datetime
            import json

            # Get current briefing
            statement = select(
                t_desk_briefings.c.emerging_topics,
                t_desk_briefings.c.status
            ).where(
                (t_desk_briefings.c.id == briefing_id) &
                (t_desk_briefings.c.username == username)
            )
            result = self._execute_with_rollback(statement).fetchone()
            if not result:
                return False

            # Don't allow adding to finalized briefings
            if result[1] == 'finalized':
                self.logger.warning(f"Cannot add emerging topic to finalized briefing {briefing_id}")
                return False

            emerging_topics = result[0] if result[0] else []

            # Check for duplicate name
            topic_name = topic_data.get('name')
            if any(t.get('name') == topic_name for t in emerging_topics):
                self.logger.info(f"Emerging topic {topic_name} already in briefing {briefing_id}")
                return True  # Already exists, consider success

            # Add the emerging topic
            emerging_topics.append(topic_data)

            # Update briefing
            update_stmt = update(t_desk_briefings).where(
                (t_desk_briefings.c.id == briefing_id) &
                (t_desk_briefings.c.username == username)
            ).values(
                emerging_topics=json.loads(json.dumps(emerging_topics, default=str)),
                emerging_topics_count=len(emerging_topics),
                updated_at=datetime.utcnow()
            )

            self._execute_with_rollback(update_stmt)
            self.logger.info(f"Added emerging topic to briefing {briefing_id}, total: {len(emerging_topics)}")
            return True
        except Exception as e:
            self.logger.error(f"Error adding emerging topic to briefing {briefing_id}: {e}")
            return False

    def remove_emerging_topic_from_desk_briefing(
        self,
        briefing_id: int,
        username: str,
        topic_name: str
    ) -> bool:
        """Remove an emerging topic from a desk briefing.

        Args:
            briefing_id: Briefing ID
            username: Username (for ownership check)
            topic_name: Name of the emerging topic to remove

        Returns:
            True if removed, False otherwise
        """
        try:
            from app.database_models import t_desk_briefings
            from sqlalchemy import select, update
            from datetime import datetime
            import json

            # Get current briefing
            statement = select(
                t_desk_briefings.c.emerging_topics,
                t_desk_briefings.c.status
            ).where(
                (t_desk_briefings.c.id == briefing_id) &
                (t_desk_briefings.c.username == username)
            )
            result = self._execute_with_rollback(statement).fetchone()
            if not result:
                return False

            # Don't allow modifying finalized briefings
            if result[1] == 'finalized':
                self.logger.warning(f"Cannot remove emerging topic from finalized briefing {briefing_id}")
                return False

            emerging_topics = result[0] if result[0] else []

            # Remove the emerging topic
            original_count = len(emerging_topics)
            emerging_topics = [t for t in emerging_topics if t.get('name') != topic_name]

            if len(emerging_topics) == original_count:
                self.logger.warning(f"Emerging topic {topic_name} not found in briefing {briefing_id}")
                return False

            # Update briefing
            update_stmt = update(t_desk_briefings).where(
                (t_desk_briefings.c.id == briefing_id) &
                (t_desk_briefings.c.username == username)
            ).values(
                emerging_topics=json.loads(json.dumps(emerging_topics, default=str)),
                emerging_topics_count=len(emerging_topics),
                updated_at=datetime.utcnow()
            )

            self._execute_with_rollback(update_stmt)
            self.logger.info(f"Removed emerging topic from briefing {briefing_id}, remaining: {len(emerging_topics)}")
            return True
        except Exception as e:
            self.logger.error(f"Error removing emerging topic from briefing {briefing_id}: {e}")
            return False

    def finalize_desk_briefing(
        self,
        briefing_id: int,
        username: str,
        synthesis: str,
        themes: list,
        priority_actions: list,
        metadata: dict,
        model_used: str
    ) -> bool:
        """Finalize a desk briefing with AI-generated synthesis.

        Args:
            briefing_id: Briefing ID
            username: Username (for ownership check)
            synthesis: AI-generated synthesis text
            themes: List of theme dicts
            priority_actions: List of action dicts
            metadata: Generation metadata
            model_used: AI model used

        Returns:
            True if finalized, False otherwise
        """
        try:
            from app.database_models import t_desk_briefings
            from sqlalchemy import update
            from datetime import datetime
            import json

            update_stmt = update(t_desk_briefings).where(
                (t_desk_briefings.c.id == briefing_id) &
                (t_desk_briefings.c.username == username)
            ).values(
                synthesis=synthesis,
                themes=json.loads(json.dumps(themes, default=str)) if themes else None,
                priority_actions=json.loads(json.dumps(priority_actions, default=str)) if priority_actions else None,
                metadata=json.loads(json.dumps(metadata, default=str)) if metadata else None,
                model_used=model_used,
                status='finalized',
                finalized_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

            result = self._execute_with_rollback(update_stmt)
            finalized = result.rowcount > 0
            if finalized:
                self.logger.info(f"Finalized desk briefing {briefing_id}")
            return finalized
        except Exception as e:
            self.logger.error(f"Error finalizing desk briefing {briefing_id}: {e}")
            return False

    def update_desk_briefing_synthesis(
        self,
        briefing_id: int,
        username: str,
        synthesis: str
    ) -> bool:
        """Update just the synthesis text of a desk briefing.

        Args:
            briefing_id: Briefing ID
            username: Username (for ownership check)
            synthesis: Updated synthesis text (markdown supported)

        Returns:
            True if updated, False otherwise
        """
        try:
            from app.database_models import t_desk_briefings
            from sqlalchemy import update
            from datetime import datetime

            update_stmt = update(t_desk_briefings).where(
                (t_desk_briefings.c.id == briefing_id) &
                (t_desk_briefings.c.username == username)
            ).values(
                synthesis=synthesis,
                updated_at=datetime.utcnow()
            )

            result = self._execute_with_rollback(update_stmt)
            updated = result.rowcount > 0
            if updated:
                self.logger.info(f"Updated synthesis for desk briefing {briefing_id}")
            return updated
        except Exception as e:
            self.logger.error(f"Error updating synthesis for desk briefing {briefing_id}: {e}")
            return False

    def reopen_desk_briefing(self, briefing_id: int, username: str) -> bool:
        """Reopen a finalized desk briefing to allow adding more content.

        Args:
            briefing_id: Briefing ID
            username: Username (for ownership check)

        Returns:
            True if reopened, False otherwise
        """
        try:
            from app.database_models import t_desk_briefings
            from sqlalchemy import update
            from datetime import datetime

            update_stmt = update(t_desk_briefings).where(
                (t_desk_briefings.c.id == briefing_id) &
                (t_desk_briefings.c.username == username) &
                (t_desk_briefings.c.status == 'finalized')
            ).values(
                status='draft',
                updated_at=datetime.utcnow()
            )

            result = self._execute_with_rollback(update_stmt)
            reopened = result.rowcount > 0
            if reopened:
                self.logger.info(f"Reopened desk briefing {briefing_id}")
            return reopened
        except Exception as e:
            self.logger.error(f"Error reopening desk briefing {briefing_id}: {e}")
            return False

    def update_desk_briefing_priority_actions(
        self,
        briefing_id: int,
        username: str,
        priority_actions: list
    ) -> bool:
        """Update just the priority actions of a desk briefing.

        Args:
            briefing_id: Briefing ID
            username: Username (for ownership check)
            priority_actions: Updated list of priority actions

        Returns:
            True if updated, False otherwise
        """
        try:
            from app.database_models import t_desk_briefings
            from sqlalchemy import update
            from datetime import datetime

            update_stmt = update(t_desk_briefings).where(
                (t_desk_briefings.c.id == briefing_id) &
                (t_desk_briefings.c.username == username)
            ).values(
                priority_actions=json.dumps(priority_actions) if priority_actions else '[]',
                updated_at=datetime.utcnow()
            )

            result = self._execute_with_rollback(update_stmt)
            updated = result.rowcount > 0
            if updated:
                self.logger.info(f"Updated priority actions for desk briefing {briefing_id}")
            return updated
        except Exception as e:
            self.logger.error(f"Error updating priority actions for desk briefing {briefing_id}: {e}")
            return False

    def update_desk_briefing_themes(
        self,
        briefing_id: int,
        username: str,
        themes: list
    ) -> bool:
        """Update just the themes of a desk briefing.

        Args:
            briefing_id: Briefing ID
            username: Username (for ownership check)
            themes: Updated list of themes

        Returns:
            True if updated, False otherwise
        """
        try:
            from app.database_models import t_desk_briefings
            from sqlalchemy import update
            from datetime import datetime

            update_stmt = update(t_desk_briefings).where(
                (t_desk_briefings.c.id == briefing_id) &
                (t_desk_briefings.c.username == username)
            ).values(
                themes=json.dumps(themes) if themes else '[]',
                updated_at=datetime.utcnow()
            )

            result = self._execute_with_rollback(update_stmt)
            updated = result.rowcount > 0
            if updated:
                self.logger.info(f"Updated themes for desk briefing {briefing_id}")
            return updated
        except Exception as e:
            self.logger.error(f"Error updating themes for desk briefing {briefing_id}: {e}")
            return False

    def get_draft_desk_briefings_count(self, username: str) -> int:
        """Get count of draft desk briefings for a user.

        Returns count of briefings with status='draft'.
        """
        try:
            from app.database_models import t_desk_briefings
            from sqlalchemy import select, func

            statement = select(func.count()).where(
                (t_desk_briefings.c.username == username) &
                (t_desk_briefings.c.status == 'draft')
            )

            result = self._execute_with_rollback(statement).scalar()
            return result or 0
        except Exception as e:
            self.logger.error(f"Error getting draft briefings count for {username}: {e}")
            return 0