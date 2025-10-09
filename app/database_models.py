from sqlalchemy import Boolean, CheckConstraint, Column, Enum, ForeignKey, Index, Integer, MetaData, REAL, TIMESTAMP, Table, Text, UniqueConstraint, text

metadata = MetaData()


t_analysis_versions = Table(
    'analysis_versions', metadata,
    Column('id', Integer, primary_key=True),
    Column('topic', Text, nullable=False),
    Column('version_data', Text, nullable=False),
    Column('created_at', TIMESTAMP, default=text('CURRENT_TIMESTAMP')),
    Column('model_used', Text),
    Column('analysis_depth', Text)
)

t_analysis_versions_v2 = Table(
    'analysis_versions_v2', metadata,
    Column('id', Integer, primary_key=True),
    Column('cache_key', Text, nullable=False, unique=True),
    Column('topic', Text, nullable=False),
    Column('version_data', Text, nullable=False),
    Column('cache_metadata', Text),
    Column('created_at', TIMESTAMP, default=text('CURRENT_TIMESTAMP')),
    Column('accessed_at', TIMESTAMP, default=text('CURRENT_TIMESTAMP')),
    Index('idx_accessed_at', 'accessed_at'),
    Index('idx_cache_key_created', 'cache_key', 'created_at'),
    Index('idx_topic_created', 'topic', 'created_at')
)

t_articles = Table(
    'articles', metadata,
    Column('uri', Text, primary_key=True),
    Column('title', Text),
    Column('news_source', Text),
    Column('publication_date', Text),
    Column('submission_date', Text, default=text('CURRENT_TIMESTAMP')),
    Column('summary', Text),
    Column('category', Text),
    Column('future_signal', Text),
    Column('future_signal_explanation', Text),
    Column('sentiment', Text),
    Column('sentiment_explanation', Text),
    Column('time_to_impact', Text),
    Column('time_to_impact_explanation', Text),
    Column('tags', Text),
    Column('driver_type', Text),
    Column('driver_type_explanation', Text),
    Column('topic', Text),
    Column('analyzed', Boolean, default=text('FALSE')),
    Column('bias', Text),
    Column('factual_reporting', Text),
    Column('mbfc_credibility_rating', Text),
    Column('bias_source', Text),
    Column('bias_country', Text),
    Column('press_freedom', Text),
    Column('media_type', Text),
    Column('popularity', Text),
    Column('topic_alignment_score', REAL),
    Column('keyword_relevance_score', REAL),
    Column('confidence_score', REAL),
    Column('overall_match_explanation', Text),
    Column('extracted_article_topics', Text),
    Column('extracted_article_keywords', Text),
    # Column('ingest_status', Text, default=text('"manual"')),
    Column('ingest_status', Text),
    Column('quality_score', REAL),
    Column('quality_issues', Text),
    Column('auto_ingested', Boolean, default=text('FALSE')),
    Index('idx_articles_auto_ingested', 'auto_ingested'),
    Index('idx_articles_bias', 'bias'),
    Index('idx_articles_factual_reporting', 'factual_reporting'),
    Index('idx_articles_ingest_status', 'ingest_status'),
    Index('idx_articles_quality_score', 'quality_score'),
    Index('idx_articles_uri', 'uri', unique=True)
)

t_articles_scenario_1 = Table(
    'articles_scenario_1', metadata,
    Column('uri', Text, primary_key=True),
    Column('title', Text),
    Column('news_source', Text),
    Column('publication_date', Text),
    Column('submission_date', Text, default=text('CURRENT_TIMESTAMP')),
    Column('summary', Text),
    Column('tags', Text),
    Column('topic', Text),
    Column('analyzed', Boolean, default=text('FALSE')),
    Column('topic_sentiment', Text),
    Column('topic_sentiment_explanation', Text),
    Column('sensitivity_level', Text),
    Column('sensitivity_level_explanation', Text)
)

t_building_blocks = Table(
    'building_blocks', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', Text, nullable=False, unique=True),
    Column('kind', Text, nullable=False),
    Column('prompt', Text, nullable=False),
    Column('options', Text),
    Column('created_at', Text, default=text('CURRENT_TIMESTAMP'))
)

t_feed_keyword_groups = Table(
    'feed_keyword_groups', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', Text, nullable=False),
    Column('description', Text),
    Column('color', Text, default=text("'#FF69B4'")),
    Column('is_active', Boolean, default=text('TRUE')),
    Column('created_at', TIMESTAMP, default=text('CURRENT_TIMESTAMP')),
    Column('updated_at', TIMESTAMP, default=text('CURRENT_TIMESTAMP'))
)

