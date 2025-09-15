from datetime import datetime, timedelta
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
                        case)

from app.routes.keyword_monitor import KeywordGroup
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
                             t_keyword_monitor_checks as keyword_monitor_checks,
                             t_raw_articles as raw_articles,
                             t_paper_search_results as paper_search_results,
                             t_news_search_results as news_search_results,
                             t_keyword_alert_articles as keyword_alert_articles)


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
        self.connection.begin()
        try:
            inserted_new_article = False
            if not article_exists:
                # Save new article
                self.connection.execute(insert(articles).values(
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

            # Create alert
            is_keyword_alert_exists = self.connection.execute(
                        select(keyword_alerts).where(keyword_alerts.c.article_uri == article_url, keyword_alerts.c.keyword_id == keyword_id)
                    ).fetchone()

            alert_inserted = False
            if not is_keyword_alert_exists:
                result = self.connection.execute(insert(keyword_alerts).values(
                    keyword_id=keyword_id,
                    article_uri=article_url))
                alert_inserted = result.rowcount > 0
            
            # Get the group_id for this keyword
            group_id = self.connection.execute(
                select(monitored_keywords.c.group_id).where(monitored_keywords.c.id == keyword_id)
            ).fetchone().scalar()
            
            # Check if we already have a match for this article in this group
            existing_match = self.connection.execute(select(keyword_article_matches.c.id, keyword_article_matches.c.keyword_ids).where(
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
                    result = self.connection.execute(update(keyword_article_matches).where(
                        keyword_article_matches.c.id == match_id
                        ).values(keyword_ids = updated_keyword_ids))

                    match_updated = True
            else:
                # Create a new match
                self.connection.execute(insert(keyword_article_matches).values(
                    article_uri=article_url,
                    keyword_ids=str(keyword_id),
                    group_id=group_id))

                match_updated = True
                
            self.connection.commit()

            return inserted_new_article, alert_inserted, match_updated

        except Exception as e:
            self.connection.rollback()
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
        existing = self.connection.execute(select(keyword_monitor_status).where(keyword_monitor_status.c.id == 1)).fetchone()
        if existing:
            self.connection.execute(update(keyword_monitor_status).where(keyword_monitor_status.c.id == 1).values(last_check_time = params[0], last_error = params[1], requests_today = params[2]))
        else:
            self.connection.execute(insert(keyword_monitor_status).values(id = 1, last_check_time = params[0], last_error = params[1], requests_today = params[2]))

        self.connection.commit()

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
        self.connection.execute(statement)
        self.connection.commit()

    async def move_alert_to_articles(self, url: str) -> None:
        statement = select(
            keyword_alert_articles
        ).where(
            keyword_alert_articles.c.url == url,
            keyword_alert_articles.c.moved_to_articles == False
        )
        alert = self.connection.execute(statement).fetchone()
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
            self.connection.execute(statement)
            
            statement = update(
                keyword_alert_articles
            ).where(
                keyword_alert_articles.c.url == url
            ).values(
                moved_to_articles = True
            )
            self.connection.execute(statement)
            self.connection.commit()

    #### REINDEX CHROMA DB QUERIES ####
    def get_iter_articles(self, limit: int | None = None):  

        statement = select(articles, raw_articles.c.raw_markdown.label('raw')).select_from(
            articles.outerjoin(raw_articles, articles.c.uri == raw_articles.c.uri)
        ).order_by(articles.c.rowid)

        if limit:
            statement = statement.limit(limit)

        return self.connection.execute(statement).mappings().fetchall()

    def save_analysis_version(self, params):
        statement = insert(
            analysis_versions
        ).values(
            topic=params[0],
            version_data=params[1],
            model_used=params[2],
            analysis_depth=params[3]
        )
        self.connection.execute(statement)
        self.connection.commit()

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
        
        return self.connection.execute(statement)

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
        statement = select(
            articles.c.future_signal,
            func.count().label('count')
        ).where(
            and_(
                articles.c.topic == topic_name,
                articles.c.future_signal != None,
                articles.c.future_signal != '',
                articles.c.analyzed == 1
            )
        ).group_by(
            articles.c.future_signal
        ).order_by(
            desc(func.count())
        )
        return self.connection.execute(statement).fetchall()

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
        is_email_exists = self.is_oauth_user_allowed(email)
        if is_email_exists:
            update_statement = update(oauth_allowlist).where(oauth_allowlist.c.email == email).values(email = email, added_by = added_by)
            self.connection.execute(update_statement)
        else:
            insert_statement = insert(oauth_allowlist).values(email = email, added_by = added_by)
            self.connection.execute(insert_statement)

        self.connection.commit()

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
        statement = insert(
            oauth_users
        ).values(
            email=params[0],
            name=params[1],
            provider=params[2],
            provider_id=params[3],
            avatar_url=params[4]
        )
        result =self.connection.execute(statement)
        self.connection.commit()

        return result.inserted_primary_key[0]

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
        #count allowlist entries
        statement = select(
            func.count()
        ).select_from(
            oauth_allowlist
        ).where(
            oauth_allowlist.c.is_active == 1
        )
        allowlist_count = self.connection.execute(statement).fetchone().scalar()
        
        #count Oauth users
        statement = select(
            func.count()
        ).select_from(
            oauth_users
        ).where(
            oauth_users.c.is_active == 1
        )
        oauth_users_count = self.connection.execute(statement).fetchone().scalar()
        
        #get recent logins
        statement = select(
            oauth_users.c.provider,
            func.count().label('count')
        ).where(
            oauth_users.c.is_active == 1
        ).group_by(
            oauth_users.c.provider
        )
        provider_stats = {row[0]: row[1] for row in self.connection.execute(statement).fetchall()}
        
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
        # Get total items count
        statement = select(
            func.count()
        ).select_from(
            feed_items
        ).where(
            feed_items.c.group_id == group_id
        )

        total_items = self.connection.execute(statement).fetchone().scalar()
        
        # Get counts by source type
        statement = select(
            feed_items.c.source_type,
            func.count().label('count')
        ).where(
            feed_items.c.group_id == group_id
        ).group_by(
            feed_items.c.source_type
        )
        source_counts = dict(self.connection.execute(statement).fetchall())

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
        recent_items = self.connection.execute(statement).fetchone().scalar()

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
        statement = select(
            func.count()
        ).select_from(
            articles
        ).where(
            func.lower(articles.c.topic) == func.lower(params[0]),
            articles.c.category.in_(placeholders)
        )
        return self.connection.execute(statement).fetchone().scalar()

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

        return self.connection.execute(statement).fetchall()

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
        return self.connection.execute(statement).fetchone()

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
        # Query for articles that have a non-null and non-empty category
        statement = select(articles).where(
            articles.c.category.isnot(None),
            articles.c.category != ''
        ).order_by(
            articles.c.submission_date.desc()
        ).limit(limit)

        articles_list = self.connection.execute(statement).mappings().fetchall()

        articles = []
        for article in articles_list:
            if article.get('tags'):
                article['tags'] = article['tags'].split(',')
            else:
                article['tags'] = []

            articles.append(article)

        return articles

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

        result = self.connection.execute(statement)
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
        self.connection.execute(statement)
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
        self.connection.execute(statement)
        self.connection.commit()

    def update_run_status(self, params):
        statement = update(model_bias_arena_runs).where(model_bias_arena_runs.c.id == params[1]).values(
                status=params[0],
                completed_at=func.current_timestamp()
            )

        self.connection.execute(statement)
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

        return self.connection.execute(statement).fetchone()                         

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

        return self.connection.execute(statement).fetchall()

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
        return self.connection.execute(statement).fetchall()

    def delete_run(self, run_id):
        statement = delete(model_bias_arena_runs).where(model_bias_arena_runs.c.id == run_id)
        result = self.connection.execute(statement)
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

        return self.connection.execute(statement).fetchone()

    def get_run_articles(self, run_id):
        statement = select(
            model_bias_arena_articles.c.article_uri,
            model_bias_arena_articles.c.article_title,
            model_bias_arena_articles.c.article_summary
        ).where(model_bias_arena_articles.c.run_id == run_id)

        return self.connection.execute(statement).fetchall()

    def get_all_bias_evaluation_runs(self):
        statement = select(
            model_bias_arena_articles.c.id,
            model_bias_arena_articles.c.name,
            model_bias_arena_articles.c.description,
            model_bias_arena_articles.c.benchmark_model,
            model_bias_arena_articles.c.selected_models,
            model_bias_arena_articles.c.article_count,
            model_bias_arena_articles.c.rounds,
            model_bias_arena_articles.c.current_round,
            model_bias_arena_articles.c.created_at,
            model_bias_arena_articles.c.completed_at,
            model_bias_arena_articles.c.status
        ).order_by(
            model_bias_arena_articles.c.created_at.desc()
        )

        return self.connection.execute(statement).fetchall()

    def update_run(self, params):
        statement = update(model_bias_arena_runs).where(
            model_bias_arena_runs.c.id == params[1]
        ).values(
                current_round=params[0]
        )

        self.connection.execute(statement)
        self.connection.commit()

    def get_topics_from_article(self, article_url):
        statement = select(
            articles.c.topic
        ).where(
            articles.c.uri == article_url
        ).distinct()

        return self.connection.execute(statement).fetchone()

    def get_run_info(self, run_id):
        statement = select(
            model_bias_arena_runs.c.rounds,
            model_bias_arena_runs.c.current_round
        ).where(
            model_bias_arena_runs.c.id == run_id
        )

        return self.connection.execute(statement).fetchone()

    def add_articles_to_run(self, params):
        statement = insert(model_bias_arena_articles).values(
            run_id=params[0],
            article_uri=params[1],
            article_title=params[2],
            article_summary=params[3]
        )
        self.connection.execute(statement)
        self.connection.commit()

    def sample_articles(self, count, topic):
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
            articles.c.summary.isnot(None),
            func.length(articles.c.summary) > 100,
            articles.c.analyzed == 1,
            articles.c.sentiment.isnot(None),
            articles.c.sentiment != '',
            articles.c.future_signal.isnot(None),
            articles.c.future_signal != '',
            articles.c.time_to_impact.isnot(None),
            articles.c.time_to_impact != '',
            articles.c.driver_type.isnot(None),
            articles.c.driver_type != '',
            articles.c.category.isnot(None),
            articles.c.category != '',
            articles.c.news_source.isnot(None),
            articles.c.news_source != ''
        )

        if topic:
            statement = statement.where(
                articles.c.topic == topic
            )

        statement = statement.order_by(
            func.random()
        ).limit(count)

        return self.connection.execute(statement).fetchall()

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
        
        db_topics = {row[0]: {"article_count": row[1], "last_article_date": row[2]}
                        for row in self.connection.execute(statement).fetchall()}
        return db_topics

    def debug_articles(self):
        statement = select(articles)
        articles = self.connection.execute(statement).fetchall()
        return articles

    def get_rate_limit_status(self):
        statement = select(
            keyword_monitor_status.c.requests_today,
            keyword_monitor_status.c.last_error
        ).where(
            keyword_monitor_status.c.id == 1
        )
        return self.connection.execute(statement).fetchone()

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

        return self.connection.execute(statement).fetchall()

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

        return self.connection.execute(statement).fetchone()

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

        return self.connection.execute(statement).fetchall()

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

        return self.connection.execute(statement).fetchall()

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

        return self.connection.execute(statement).fetchall()

    def create_podcast(self, params):
        statement = insert(podcasts).values(
            id=params[0],
            title=params[1],
            created_at=func.current_timestamp(),
            status= 'processing',
            config=params[2],
            article_uris=params[3]
        )
        self.connection.execute(statement)
        self.connection.commit()

    def update_podcast_status(self, params):
        statement = update(podcasts).where(podcasts.c.id == params[3]).values(
                status=params[0],
                audio_url=params[1],
                transcript=params[2]
            )
        self.connection.execute(statement)
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

        return self.connection.execute(statement).fetchall()

    def create_keyword_monitor_group(self, params):
        statement = insert(keyword_groups).values(
            name=params[0],
            topic=params[1]
        )
        result =self.connection.execute(statement)
        self.connection.commit()

        return result.inserted_primary_key[0]

    def create_keyword(self, params):
        statement = insert(monitored_keywords).values(
            group_id=params[0],
            keyword=params[1]
        )
        self.connection.execute(statement)
        self.connection.commit()

    def delete_keyword(self, keyword_id):
        statement = delete(monitored_keywords).where(monitored_keywords.c.id == keyword_id)
        self.connection.execute(statement)
        self.connection.commit()

    def delete_keyword_group(self, group_id):
        statement = delete(keyword_groups).where(keyword_groups.c.id == group_id)
        self.connection.execute(statement)
        self.connection.commit()

    def delete_group_keywords(self, group_id):
        statement = delete(monitored_keywords).where(monitored_keywords.c.group_id == group_id)
        self.connection.execute(statement)
        self.connection.commit()

    def create_group(self, group_name, group_topic):
        statement = insert(keyword_groups).values(
            name=group_name,
            topic=group_topic
        )
        result = self.connection.execute(statement)
        self.connection.commit()

        return result.inserted_primary_key[0]

    def add_keywords_to_group(self, group_id, keyword):
        statement = insert(monitored_keywords).values(
            group_id=group_id,
            keyword=keyword
        )
        self.connection.execute(statement)
        self.connection.commit()

    def get_all_group_ids_associated_to_topic(self, topic_name):
        statement = select(
            keyword_groups.c.id
        ).where(
            keyword_groups.c.topic == topic_name
        )
        return self.connection.execute(statement).fetchall()

    def get_keyword_ids_associated_to_group(self, group_id):
        statement = select(
            monitored_keywords.c.id
        ).where(
            monitored_keywords.c.group_id == group_id
        )
        return self.connection.execute(statement).fetchall()

    def get_keywords_associated_to_group(self, group_id):
        statement = select(
            monitored_keywords.c.keyword
        ).where(
            monitored_keywords.c.group_id == group_id
        )

        return [row[0] for row in self.connection.execute(statement).fetchall()]

    def get_keywords_associated_to_group_ordered_by_keyword(self, group_id):
        statement = select(
            monitored_keywords.c.keyword
        ).where(
            monitored_keywords.c.group_id == group_id
        ).order_by(
            monitored_keywords.c.keyword
        )

        return [row[0] for row in self.connection.execute(statement).fetchall()]

    def delete_keyword_article_matches_from_new_table_structure(self, group_id):
        statement = delete(keyword_article_matches).where(keyword_article_matches.c.group_id == group_id)
        result = self.connection.execute(statement)
        self.connection.commit()

        return result.rowcount

    def delete_keyword_article_matches_from_old_table_structure(self, ids_str, keyword_ids):
        statement = delete(keyword_alerts).where(keyword_alerts.c.keyword_id.in_(keyword_ids))
        result = self.connection.execute(statement)
        self.connection.commit()

        return result.rowcount

    def delete_groups_keywords(self, ids_str, group_ids):
        statement = delete(monitored_keywords).where(monitored_keywords.c.group_id.in_(group_ids))
        result = self.connection.execute(statement)
        self.connection.commit()

        return result.rowcount

    def delete_all_keyword_groups(self, topic_name):
        statement = delete(keyword_groups).where(keyword_groups.c.topic == topic_name)
        result = self.connection.execute(statement)
        self.connection.commit()

        return result.rowcount

    def check_if_alert_id_exists_in_new_table_structure(self, alert_id):
        statement = select(
            keyword_article_matches.c.id
        ).where(
            keyword_article_matches.c.id == alert_id
        )

        return self.connection.execute(statement).fetchone()

    def mark_alert_as_read_or_unread_in_new_table(self, alert_id, read_or_unread):
        statement = update(keyword_article_matches).where(keyword_article_matches.c.id == alert_id).values(is_read = read_or_unread)

        self.connection.execute(statement)
        self.connection.commit()

    def mark_alert_as_read_or_unread_in_old_table(self, alert_id, read_or_unread):
        statement = update(keyword_alerts).where(keyword_alerts.c.id == alert_id).values(is_read = read_or_unread)

        self.connection.execute(statement)
        self.connection.commit()

    def get_number_of_monitored_keywords_by_group_id(self, group_id):
        statement = select(
            func.count()
        ).select_from(
            monitored_keywords
        ).where(
            monitored_keywords.c.group_id == group_id
        )

        return self.connection.execute(statement).fetchone().scalar()

    def get_total_number_of_keywords(self):
        statement = select(
            func.count()
        ).select_from(
            monitored_keywords
        )

        return self.connection.execute(statement).fetchone().scalar()

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

        return columns, self.connection.execute(statement).fetchall()

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

        return self.connection.execute(statement).fetchone()

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
            articles.c.extracted_article_keywords
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

        return self.connection.execute(statement).fetchall()

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

        return self.connection.execute(statement).fetchall()

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

        return self.connection.execute(statement).fetchone().scalar()

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
        
        return [row[0] for row in self.connection.execute(statement).fetchall()]

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
        
        return [row[0] for row in self.connection.execute(statement).fetchall()]

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
        
        return self.connection.execute(statement).fetchone()

    def create_keyword_monitor_table_if_not_exists_and_insert_default_value(self):
        # TODO: Move to migrations.

        # Check if the keyword_monitor_status table has a row with id 1
        statement = select(keyword_monitor_status).where(keyword_monitor_status.c.id == 1)
        existing = self.connection.execute(statement).fetchone()

        if not existing:
            statement = insert(keyword_monitor_status).values(
                id = 1,
                requests_today = 0
            )
            self.connection.execute(statement)
            self.connection.commit()

    def check_keyword_monitor_status_and_settings_tables(self):
        status_data_stmt = select(keyword_monitor_status).where(keyword_monitor_status.c.id == 1)
        status_data = self.connection.execute(status_data_stmt).fetchone()

        settings_data_stmt = select(keyword_monitor_settings).where(keyword_monitor_settings.c.id == 1)
        settings_data = self.connection.execute(settings_data_stmt).fetchone()

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

        return self.connection.execute(statement).fetchone().scalar()


    def get_settings_and_status_together(self):
        kms_subq = select(
            keyword_monitor_status.c.id,
            keyword_monitor_status.c.requests_today,
            keyword_monitor_status.c.last_error
        ).where(
            keyword_monitor_status.c.id == 1,
            keyword_monitor_status.c.last_reset_date == func.current_date()
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
            kms_subq.c.last_error
        ).select_from(
            keyword_monitor_settings.join(
                kms_subq,
                kms_subq.c.id == 1,
                isouter=True
            )
        ).where(keyword_monitor_settings.c.id == 1)

        return self.connection.execute(statement).fetchone()

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
            if self.connection.execute(
                select(keyword_monitor_settings).where(keyword_monitor_settings.c.id == 1)
            ).fetchone()
            else insert(keyword_monitor_settings).values(**values_dict)
        )

        self.connection.execute(stmt)
        self.connection.commit()


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
        statement = select(
            articles.c.topic
        ).where(articles.c.topic == topic).limit(1)

        return self.connection.execute(statement).fetchone() is not None

    def get_keyword_group_id_by_name_and_topic(self, group_name, topic_name):
        statement = select(
            keyword_groups.c.id
        ).where(
            keyword_groups.c.name == group_name,
            keyword_groups.c.topic == topic_name
        )

        return self.connection.execute(statement).fetchone()

    def toggle_polling(self, toggle):
        statement = select(
            keyword_monitor_settings.c.id
        ).where(
            keyword_monitor_settings.c.id == 1
        )

        # First check if settings exist
        settings_exists = self.connection.execute(statement).fetchone() is not None

        if settings_exists:
            # Just update is_enabled if settings exist
            statement = update(keyword_monitor_settings).where(keyword_monitor_settings.c.id == 1).values(is_enabled = toggle.enabled)
            self.connection.execute(statement)
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
            self.connection.execute(statement)
            
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
        
        return self.connection.execute(statement).fetchall()

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

        return self.connection.execute(statement).fetchall()

    def save_keyword_alert(self, article_data):
        is_keyword_alert_exists = self.connection.execute(select(keyword_alert_articles).where(keyword_alert_articles.c.url == article_data['url'])).fetchone()
        if not is_keyword_alert_exists:
            statement = insert(keyword_alert_articles).values(
                url = article_data['url'],
                title = article_data['title'],
                summary = article_data['summary'],
                source = article_data['source'],
                topic = article_data['topic'],
                keywords = ','.join(article_data['matched_keywords'])
            )
            self.connection.execute(statement)
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

        return self.connection.execute(statement).fetchall()

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

        return self.connection.execute(statement).fetchall()

    def count_unread_articles_by_group_id_from_new_table_structure(self, group_id):
        statement = select(
            func.count(keyword_article_matches.c.id)
        ).select_from(
            keyword_article_matches
        ).where(
            keyword_article_matches.c.group_id == group_id,
            keyword_article_matches.c.is_read == 0
        )
        
        return self.connection.execute(statement).fetchone().scalar()

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
        
        return self.connection.execute(statement).fetchone().scalar()

    def count_total_articles_by_group_id_from_new_table_structure(self, group_id):
        statement = select(
            func.count(keyword_article_matches.c.id)
        ).select_from(
            keyword_article_matches
        ).where(
            keyword_article_matches.c.group_id == group_id
        )

        return self.connection.execute(statement).fetchone().scalar()

    def count_total_articles_by_group_id_from_old_table_structure(self, group_id):
        statement = select(
            func.count(keyword_alerts.c.id)
        ).select_from(
            keyword_alerts.join(
                monitored_keywords,
                keyword_alerts.c.keyword_id == monitored_keywords.c.id
            )
        ).where(
            monitored_keywords.c.group_id == group_id
        )

        return self.connection.execute(statement).fetchone().scalar()

    def update_media_bias(self, source):
        statement = update(mediabias).where(mediabias.c.source == source).values(enabled = 1)
        self.connection.execute(statement)
        self.connection.commit()

    def get_group_name(self, group_id):
        statement = select(
            keyword_groups.c.name
        ).where(
            keyword_groups.c.id == group_id
        )

        group_name = self.connection.execute(statement).fetchone().scalar()

        return group_name if group_name else "Unknown Group"

    def get_article_urls_from_news_search_results_by_topic(self, topic_name):
        # TODO: add news_search_results table to database_models.py file!!
        statement = select(
            news_search_results.c.article_uri
        ).where(
            news_search_results.c.topic == topic_name
        )

        return self.connection.execute(statement).fetchall()

    def get_article_urls_from_paper_search_results_by_topic(self, topic_name):
        # TODO: add paper_search_results table to database_models.py file!!
        statement = select(
            paper_search_results.c.article_uri
        ).where(
            paper_search_results.c.topic == topic_name
        )

        return self.connection.execute(statement).fetchall()

    def article_urls_by_topic(self, topic_name):
        statement = select(
            articles.c.uri
        ).where(
            articles.c.topic == topic_name
        )

        return self.connection.execute(statement).fetchall()

    def delete_article_matches_by_url(self, url):
        statement = delete(
            keyword_article_matches
        ).where(
            keyword_article_matches.c.article_uri == url
        )
        result = self.connection.execute(statement)
        self.connection.commit()

        return result.rowcount

    def delete_keyword_alerts_by_url(self, url):
        statement = delete(
            keyword_alerts
        ).where(
            keyword_alerts.c.article_uri == url
        )
        result = self.connection.execute(statement)
        self.connection.commit()

        return result.rowcount

    def delete_news_search_results_by_topic(self, topic_name):
        statement = delete(
            news_search_results
        ).where(
            news_search_results.c.topic == topic_name
        )
        self.connection.execute(statement)
        self.connection.commit()

    def delete_paper_search_results_by_topic(self, topic_name):
        statement = delete(
            paper_search_results
        ).where(
            paper_search_results.c.topic == topic_name
        )
        self.connection.execute(statement)
        self.connection.commit()

    def delete_article_by_url(self, url):
        statement = delete(
            articles
        ).where(
            articles.c.uri == url
        )
        result = self.connection.execute(statement)
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
        topics = self.connection.execute(statement).fetchall()

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

        return self.connection.execute(statement).fetchall()

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

        return self.connection.execute(statement).fetchall()

    def get_urls_and_topics_from_paper_search_results(self):
        statement = select(
            paper_search_results.c.article_uri,
            paper_search_results.c.topic
        ).group_by(
            paper_search_results.c.article_uri,
            paper_search_results.c.topic
        )

        return self.connection.execute(statement).fetchall()

    def check_if_articles_table_has_topic_column(self):
        statement = select(articles)
        columns = self.connection.execute(statement).mappings().fetchone().keys()

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
        
        result = self.connection.execute(statement).fetchall()

        return [row[0] for row in result]

    def delete_keyword_article_matches_from_new_table_structure_by_url(self, url):
        statement = delete(
            keyword_article_matches
        ).where(
            keyword_article_matches.c.article_uri == url
        )
        result = self.connection.execute(statement)
        self.connection.commit()

        return result.rowcount

    def delete_keyword_article_matches_from_old_table_structure_by_url(self, url):
        statement = delete(
            keyword_alerts
        ).where(
            keyword_alerts.c.article_uri == url
        )
        result = self.connection.execute(statement)
        self.connection.commit()

        return result.rowcount

    def delete_news_search_results_by_article_urls(self, placeholders, batch):
        statement = delete(
            news_search_results
        ).where(
            news_search_results.c.article_uri.in_(batch)
        )
        self.connection.execute(statement)
        self.connection.commit()

    def delete_paper_search_results_by_article_urls(self, placeholders, batch):
        statement = delete(
            paper_search_results
        ).where(
            paper_search_results.c.article_uri.in_(batch)
        )
        self.connection.execute(statement)
        self.connection.commit()

    def delete_articles_by_article_urls(self, placeholders, batch):
        statement = delete(
            articles
        ).where(
            articles.c.uri.in_(batch)
        )
        result = self.connection.execute(statement)
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

        return self.connection.execute(statement).fetchone()

    def get_request_count_for_today(self):
        statement = select(
            keyword_monitor_status.c.requests_today,
            keyword_monitor_status.c.last_reset_date
        ).where(
            keyword_monitor_status.c.id == 1
        )

        return self.connection.execute(statement).fetchone()

    def get_articles_by_url(self, url):
        statement = select(
            articles
        ).where(
            articles.c.uri == url
        )

        return self.connection.execute(statement).mappings().fetchone()

    def get_raw_articles_markdown_by_url(self, url):
        statement = select(
            raw_articles.c.raw_markdown
        ).where(
            raw_articles.c.uri == url
        )

        return self.connection.execute(statement).mappings().fetchone()

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

        podcasts = self.connection.execute(statement).fetchall()

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
        self.connection.execute(statement)
        self.connection.commit()

    def mark_podcast_generation_as_complete(self, params):
        statement = update(podcasts).where(podcasts.c.id == params[2]).values(
            status='completed',
            audio_url=params[0],
            completed_at=func.current_timestamp(),
            error=None,
            metadata=params[1]
        )
        self.connection.execute(statement)
        self.connection.commit()

    def log_error_generating_podcast(self, params):
        statement = update(podcasts).where(podcasts.c.id == params[1]).values(
            status='error',
            error=params[0],
            completed_at=func.current_timestamp()
        )
        self.connection.execute(statement)
        self.connection.commit()

    def test_data_select(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT 1")

    def get_keyword_monitor_is_enabled_and_daily_request_limit(self):
        statement = select(
            keyword_monitor_settings.c.is_enabled,
            keyword_monitor_settings.c.daily_request_limit
        ).where(
            keyword_monitor_settings.c.id == 1
        )

        return self.connection.execute(statement).fetchone()

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

        result = self.connection.execute(stmt).fetchall()

        return [(row[0], row[1], row[2].strftime("%Y-%m-%dT%H:%M:%S.000Z") if row[2] else None) for row in result]

    def get_last_check_time_using_timezone_format(self):
        statement = select(keyword_monitor_status.c.last_check_time).where(keyword_monitor_status.c.id == 1)

        result = self.connection.execute(statement).fetchone()

        return result[0].strftime("%Y-%m-%dT%H:%M:%S.000Z") if result else None

    def get_podcast_transcript(self, podcast_id):
        statement = select(
            podcasts.c.title,
            podcasts.c.transcript,
            podcasts.c.metadata
        ).where(
            podcasts.c.id == podcast_id
        )

        return self.connection.execute(statement).fetchone()

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

        return self.connection.execute(statement).fetchall()

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

        return self.connection.execute(statement).fetchone()

    def get_podcast_audio_file(self, podcast_id):
        statement = select(
            podcasts.c.audio_url
        ).where(
            podcasts.c.id == podcast_id
        )

        return self.connection.execute(statement).fetchone()

    def delete_podcast(self, podcast_id):
        statement = delete(
            podcasts
        ).where(
            podcasts.c.id == podcast_id
        )
        self.connection.execute(statement)
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

        return self.connection.execute(statement).mappings().fetchall()

    def update_article_by_url(self, params):
        statement = update(articles).where(articles.c.uri == params[6]).values(
            topic_alignment_score = params[0],
            keyword_relevance_score = params[1],
            confidence_score = params[2],
            overall_match_explanation = params[3],
            extracted_article_topics = params[4],
            extracted_article_keywords = params[5]
        )
        result = self.connection.execute(statement)
        self.connection.commit()

        return result.rowcount

    def enable_or_disable_auto_ingest(self, enabled):
        statement = update(keyword_monitor_settings).where(keyword_monitor_settings.c.id == 1).values(
            auto_ingest_enabled = enabled
        )
        self.connection.execute(statement)
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

        return self.connection.execute(statement).fetchone()

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
            .where(articles.c.auto_ingested == 1)
        )

        return self.connection.execute(stmt).fetchone()

    def stamp_keyword_monitor_status_table_with_todays_date(self, params):
        # check if the keyword_monitor_status table has a row with id 1
        statement = select(keyword_monitor_status).where(keyword_monitor_status.c.id == 1)
        result = self.connection.execute(statement).fetchone()

        if result:
            update_statement = update(keyword_monitor_status).where(keyword_monitor_status.c.id == 1).values(
                requests_today = params[0],
                last_check_time = func.current_timestamp(),
                last_reset_date = params[1]
            )
            self.connection.execute(update_statement)
            self.connection.commit()
        else:
            insert_statement = insert(keyword_monitor_status).values(
                id = 1,
                requests_today = params[0],
                last_check_time = func.current_timestamp(),
                last_reset_date = params[1]
            )
            self.connection.execute(insert_statement)
            self.connection.commit()

    def get_keyword_monitor_status_daily_request_limit(self):
        statement = select(keyword_monitor_settings.c.daily_request_limit).where(keyword_monitor_settings.c.id == 1)
        return self.connection.execute(statement).fetchone()

    #### AUTOMATED INGEST SERVICE ####

    #### MEDIA BIAS ####

    def check_if_media_bias_has_updated_at_column(self):
        return [column.name for column in mediabias.columns]

    def insert_media_bias(self, params):
        # check if the source already exists in the mediabias table
        statement = select(mediabias).where(mediabias.c.source == params[0])
        result = self.connection.execute(statement).fetchone()
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
            result = self.connection.execute(statement)
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
            result = self.connection.execute(statement)
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
        self.connection.execute(statement)
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
        self.connection.execute(statement)
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
        return self.connection.execute(statement).fetchall()

    def get_media_bias_status(self):
        statement = select(
            mediabias_settings.c.enabled,
            mediabias_settings.c.last_updated,
            mediabias_settings.c.source_file
        ).where(mediabias_settings.c.id == 1)

        return self.connection.execute(statement).fetchone()

    def get_media_bias_source(self, source_id):
        statement = select(
            mediabias.c.id
        ).where(mediabias.c.id == source_id)

        return self.connection.execute(statement).fetchone()

    def delete_media_bias_source(self, source_id):
        statement = delete(mediabias).where(mediabias.c.id == source_id)
        self.connection.execute(statement)
        self.connection.commit()

    def get_total_media_bias_sources(self):
        statement = select(
            func.count()
        ).select_from(
            mediabias
        )
        return self.connection.execute(statement).fetchone().scalar()

    def enable_media_bias_sources(self, enabled):
        statement = update(mediabias_settings).where(mediabias_settings.c.id == 1).values(
            enabled = 1 if enabled else 0,
            last_updated = func.current_timestamp()
        )
        self.connection.execute(statement)
        self.connection.commit()

    def update_media_bias_last_updated(self):
        statement = update(mediabias_settings).where(mediabias_settings.c.id == 1).values(
            last_updated = func.current_timestamp()
        )
        result = self.connection.execute(statement)
        self.connection.commit()

        return result.rowcount

    def reset_media_bias_sources(self):
        # delete all media bias data
        statement = delete(mediabias)
        self.connection.execute(statement)

        # Reset settings but keep enabled state
        statement = update(mediabias_settings).where(mediabias_settings.c.id == 1).values(
            last_updated = None,
            source_file = None
        )
        self.connection.execute(statement)
        self.connection.commit()

    def enable_media_source(self, source):
        statement = update(mediabias).where(mediabias.c.source == source).values(
            enabled = 1
        )
        self.connection.execute(statement)
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
        total_count = self.connection.execute(count_stmt).scalar()

        # Add pagination
        offset_value = (page - 1) * per_page
        paginated_stmt = (
            base_stmt
            .order_by(asc(mediabias.c.source))
            .limit(per_page)
            .offset(offset_value)
        )

        return total_count, self.connection.execute(paginated_stmt).fetchall()

    def delete_media_bias_source(self, source_id):
        statement = delete(mediabias).where(mediabias.c.id == source_id)
        self.connection.execute(statement)
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
        
        return self.connection.execute(statement).fetchone()

    def get_media_bias_filter_options(self):
        # Get unique biases
        biases_statement = select(
            mediabias.c.bias
        ).where(
            mediabias.c.bias.isnot(None),
            mediabias.c.bias != ''
        ).distinct()

        biases = [row[0] for row in self.connection.execute(biases_statement).fetchall()]

        # Get unique factual reporting levels
        factual_reporting_statement = select(
            mediabias.c.factual_reporting
        ).where(
            mediabias.c.factual_reporting.isnot(None),
            mediabias.c.factual_reporting != ''
        ).distinct()

        factual_levels = [row[0] for row in self.connection.execute(factual_reporting_statement).fetchall()]

        # Get unique countries
        countries_statement = select(
            mediabias.c.country
        ).where(
            mediabias.c.country.isnot(None),
            mediabias.c.country != ''
        ).distinct()

        countries = [row[0] for row in self.connection.execute(countries_statement).fetchall()]

        return biases, factual_levels, countries

    def load_media_bias_sources_from_database(self):
        return self.connection.execute(select(mediabias)).mappings().fetchall()