t_keyword_groups = Table(
    'keyword_groups', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', Text, nullable=False, unique=True),
    Column('topic', Text, nullable=False),
    Column('created_at', Text, default=text('CURRENT_TIMESTAMP')),
    Column('provider', Text, default=text("'news'")),
    Column('source', Text, nullable=False, default=text("'news'"))
)

t_keyword_monitor_settings = Table(
    'keyword_monitor_settings', metadata,
    Column('id', Integer, primary_key=True),
    Column('check_interval', Integer, nullable=False, default=text('15')),
    Column('interval_unit', Integer, nullable=False, default=text('60')),
    Column('search_fields', Text, nullable=False, default=text("'title,description,content'")),
    Column('language', Text, nullable=False, default=text("'en'")),
    Column('sort_by', Text, nullable=False, default=text("'publishedAt'")),
    Column('page_size', Integer, nullable=False, default=text('10')),
    Column('is_enabled', Boolean, nullable=False, default=True),
    Column('daily_request_limit', Integer, nullable=False, default=text('100')),
    Column('search_date_range', Integer, nullable=False, default=text('7')),
    Column('provider', Text, nullable=False, default=text("'newsapi'")),
    Column('auto_ingest_enabled', Boolean, nullable=False, default=text('FALSE')),
    Column('min_relevance_threshold', REAL, nullable=False, default=text('0.0')),
    Column('quality_control_enabled', Boolean, nullable=False, default=text('TRUE')),
    Column('auto_save_approved_only', Boolean, nullable=False, default=text('FALSE')),
    Column('default_llm_model', Text, nullable=False, default=text('"gpt-4o-mini"')),
    Column('llm_temperature', REAL, nullable=False, default=text('0.1')),
    Column('llm_max_tokens', Integer, nullable=False, default=text('1000'))
)

t_keyword_monitor_status = Table(
    'keyword_monitor_status', metadata,
    Column('id', Integer, primary_key=True),
    Column('last_check_time', Text),
    Column('last_error', Text),
    # TODO: Should this default text of 0? or 0? REVIEW ALL DEFAULT VALUES!!!
    Column('requests_today', Integer, default=text('0')),
    Column('last_reset_date', Text)
)

t_mediabias = Table(
    'mediabias', metadata,
    Column('source', Text, primary_key=True),
    Column('country', Text),
    Column('bias', Text),
    Column('factual_reporting', Text),
    Column('press_freedom', Text),
    Column('media_type', Text),
    Column('popularity', Text),
    Column('mbfc_credibility_rating', Text),
    Column('enabled', Boolean, default=text('FALSE')),
    Column('last_updated', Text, default=text('CURRENT_TIMESTAMP')),
    Column('updated_at', TIMESTAMP, default=text('CURRENT_TIMESTAMP')),
    Index('idx_mediabias_source', 'source')
)

t_mediabias_settings = Table(
    'mediabias_settings', metadata,
    Column('id', Integer, primary_key=True),
    Column('enabled', Boolean, default=text('0')),
    Column('last_updated', TIMESTAMP),
    Column('source_file', Text),
    CheckConstraint('id = 1')
)

t_migrations = Table(
    'migrations', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', Text, unique=True),
    Column('applied_at', Text, default=text('CURRENT_TIMESTAMP'))
)

t_model_bias_arena_runs = Table(
    'model_bias_arena_runs', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', Text, nullable=False),
    Column('description', Text),
    Column('benchmark_model', Text, nullable=False),
    Column('selected_models', Text, nullable=False),
    Column('article_count', Integer, nullable=False, default=text('25')),
    Column('created_at', TIMESTAMP, default=text('CURRENT_TIMESTAMP')),
    Column('completed_at', TIMESTAMP),
    Column('status', Text, default=text("'running'")),
    Column('rounds', Integer, default=text('1')),
    Column('current_round', Integer, default=text('1')),
    Index('idx_bias_arena_runs_rounds', 'rounds', 'current_round'),
    Index('idx_bias_arena_runs_status', 'status')
)

t_newsletter_prompts = Table(
    'newsletter_prompts', metadata,
    Column('content_type_id', Text, primary_key=True),
    Column('prompt_template', Text, nullable=False),
    Column('description', Text, nullable=False),
    Column('last_updated', Text, default=text('CURRENT_TIMESTAMP'))
)

t_oauth_allowlist = Table(
    'oauth_allowlist', metadata,
    Column('id', Integer, primary_key=True),
    Column('email', Text, nullable=False, unique=True),
    Column('added_by', Text),
    Column('added_at', TIMESTAMP, default=text('CURRENT_TIMESTAMP')),
    Column('is_active', Boolean, default=text('TRUE'))
)

t_oauth_users = Table(
    'oauth_users', metadata,
    Column('id', Integer, primary_key=True),
    Column('email', Text, nullable=False),
    Column('name', Text),
    Column('provider', Text, nullable=False),
    Column('provider_id', Text),
    Column('avatar_url', Text),
    Column('created_at', TIMESTAMP, default=text('CURRENT_TIMESTAMP')),
    Column('last_login', TIMESTAMP, default=text('CURRENT_TIMESTAMP')),
    Column('is_active', Boolean, default=text('TRUE')),
    UniqueConstraint('email', 'provider'),
    Index('idx_oauth_users_active', 'is_active'),
    Index('idx_oauth_users_email_provider', 'email', 'provider'),
    Index('idx_oauth_users_provider', 'provider')
)

t_organizational_profiles = Table(
    'organizational_profiles', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', Text, nullable=False, unique=True),
    Column('description', Text),
    Column('industry', Text),
    Column('organization_type', Text),
    Column('key_concerns', Text),
    Column('strategic_priorities', Text),
    Column('risk_tolerance', Text),
    Column('innovation_appetite', Text),
    Column('decision_making_style', Text),
    Column('stakeholder_focus', Text),
    Column('competitive_landscape', Text),
    Column('regulatory_environment', Text),
    Column('custom_context', Text),
    Column('created_at', TIMESTAMP, default=text('CURRENT_TIMESTAMP')),
    Column('updated_at', TIMESTAMP, default=text('CURRENT_TIMESTAMP')),
    Column('is_default', Boolean, default=text('FALSE')),
    Column('region', Text),
    Index('idx_org_profiles_default', 'is_default'),
    Index('idx_org_profiles_industry', 'industry'),
    Index('idx_org_profiles_name', 'name')
)

t_podcasts = Table(
    'podcasts', metadata,
    Column('id', Text, primary_key=True),
    Column('title', Text),
    Column('status', Text, default=text("'processing'")),
    Column('audio_url', Text),
    Column('created_at', TIMESTAMP, default=text('CURRENT_TIMESTAMP')),
    Column('completed_at', TIMESTAMP),
    Column('error', Text),
    Column('transcript', Text),
    Column('metadata', Text)
)

t_scenarios = Table(
    'scenarios', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', Text, nullable=False, unique=True),
    Column('topic', Text, nullable=False),
    Column('article_table', Text, unique=True),
    Column('created_at', Text, default=text('CURRENT_TIMESTAMP'))
)

t_settings_podcasts = Table(
    'settings_podcasts', metadata,
    Column('key', Text, primary_key=True),
    Column('value', Text)
)

t_trend_consistency_metrics = Table(
    'trend_consistency_metrics', metadata,
    Column('id', Integer, primary_key=True),
    Column('topic', Text, nullable=False),
    Column('consistency_score', REAL, nullable=False),
    Column('comparison_count', Integer),
    Column('detailed_metrics', Text),
    Column('analysis_date', TIMESTAMP, default=text('CURRENT_TIMESTAMP')),
    Index('idx_consistency_topic_date', 'topic', 'analysis_date')
)

t_users = Table(
    'users', metadata,
    Column('username', Text, primary_key=True),
    Column('password_hash', Text, nullable=False),
    Column('force_password_change', Boolean, default=text('0')),
    Column('completed_onboarding', Boolean, default=text('0'))
)

t_article_annotations = Table(
    'article_annotations', metadata,
    Column('id', Integer, primary_key=True),
    Column('article_uri', ForeignKey('articles.uri', ondelete='CASCADE'), nullable=False),
    Column('author', Text, nullable=False),
    Column('content', Text, nullable=False),
    Column('is_private', Boolean, default=text('FALSE')),
    Column('created_at', TIMESTAMP, default=text('CURRENT_TIMESTAMP')),
    Column('updated_at', TIMESTAMP, default=text('CURRENT_TIMESTAMP'))
)

t_auspex_chats = Table(
    'auspex_chats', metadata,
    Column('id', Integer, primary_key=True),
    Column('topic', Text, nullable=False),
    Column('title', Text),
    Column('created_at', TIMESTAMP, default=text('CURRENT_TIMESTAMP')),
    Column('updated_at', TIMESTAMP, default=text('CURRENT_TIMESTAMP')),
    Column('user_id', ForeignKey('users.username', ondelete='SET NULL')),
    Column('metadata', Text),
    Index('idx_auspex_chats_topic', 'topic'),
    Index('idx_auspex_chats_user_id', 'user_id')
)

t_auspex_prompts = Table(
    'auspex_prompts', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', Text, nullable=False, unique=True),
    Column('title', Text, nullable=False),
    Column('content', Text, nullable=False),
    Column('description', Text),
    Column('is_default', Boolean, default=text('0')),
    Column('created_at', TIMESTAMP, default=text('CURRENT_TIMESTAMP')),
    Column('updated_at', TIMESTAMP, default=text('CURRENT_TIMESTAMP')),
    Column('user_created', ForeignKey('users.username', ondelete='SET NULL')),
    Index('idx_auspex_prompts_is_default', 'is_default'),
    Index('idx_auspex_prompts_name', 'name')
)

t_feed_group_sources = Table(
    'feed_group_sources', metadata,
    Column('id', Integer, primary_key=True),
    Column('group_id', ForeignKey('feed_keyword_groups.id', ondelete='CASCADE'), nullable=False),
    # Column('source_type', Enum('bluesky', 'arxiv', 'thenewsapi'), nullable=False),
    Column('source_type', Text, nullable=False),
    Column('keywords', Text, nullable=False),
    Column('enabled', Boolean, default=text('TRUE')),
    Column('last_checked', TIMESTAMP),
    Column('created_at', TIMESTAMP, default=text('CURRENT_TIMESTAMP')),
    Column('date_range_days', Integer, default=text('7')),
    Column('custom_start_date', Text, default=text('NULL')),
    Column('custom_end_date', Text, default=text('NULL')),
    Column('search_settings', Text, default=text("'{}'"))
)

t_feed_items = Table(
    'feed_items', metadata,
    Column('id', Integer, primary_key=True),
    # Column('source_type', Enum('bluesky', 'arxiv', 'thenewsapi'), nullable=False),
    Column('source_type', Text, nullable=False),
    Column('source_id', Text, nullable=False),
    Column('group_id', ForeignKey('feed_keyword_groups.id', ondelete='CASCADE'), nullable=False),
    Column('title', Text, nullable=False),
    Column('content', Text),
    Column('author', Text),
    Column('author_handle', Text),
    Column('url', Text, nullable=False),
    Column('publication_date', TIMESTAMP),
    Column('engagement_metrics', Text),
    Column('tags', Text),
    Column('mentions', Text),
    Column('images', Text),
    Column('is_hidden', Boolean, default=text('FALSE')),
    Column('is_starred', Boolean, default=text('FALSE')),
    Column('created_at', TIMESTAMP, default=text('CURRENT_TIMESTAMP')),
    UniqueConstraint('source_type', 'source_id', 'group_id'),
    Index('idx_feed_items_group_id', 'group_id'),
    Index('idx_feed_items_is_hidden', 'is_hidden'),
    Index('idx_feed_items_is_starred', 'is_starred'),
    Index('idx_feed_items_publication_date', 'publication_date'),
    Index('idx_feed_items_source_type', 'source_type')
)

t_keyword_article_matches = Table(
    'keyword_article_matches', metadata,
    Column('id', Integer, primary_key=True),
    Column('article_uri', ForeignKey('articles.uri', ondelete='CASCADE'), nullable=False),
    Column('keyword_ids', Text, nullable=False),
    Column('group_id', ForeignKey('keyword_groups.id', ondelete='CASCADE'), nullable=False),
    Column('detected_at', Text, default=text('CURRENT_TIMESTAMP')),
    Column('is_read', Integer, default=text('0')),
    UniqueConstraint('article_uri', 'group_id')
)

t_model_bias_arena_articles = Table(
    'model_bias_arena_articles', metadata,
    Column('id', Integer, primary_key=True),
    Column('run_id', ForeignKey('model_bias_arena_runs.id', ondelete='CASCADE'), nullable=False),
    Column('article_uri', ForeignKey('articles.uri', ondelete='CASCADE'), nullable=False),
    Column('article_title', Text),
    Column('article_summary', Text),
    Column('selected_for_benchmark', Boolean, default=text('FALSE')),
    Column('created_at', TIMESTAMP, default=text('CURRENT_TIMESTAMP')),
    UniqueConstraint('run_id', 'article_uri'),
    Index('idx_bias_arena_articles_run_id', 'run_id')
)

t_model_bias_arena_results = Table(
    'model_bias_arena_results', metadata,
    Column('id', Integer, primary_key=True),
    Column('run_id', ForeignKey('model_bias_arena_runs.id', ondelete='CASCADE'), nullable=False),
    Column('article_uri', ForeignKey('articles.uri', ondelete='CASCADE'), nullable=False),
    Column('model_name', Text, nullable=False),
    Column('response_text', Text),
    Column('bias_score', REAL),
    Column('confidence_score', REAL),
    Column('response_time_ms', Integer),
    Column('error_message', Text),
    Column('created_at', TIMESTAMP, default=text('CURRENT_TIMESTAMP')),
    Column('sentiment_explanation', Text),
    Column('future_signal_explanation', Text),
    Column('time_to_impact_explanation', Text),
    Column('driver_type_explanation', Text),
    Column('category_explanation', Text),
    Column('sentiment', Text),
    Column('future_signal', Text),
    Column('time_to_impact', Text),
    Column('driver_type', Text),
    Column('category', Text),
    Column('political_bias', Text),
    Column('political_bias_explanation', Text),
    Column('factuality', Text),
    Column('factuality_explanation', Text),
    Column('round_number', Integer, default=text('1')),
    Index('idx_bias_arena_results_factuality', 'factuality'),
    Index('idx_bias_arena_results_model', 'model_name'),
    Index('idx_bias_arena_results_political_bias', 'political_bias'),
    Index('idx_bias_arena_results_round', 'run_id', 'round_number'),
    Index('idx_bias_arena_results_run_id', 'run_id')
)

t_monitored_keywords = Table(
    'monitored_keywords', metadata,
    Column('id', Integer, primary_key=True),
    Column('group_id', ForeignKey('keyword_groups.id', ondelete='CASCADE'), nullable=False),
    Column('keyword', Text, nullable=False),
    Column('created_at', Text, default=text('CURRENT_TIMESTAMP')),
    Column('last_checked', Text),
    UniqueConstraint('group_id', 'keyword')
)

t_oauth_sessions = Table(
    'oauth_sessions', metadata,
    Column('id', Integer, primary_key=True),
    Column('user_id', ForeignKey('oauth_users.id')),
    Column('session_token', Text, unique=True),
    Column('provider', Text),
    Column('created_at', TIMESTAMP, default=text('CURRENT_TIMESTAMP')),
    Column('expires_at', TIMESTAMP),
    Column('last_accessed', TIMESTAMP, default=text('CURRENT_TIMESTAMP'))
)

t_raw_articles = Table(
    'raw_articles', metadata,
    Column('uri', ForeignKey('articles.uri', ondelete='CASCADE'), primary_key=True),
    Column('raw_markdown', Text),
    Column('submission_date', Text, default=text('CURRENT_TIMESTAMP')),
    Column('last_updated', Text),
    Column('topic', Text)
)

t_scenario_blocks = Table(
    'scenario_blocks', metadata,
    Column('scenario_id', ForeignKey('scenarios.id', ondelete='CASCADE'), primary_key=True),
    Column('building_block_id', ForeignKey('building_blocks.id', ondelete='CASCADE'), primary_key=True)
)

t_user_feed_subscriptions = Table(
    'user_feed_subscriptions', metadata,
    Column('id', Integer, primary_key=True),
    Column('user_id', Integer, default=text('1')),
    Column('group_id', ForeignKey('feed_keyword_groups.id', ondelete='CASCADE'), nullable=False),
    Column('notification_enabled', Boolean, default=text('TRUE')),
    Column('created_at', TIMESTAMP, default=text('CURRENT_TIMESTAMP')),
    Index('idx_user_feed_subscriptions_group_id', 'group_id')
)

t_auspex_messages = Table(
    'auspex_messages', metadata,
    Column('id', Integer, primary_key=True),
    Column('chat_id', ForeignKey('auspex_chats.id', ondelete='CASCADE'), nullable=False),
    # Column('role', Enum('user', 'assistant', 'system'), nullable=False),
    Column('role', Text, nullable=False),
    Column('content', Text, nullable=False),
    Column('timestamp', TIMESTAMP, default=text('CURRENT_TIMESTAMP')),
    Column('model_used', Text),
    Column('tokens_used', Integer),
    Column('metadata', Text),
    Index('idx_auspex_messages_chat_id', 'chat_id'),
    Index('idx_auspex_messages_role', 'role')
)

t_keyword_alerts = Table(
    'keyword_alerts', metadata,
    Column('id', Integer, primary_key=True),
    Column('keyword_id', ForeignKey('monitored_keywords.id', ondelete='CASCADE'), nullable=False),
    Column('article_uri', ForeignKey('articles.uri', ondelete='CASCADE'), nullable=False),
    Column('detected_at', Text, default=text('CURRENT_TIMESTAMP')),
    Column('is_read', Integer, default=text('0')),
    UniqueConstraint('keyword_id', 'article_uri')
)
