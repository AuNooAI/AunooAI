from sqlalchemy import Boolean, CheckConstraint, Column, Date, DateTime, Enum, Float, ForeignKey, Index, Integer, JSON, MetaData, REAL, String, TIMESTAMP, Table, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

metadata = MetaData()


t_consensus_analysis_runs = Table(
    'consensus_analysis_runs', metadata,
    Column('id', String(36), primary_key=True),
    Column('user_id', Integer),
    Column('topic', Text, nullable=False),
    Column('timeframe', String(100)),
    Column('selected_categories', JSON),
    Column('raw_output', JSON, nullable=False),
    Column('article_list', JSON),
    Column('total_articles_analyzed', Integer),
    Column('created_at', DateTime, server_default=text('CURRENT_TIMESTAMP'), nullable=False),
    Column('analysis_duration_seconds', Float),
    Index('idx_consensus_analysis_user_created', 'user_id', 'created_at')
)

t_market_signals_runs = Table(
    'market_signals_runs', metadata,
    Column('id', String(36), primary_key=True),
    Column('user_id', Integer),
    Column('topic', Text, nullable=False),
    Column('model_used', String(100)),
    Column('raw_output', JSON, nullable=False),
    Column('total_articles_analyzed', Integer),
    Column('created_at', DateTime, server_default=text('CURRENT_TIMESTAMP'), nullable=False),
    Column('analysis_duration_seconds', Float),
    Index('idx_market_signals_user_created', 'user_id', 'created_at')
)

t_impact_timeline_runs = Table(
    'impact_timeline_runs', metadata,
    Column('id', String(36), primary_key=True),
    Column('user_id', Integer),
    Column('topic', Text, nullable=False),
    Column('model_used', String(100)),
    Column('raw_output', JSON, nullable=False),
    Column('total_articles_analyzed', Integer),
    Column('created_at', DateTime, server_default=text('CURRENT_TIMESTAMP'), nullable=False),
    Column('analysis_duration_seconds', Float),
    Index('idx_impact_timeline_user_created', 'user_id', 'created_at')
)

t_strategic_recommendations_runs = Table(
    'strategic_recommendations_runs', metadata,
    Column('id', String(36), primary_key=True),
    Column('user_id', Integer),
    Column('topic', Text, nullable=False),
    Column('model_used', String(100)),
    Column('raw_output', JSON, nullable=False),
    Column('total_articles_analyzed', Integer),
    Column('created_at', DateTime, server_default=text('CURRENT_TIMESTAMP'), nullable=False),
    Column('analysis_duration_seconds', Float),
    Index('idx_strategic_recs_user_created', 'user_id', 'created_at')
)

t_future_horizons_runs = Table(
    'future_horizons_runs', metadata,
    Column('id', String(36), primary_key=True),
    Column('user_id', Integer),
    Column('topic', Text, nullable=False),
    Column('model_used', String(100)),
    Column('raw_output', JSON, nullable=False),
    Column('total_articles_analyzed', Integer),
    Column('created_at', DateTime, server_default=text('CURRENT_TIMESTAMP'), nullable=False),
    Column('analysis_duration_seconds', Float),
    Index('idx_future_horizons_user_created', 'user_id', 'created_at')
)

t_saved_dashboards = Table(
    'saved_dashboards', metadata,
    Column('id', Integer, primary_key=True),
    Column('topic', String(255), nullable=False),
    Column('username', Text, ForeignKey('users.username', ondelete='SET NULL')),
    Column('name', String(255), nullable=False),
    Column('description', Text),
    Column('config', JSONB, nullable=False),
    Column('article_uris', ARRAY(Text), nullable=False),
    Column('consensus_data', JSONB),
    Column('strategic_data', JSONB),
    Column('timeline_data', JSONB),
    Column('signals_data', JSONB),
    Column('horizons_data', JSONB),
    Column('created_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    Column('updated_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    Column('last_accessed_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    Column('profile_snapshot', JSONB),
    Column('articles_analyzed', Integer),
    Column('model_used', String(100)),
    Column('auto_generated', Boolean, server_default=text('false'), nullable=False),
    UniqueConstraint('topic', 'username', 'name', name='uq_saved_dashboards_topic_user_name'),
    Index('idx_saved_dashboards_topic', 'topic'),
    Index('idx_saved_dashboards_user', 'username'),
    Index('idx_saved_dashboards_created', 'created_at')
)

t_saved_newsletters = Table(
    'saved_newsletters', metadata,
    Column('id', Integer, primary_key=True),
    Column('topic', String(255), nullable=False),
    Column('username', Text, ForeignKey('users.username', ondelete='SET NULL')),
    Column('name', String(255), nullable=False),
    Column('description', Text),
    Column('config', JSONB),
    Column('days_back', Integer),
    Column('deep_dive_topic', String(255)),
    Column('newsletter_content', Text, nullable=False),
    Column('deep_dive_analysis', Text),
    Column('articles_used', Integer),
    Column('article_uris', ARRAY(Text)),
    Column('model_used', String(100)),
    Column('created_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    Column('updated_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    UniqueConstraint('topic', 'username', 'name', name='uq_saved_newsletters_topic_user_name'),
    Index('idx_saved_newsletters_topic', 'topic'),
    Index('idx_saved_newsletters_user', 'username'),
    Index('idx_saved_newsletters_created', 'created_at')
)

t_saved_eos = Table(
    'saved_eos', metadata,
    Column('id', Integer, primary_key=True),
    Column('topic', String(255), nullable=False),
    Column('username', Text, ForeignKey('users.username', ondelete='SET NULL')),
    Column('name', String(255), nullable=False),
    Column('description', Text),
    Column('config', JSONB),
    Column('scenarios', JSONB, nullable=False),
    Column('metadata', JSONB),
    Column('articles_used', Integer),
    Column('article_uris', ARRAY(Text)),
    Column('model_used', String(100)),
    Column('time_horizon', String(50)),
    Column('scenario_count', Integer),
    Column('created_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    Column('updated_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    UniqueConstraint('topic', 'username', 'name', name='uq_saved_eos_topic_user_name'),
    Index('idx_saved_eos_topic', 'topic'),
    Index('idx_saved_eos_user', 'username'),
    Index('idx_saved_eos_created', 'created_at')
)

t_saved_focus_groups = Table(
    'saved_focus_groups', metadata,
    Column('id', Integer, primary_key=True),
    Column('topic', String(255), nullable=False),
    Column('username', Text, ForeignKey('users.username', ondelete='SET NULL')),
    Column('name', String(255), nullable=False),
    Column('description', Text),
    Column('config', JSONB),
    Column('personas', JSONB, nullable=False),
    Column('focus_group_summary', Text),
    Column('interaction_dynamics', JSONB),
    Column('metadata', JSONB),
    Column('articles_used', Integer),
    Column('article_uris', ARRAY(Text)),
    Column('model_used', String(100)),
    Column('persona_count', Integer),
    Column('created_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    Column('updated_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    UniqueConstraint('topic', 'username', 'name', name='uq_saved_focus_groups_topic_user_name'),
    Index('idx_saved_focus_groups_topic', 'topic'),
    Index('idx_saved_focus_groups_user', 'username'),
    Index('idx_saved_focus_groups_created', 'created_at')
)

t_saved_executive_briefings = Table(
    'saved_executive_briefings', metadata,
    Column('id', Integer, primary_key=True),
    Column('topic', String(255), nullable=False),
    Column('username', Text, ForeignKey('users.username', ondelete='SET NULL')),
    Column('name', String(255), nullable=False),
    Column('description', Text),
    Column('persona', String(50), nullable=False),  # CEO/CMO/CTO/CISO/Custom
    Column('article_count', Integer, nullable=False),
    Column('config', JSONB),  # Generation config (custom persona settings)
    Column('articles', JSONB, nullable=False),  # Array of analyzed articles
    Column('briefing_summary', Text),  # Synthesis narrative
    Column('themes', JSONB),  # Cross-article themes
    Column('priority_actions', JSONB),  # Recommended actions
    Column('metadata', JSONB),  # Generation stats
    Column('articles_used', Integer),
    Column('article_uris', ARRAY(Text)),
    Column('model_used', String(100)),
    Column('created_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    Column('updated_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    UniqueConstraint('topic', 'username', 'name', name='uq_saved_exec_briefings_topic_user_name'),
    Index('idx_saved_exec_briefings_topic', 'topic'),
    Index('idx_saved_exec_briefings_user', 'username'),
    Index('idx_saved_exec_briefings_persona', 'persona'),
    Index('idx_saved_exec_briefings_created', 'created_at')
)

# Desk briefings - user-curated briefings with articles and incidents
t_desk_briefings = Table(
    'desk_briefings', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String(255), nullable=False),
    Column('description', Text),
    Column('topic', String(255)),  # Optional - briefings can be cross-topic
    Column('username', Text, ForeignKey('users.username', ondelete='SET NULL')),
    Column('articles', JSONB, nullable=False, server_default=text("'[]'")),  # Array of curated articles
    Column('incidents', JSONB, nullable=False, server_default=text("'[]'")),  # Array of curated incidents
    Column('emerging_topics', JSONB, nullable=False, server_default=text("'[]'")),  # Array of emerging topics
    Column('synthesis', Text),  # AI-generated synthesis narrative
    Column('themes', JSONB),  # AI-generated themes
    Column('priority_actions', JSONB),  # AI-generated actions
    Column('metadata', JSONB),  # Generation metadata
    Column('status', String(50), nullable=False, server_default=text("'draft'")),  # draft, finalized
    Column('model_used', String(100)),
    Column('articles_count', Integer, server_default=text('0'), nullable=False),
    Column('incidents_count', Integer, server_default=text('0'), nullable=False),
    Column('emerging_topics_count', Integer, server_default=text('0'), nullable=False),
    Column('created_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    Column('updated_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    Column('finalized_at', DateTime(timezone=True)),
    UniqueConstraint('name', 'username', name='uq_desk_briefings_name_user'),
    Index('idx_desk_briefings_username', 'username'),
    Index('idx_desk_briefings_status', 'status'),
    Index('idx_desk_briefings_created_at', 'created_at')
)

# Newsfeed dashboard snapshots - stores auto-generated dashboard state
t_newsfeed_dashboard_snapshots = Table(
    'newsfeed_dashboard_snapshots', metadata,
    Column('id', Integer, primary_key=True),
    Column('topic', String(255), nullable=True),  # NULL = all topics
    Column('generated_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    Column('persona', String(100), nullable=False, server_default=text("'CEO'")),
    Column('model', String(100), nullable=False, server_default=text("'gpt-5.4-mini'")),
    Column('briefing_articles', JSONB, nullable=True),
    Column('briefing_generated', Boolean, server_default=text('false'), nullable=False),
    Column('highlights_data', JSONB, nullable=True),
    Column('highlights_generated', Boolean, server_default=text('false'), nullable=False),
    Column('narratives_data', JSONB, nullable=True),
    Column('narratives_generated', Boolean, server_default=text('false'), nullable=False),
    Column('articles_analyzed', Integer, nullable=True),
    Column('generation_duration_seconds', Float, nullable=True),
    Column('error_message', Text, nullable=True),
    Index('idx_nf_snapshots_topic', 'topic'),
    Index('idx_nf_snapshots_generated', 'generated_at'),
)

t_saved_signal_reports = Table(
    'saved_signal_reports', metadata,
    Column('id', Integer, primary_key=True),
    Column('instruction_id', Integer, ForeignKey('signal_instructions.id', ondelete='SET NULL')),
    Column('instruction_name', Text, nullable=False),
    Column('topic', Text),
    Column('username', Text, ForeignKey('users.username', ondelete='SET NULL')),
    Column('name', String(255), nullable=False),
    Column('description', Text),
    Column('report_prompt', Text),
    Column('report_content', Text),
    Column('alerts_data', JSONB),  # Signal alerts that triggered this
    Column('article_uris', ARRAY(Text)),
    Column('articles_used', Integer),
    Column('config', JSONB),  # Generation config (model, etc.)
    Column('model_used', String(100)),
    Column('created_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    UniqueConstraint('topic', 'username', 'name', name='uq_saved_signal_reports_topic_user_name'),
    Index('idx_saved_signal_reports_topic', 'topic'),
    Index('idx_saved_signal_reports_user', 'username'),
    Index('idx_saved_signal_reports_instruction', 'instruction_id'),
    Index('idx_saved_signal_reports_created', 'created_at')
)

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

t_analysis_run_logs = Table(
    'analysis_run_logs', metadata,
    Column('id', Integer, primary_key=True),
    Column('run_id', Text, nullable=False, unique=True),
    Column('analysis_type', Text, nullable=False),
    Column('topic', Text, nullable=False),
    Column('model_used', Text),
    Column('sample_size', Integer),
    Column('articles_analyzed', Integer),
    Column('timeframe_days', Integer),
    Column('consistency_mode', Text),
    Column('profile_id', Integer),
    Column('persona', Text),
    Column('customer_type', Text),
    Column('cache_key', Text),
    Column('cache_hit', Boolean, default=False),
    Column('started_at', TIMESTAMP, default=text('CURRENT_TIMESTAMP')),
    Column('completed_at', TIMESTAMP),
    Column('status', Text, default=text("'running'")),
    Column('error_message', Text),
    Column('metadata', Text),
    Index('idx_analysis_run_logs_type', 'analysis_type'),
    Index('idx_analysis_run_logs_topic', 'topic'),
    Index('idx_analysis_run_logs_started', 'started_at'),
    Index('idx_analysis_run_logs_run_id', 'run_id')
)

t_analysis_run_articles = Table(
    'analysis_run_articles', metadata,
    Column('id', Integer, primary_key=True),
    Column('run_id', Text, nullable=False),
    Column('article_uri', Text, nullable=False),
    Column('article_title', Text),
    Column('article_source', Text),
    Column('published_date', TIMESTAMP),
    Column('sentiment', Text),
    Column('relevance_score', REAL),
    Column('included_in_prompt', Boolean, default=True),
    Column('article_position', Integer),
    Column('created_at', TIMESTAMP, default=text('CURRENT_TIMESTAMP')),
    Index('idx_analysis_run_articles_run_id', 'run_id'),
    Index('idx_analysis_run_articles_uri', 'article_uri'),
    Index('idx_analysis_run_articles_created', 'created_at')
)

t_article_analysis_cache = Table(
    'article_analysis_cache', metadata,
    Column('id', Integer, primary_key=True),
    Column('article_uri', Text, nullable=False),
    Column('analysis_type', Text, nullable=False),
    Column('content', Text, nullable=False),
    Column('model_used', Text, nullable=False),
    Column('generated_at', TIMESTAMP, default=text('CURRENT_TIMESTAMP')),
    Column('expires_at', TIMESTAMP),
    Column('metadata', Text),
    UniqueConstraint('article_uri', 'analysis_type', 'model_used'),
    Index('idx_article_analysis_cache_uri', 'article_uri'),
    Index('idx_article_analysis_cache_type', 'analysis_type'),
    Index('idx_article_analysis_cache_expires', 'expires_at')
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
    Column('user_preference', Text),  # 'more', 'less', or null
    Column('preference_date', DateTime),  # when preference was set
    Column('article_origin', Text, server_default=text("'unknown'")),  # 'aunoo', 'external', 'unknown'
    Column('opoint_entities', JSONB),  # Opoint per-article entity/topic enrichment (brand/competitor signal)
    Column('social_meta', JSONB),  # Social post media + engagement (thumbnail, likes/reposts/comments/plays) for xpoz posts
    Index('idx_articles_auto_ingested', 'auto_ingested'),
    Index('idx_articles_article_origin', 'article_origin'),
    Index('idx_articles_bias', 'bias'),
    Index('idx_articles_factual_reporting', 'factual_reporting'),
    Index('idx_articles_ingest_status', 'ingest_status'),
    Index('idx_articles_quality_score', 'quality_score'),
    Index('idx_articles_uri', 'uri', unique=True),
    Index('idx_articles_user_preference', 'user_preference'),
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
    Column('source', Text, nullable=False, default=text("'news'")),
    # Per-group collection settings (NULL = use global)
    Column('is_active', Boolean, default=True),
    Column('check_interval', Integer, nullable=True),
    Column('interval_unit', Integer, nullable=True),  # 60=minutes, 3600=hours, 86400=days
    Column('search_date_range', Integer, nullable=True),
    Column('providers', Text, nullable=True),  # JSON array e.g., '["thenewsapi", "arxiv"]'
    Column('social_platforms', Text, nullable=True),  # JSON array of xpoz platforms; NULL = XPOZ_PLATFORMS env default
    # Processing settings
    Column('auto_ingest_enabled', Boolean, nullable=True),
    Column('min_relevance_threshold', REAL, nullable=True),
    Column('quality_control_enabled', Boolean, nullable=True),
    Column('auto_save_approved_only', Boolean, nullable=True),
    # AI settings
    Column('default_llm_model', Text, nullable=True),
    Column('llm_temperature', REAL, nullable=True),
    Column('llm_max_tokens', Integer, nullable=True),
    # Scheduling state
    Column('last_checked_at', TIMESTAMP(timezone=True), nullable=True),
    Column('next_check_at', TIMESTAMP(timezone=True), nullable=True),
    Column('last_error', Text, nullable=True),
    Column('updated_at', TIMESTAMP(timezone=True), default=text('NOW()')),
    # Index for efficient due-group queries
    Index('idx_keyword_groups_next_check', 'is_active', 'next_check_at')
)

t_keyword_monitor_settings = Table(
    'keyword_monitor_settings', metadata,
    Column('id', Integer, primary_key=True),
    Column('check_interval', Integer, nullable=False, default=text('24')),  # 24 hours default
    Column('interval_unit', Integer, nullable=False, default=text('3600')),  # Hours (3600 seconds)
    Column('search_fields', Text, nullable=False, default=text("'title,description,content'")),
    Column('language', Text, nullable=False, default=text("'en'")),
    Column('sort_by', Text, nullable=False, default=text("'publishedAt'")),
    Column('page_size', Integer, nullable=False, default=text('10')),
    Column('is_enabled', Boolean, nullable=False, default=True),
    Column('daily_request_limit', Integer, nullable=False, default=text('100')),
    Column('search_date_range', Integer, nullable=False, default=text('7')),
    Column('provider', Text, nullable=False, default=text("'thenewsapi'")),
    Column('providers', Text, nullable=True, default=text("'[\"thenewsapi\"]'")),  # JSON array for multi-collector support
    Column('auto_ingest_enabled', Boolean, nullable=False, default=text('TRUE')),  # Auto-processing ON by default
    Column('min_relevance_threshold', REAL, nullable=False, default=text('0.0')),
    Column('quality_control_enabled', Boolean, nullable=False, default=text('TRUE')),
    Column('auto_save_approved_only', Boolean, nullable=False, default=text('TRUE')),  # Save Approved Only ON by default
    Column('default_llm_model', Text, nullable=True, default=None),  # NULL = use first available model
    Column('llm_temperature', REAL, nullable=False, default=text('0.2')),  # Temperature 0.2 default
    Column('llm_max_tokens', Integer, nullable=False, default=text('1000')),
    Column('auto_regenerate_reports', Boolean, nullable=True, default=True),  # Auto-regenerate ON by default
    Column('inference_mode', Text, nullable=False, default=text("'hybrid'")),  # 'local', 'hybrid', or 'external'
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
    Column('monitored_brands', Text),  # JSON array of brand names to track in PAM analysis
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
    Column('email', Text, unique=True, nullable=False),  # Added 2025-10-21
    Column('role', Text, default='user', nullable=False),  # Added 2025-10-21
    Column('is_active', Boolean, default=True, nullable=False),  # Added 2025-10-21
    Column('force_password_change', Boolean, default=text('FALSE')),
    Column('completed_onboarding', Boolean, default=text('FALSE')),
    Column('created_at', TIMESTAMP, server_default=text('CURRENT_TIMESTAMP')),  # Added 2025-10-21
    Index('idx_users_email', 'email'),
    Index('idx_users_is_active', 'is_active'),
    Index('idx_users_role', 'role'),
    CheckConstraint("role IN ('admin', 'user')", name='check_user_role'),
    UniqueConstraint('email', name='uq_users_email')
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
    Column('profile_id', ForeignKey('organizational_profiles.id', ondelete='SET NULL')),
    Index('idx_auspex_chats_topic', 'topic'),
    Index('idx_auspex_chats_user_id', 'user_id'),
    Index('idx_auspex_chats_profile_id', 'profile_id'),
    Index('idx_auspex_chats_user_profile', 'user_id', 'profile_id')
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

t_dashboard_cache = Table(
    'dashboard_cache', metadata,
    Column('id', Integer, primary_key=True),
    Column('cache_key', Text, nullable=False, unique=True),
    Column('dashboard_type', Text, nullable=False),
    Column('date_range', Text, nullable=False),
    Column('topic', Text),
    Column('profile_id', ForeignKey('organizational_profiles.id', ondelete='SET NULL')),
    Column('persona', Text),
    Column('content_json', Text, nullable=False),
    Column('summary_text', Text),
    Column('article_count', Integer, default=text('0')),
    Column('model_used', Text),
    Column('generation_time_seconds', Float),
    Column('generated_at', TIMESTAMP, nullable=False, default=text('CURRENT_TIMESTAMP')),
    Column('accessed_at', TIMESTAMP, default=text('CURRENT_TIMESTAMP')),
    Index('idx_dashboard_cache_type', 'dashboard_type', 'generated_at'),
    Index('idx_dashboard_cache_accessed', 'accessed_at'),
    Index('idx_dashboard_cache_key', 'cache_key'),
    Index('idx_dashboard_cache_topic', 'topic')
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

t_user_preferences = Table(
    'user_preferences', metadata,
    Column('id', Integer, primary_key=True),
    Column('username', ForeignKey('users.username', ondelete='CASCADE'), nullable=False),
    Column('preference_key', String(255), nullable=False),
    Column('config_value', JSON),
    Column('created_at', DateTime, server_default=text('NOW()'), nullable=False),
    Column('updated_at', DateTime, server_default=text('NOW()'), nullable=False),
    UniqueConstraint('username', 'preference_key', name='uq_user_preference_key'),
    Index('ix_user_preferences_username', 'username')
)

t_notifications = Table(
    'notifications', metadata,
    Column('id', Integer, primary_key=True),
    Column('username', Text, ForeignKey('users.username', ondelete='CASCADE'), nullable=True),
    Column('type', String(50), nullable=False),
    Column('title', String(255), nullable=False),
    Column('message', Text, nullable=False),
    Column('link', String(500), nullable=True),
    Column('read', Boolean, nullable=False, server_default='false'),
    Column('created_at', DateTime(timezone=True), nullable=False, server_default=text('CURRENT_TIMESTAMP')),
    Index('ix_notifications_username', 'username'),
    Index('ix_notifications_read', 'read'),
    Index('ix_notifications_created_at', 'created_at'),
    Index('ix_notifications_username_read', 'username', 'read')
)

# Trend Convergence Dashboard Reference Article Tables
t_consensus_reference_articles = Table(
    'consensus_reference_articles', metadata,
    Column('id', Integer, primary_key=True),
    Column('consensus_id', String(36), nullable=False),
    Column('article_uri', String, ForeignKey('articles.uri')),
    Column('topic', String, nullable=False),
    Column('retrieved_at', DateTime, server_default=text('CURRENT_TIMESTAMP')),
    Index('ix_consensus_ref_articles_consensus_id', 'consensus_id'),
    Index('ix_consensus_ref_articles_topic', 'topic')
)

t_strategic_recommendation_articles = Table(
    'strategic_recommendation_articles', metadata,
    Column('id', Integer, primary_key=True),
    Column('recommendation_id', String(36), nullable=False),
    Column('article_uri', String, ForeignKey('articles.uri')),
    Column('topic', String, nullable=False),
    Column('retrieved_at', DateTime, server_default=text('CURRENT_TIMESTAMP')),
    Index('ix_strategic_rec_articles_recommendation_id', 'recommendation_id'),
    Index('ix_strategic_rec_articles_topic', 'topic')
)

t_market_signal_articles = Table(
    'market_signal_articles', metadata,
    Column('id', Integer, primary_key=True),
    Column('signal_id', String(36), nullable=False),
    Column('article_uri', String, ForeignKey('articles.uri')),
    Column('topic', String, nullable=False),
    Column('retrieved_at', DateTime, server_default=text('CURRENT_TIMESTAMP')),
    Index('ix_market_signal_articles_signal_id', 'signal_id'),
    Index('ix_market_signal_articles_topic', 'topic')
)

t_impact_timeline_articles = Table(
    'impact_timeline_articles', metadata,
    Column('id', Integer, primary_key=True),
    Column('timeline_id', String(36), nullable=False),
    Column('article_uri', String, ForeignKey('articles.uri')),
    Column('topic', String, nullable=False),
    Column('retrieved_at', DateTime, server_default=text('CURRENT_TIMESTAMP')),
    Index('ix_impact_timeline_articles_timeline_id', 'timeline_id'),
    Index('ix_impact_timeline_articles_topic', 'topic')
)

t_future_horizon_articles = Table(
    'future_horizon_articles', metadata,
    Column('id', Integer, primary_key=True),
    Column('horizon_id', String(36), nullable=False),
    Column('article_uri', String, ForeignKey('articles.uri')),
    Column('topic', String, nullable=False),
    Column('retrieved_at', DateTime, server_default=text('CURRENT_TIMESTAMP')),
    Index('ix_future_horizon_articles_horizon_id', 'horizon_id'),
    Index('ix_future_horizon_articles_topic', 'topic')
)

t_forecast_assessments = Table(
    'forecast_assessments', metadata,
    Column('id', String(36), primary_key=True),
    Column('run_id', String(36), nullable=False),
    Column('topic', Text, nullable=False),
    Column('assessed_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    Column('evidence_count', Integer, nullable=False, server_default=text('0')),
    Column('scenarios_count', Integer, nullable=False, server_default=text('0')),
    Column('ambiguous_count', Integer, nullable=False, server_default=text('0')),
    Column('unrelated_count', Integer, nullable=False, server_default=text('0')),
    Column('surprises', JSONB),
    Column('summary', JSONB),
    Column('status', String(32), nullable=False, server_default=text("'completed'")),
    Column('mode', String(32), nullable=False, server_default=text("'live'")),
    Column('model_used', String(100)),
    Column('runtime_seconds', Float),
    Column('config', JSONB),
    # Dot-paths into `summary` that the analyst has locked. Supervisor
    # re-runs of per-topic stages (briefing/recs/next_steps) restore
    # these subtrees from their pre-run snapshot.
    Column('summary_locked_keys', JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Index('ix_forecast_assessments_run_id', 'run_id'),
    Index('ix_forecast_assessments_topic_assessed', 'topic', 'assessed_at'),
)

t_forecast_scenario_verdicts = Table(
    'forecast_scenario_verdicts', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('assessment_id', String(36), nullable=False),
    Column('scenario_idx', Integer, nullable=False),
    Column('horizon_type', String(4), nullable=False),
    Column('scenario_title', Text, nullable=False),
    Column('verdict_label', String(32), nullable=False),
    Column('directional_rate', Float),
    Column('velocity', Float),
    Column('milestone_density', Float),
    Column('coverage', Float),
    Column('supports', Integer, nullable=False, server_default=text('0')),
    Column('contradicts', Integer, nullable=False, server_default=text('0')),
    Column('neutral', Integer, nullable=False, server_default=text('0')),
    Column('summary_md', Text),
    Column('top_articles', JSONB),
    # Freshly-measured "X% of confident verdicts support this scenario" — shown
    # alongside the original deck-authored consensus_pct on the Wiley bundle's
    # Briefing Synthesis / Consensus & Outlier slides so the reader can see
    # quarter-over-quarter drift.
    Column('current_consensus_pct', Float),
    # Per-scenario LLM-synthesised artefacts: key_signals (list of 2-3 phrases),
    # strategic_imperative (single sentence). Cached lazily.
    Column('synthesis', JSONB),
    UniqueConstraint('assessment_id', 'scenario_idx', name='uq_scenario_verdicts_assessment_scenario'),
    Index('ix_scenario_verdicts_assessment', 'assessment_id'),
)

# Cross-topic LLM-synthesised artefacts that span an entire bundle run —
# strategic_overview, cross_cutting_themes, executive_decision_framework.
# Keyed by (cadence, period_label) so re-exports of the same quarter hit
# the cache. Cleared by quarter boundary; bundle service recomputes when
# the period_label changes.
t_forecast_bundle_synthesis = Table(
    'forecast_bundle_synthesis', metadata,
    Column('cadence', String(16), primary_key=True),
    Column('period_label', String(64), primary_key=True),
    Column('payload', JSONB, nullable=False),
    Column('topics', JSONB),
    # Dot-paths into `payload` that the analyst has locked. Supervisor
    # re-runs restore these subtrees from their pre-run snapshot so an
    # accidental "regenerate" doesn't clobber edited prose.
    Column('locked_keys', JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    # Append-only audit log of analyst edits. Each entry:
    # {key, prev_hash, next_hash, edited_by, edited_at}. Hashes keep the
    # column small while still supporting "who changed what when" audit.
    Column('edit_history', JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column('created_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    Column('updated_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
)

# Review gate state for the WileyBundleSupervisor pipeline. The LLM-as-judge
# reviewer agent populates ``reviewer_findings`` after each generation;
# ``status`` advances through awaiting_synth → under_review → either
# revision_requested (blocks) / approved_with_warnings / approved → shipped.
# A human approver clears the gate via the Wiley Deliverables UI.
t_forecast_bundle_review = Table(
    'forecast_bundle_review', metadata,
    Column('cadence', String(16), primary_key=True),
    Column('period_label', String(64), primary_key=True),
    Column('status', String(32), nullable=False, server_default=text("'awaiting_synth'")),
    Column('reviewer_findings', JSONB),
    Column('reviewer_model', Text),
    Column('approved_by', Text),
    Column('approved_at', DateTime(timezone=True)),
    Column('shipped_at', DateTime(timezone=True)),
    Column('created_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    Column('updated_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
)

# Events extracted by the wiley_event_extractor_agent during the bundle's
# events stage. Dedupe key: (topic, actor_normalized, action,
# subject_normalized, event_date). Manual analyst additions land here
# with origin='manual'. include_in_deck is the analyst's curate toggle.
t_extracted_events = Table(
    'extracted_events', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('assessment_id', String(36), nullable=True),
    Column('topic', Text, nullable=False),
    Column('cadence', String(16), nullable=True),
    Column('period_label', String(64), nullable=True),
    Column('actor', Text, nullable=False),
    Column('actor_normalized', Text, nullable=False),
    Column('action', Text, nullable=False),
    Column('subject', Text, nullable=False),
    Column('subject_normalized', Text, nullable=False),
    Column('magnitude_value', Float),
    Column('magnitude_unit', Text),
    Column('event_date', Date),
    Column('source_urls', JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column('confidence', Float),
    Column('requires_review', Boolean, nullable=False, server_default=text('false')),
    Column('include_in_deck', Boolean, nullable=False, server_default=text('true')),
    Column('scenario_relevance', JSONB),
    Column('origin', String(16), nullable=False, server_default=text("'auto'")),
    Column('edited_by', Text),
    Column('created_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    Column('updated_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    UniqueConstraint('topic', 'actor_normalized', 'action',
                     'subject_normalized', 'event_date',
                     name='uq_extracted_events_dedupe'),
    Index('idx_extracted_events_topic_period', 'topic', 'period_label'),
    Index('idx_extracted_events_assessment', 'assessment_id'),
    Index('idx_extracted_events_requires_review', 'requires_review'),
)


t_forecast_article_verdicts = Table(
    'forecast_article_verdicts', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('assessment_id', String(36), nullable=False),
    Column('article_uri', Text, nullable=False),
    Column('scenario_idx', Integer),
    Column('verdict', String(48), nullable=False),
    Column('evidence_type', String(24)),
    Column('confidence', Float),
    Column('rerank_score', Float),
    Column('margin', Float),
    Column('best_alt_scenario_idx', Integer),
    Column('rationale', Text),
    Column('article_date', Text),
    Column('recorded_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    Index('ix_article_verdicts_assessment_scenario', 'assessment_id', 'scenario_idx'),
    Index('ix_article_verdicts_assessment_uri', 'assessment_id', 'article_uri'),
)

# User-promoted scenarios — created by clicking "Track as scenario" on a
# surprise cluster in the Forecast Tracker. Stored as an addendum so the
# original future_horizons_runs.raw_output['scenarios'] stays untouched
# (preserving the audit trail of what was originally forecast). The
# assessment service concatenates these with the original scenarios at
# run time and assigns them higher scenario_idx values.
t_forecast_user_scenarios = Table(
    'forecast_user_scenarios', metadata,
    Column('id', String(36), primary_key=True),
    Column('run_id', String(36), nullable=False),
    Column('title', Text, nullable=False),
    Column('description', Text, nullable=False),
    Column('horizon_type', String(4), nullable=False),
    Column('timeframe', String(32)),
    Column('source_assessment_id', String(36)),
    Column('source_surprise_label', Text),
    Column('source_article_uris', JSONB),
    Column('created_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    Index('ix_forecast_user_scenarios_run', 'run_id'),
)

# Overlay table for marking any scenario (original or addendum) as "done".
# Polymorphic: exactly one of scenario_idx (original) or user_scenario_id
# (addendum) is set per row. Done scenarios are skipped from reranker/LLM
# during assess_run but still get a placeholder verdict row at the same
# scenario_idx so historical comparisons stay valid (scenario_idx is
# positional within an assess-time list).
t_forecast_scenario_status = Table(
    'forecast_scenario_status', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('run_id', String(36), nullable=False),
    Column('scenario_idx', Integer),  # nullable: set for originals
    Column('user_scenario_id', String(36)),  # nullable: set for addendums
    Column('status', String(16), nullable=False, server_default=text("'active'")),
    Column('marked_done_at', DateTime(timezone=True)),
    Column('note', Text),
    UniqueConstraint('run_id', 'scenario_idx', 'user_scenario_id',
                     name='uq_scenario_status_run_keys'),
    Index('ix_forecast_scenario_status_run', 'run_id'),
)

# Per-topic delivery cadence for the Wiley reporting pipeline. Sets which
# topics roll up into the monthly per-topic update vs. the quarterly bundle
# of the 5 core topics, plus the recipient address(es) and last-delivered
# timestamp the scheduler uses to avoid duplicate sends.
t_forecast_topic_delivery = Table(
    'forecast_topic_delivery', metadata,
    Column('topic', Text, primary_key=True),
    Column('cadence', String(16), nullable=False, server_default=text("'none'")),
    Column('recipient_email', Text),
    Column('last_delivered_at', DateTime(timezone=True)),
    Column('updated_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
)

# Sidecar metadata for a forecast topic — owner, description, status,
# overlay-review status. Keyed by the same topic string used everywhere
# else so existing rows remain untouched. Powers the Topics dashboard and
# the "Add topic" wizard.
t_forecast_topic_metadata = Table(
    'forecast_topic_metadata', metadata,
    Column('topic', Text, primary_key=True),
    Column('display_name', Text),
    Column('description', Text),
    Column('owner', Text),
    Column('status', String(16), nullable=False, server_default=text("'active'")),
    Column('tags', JSONB),
    Column('overlay_status', String(16), nullable=False, server_default=text("'missing'")),
    # Optional pointer back to the candidate this topic was promoted from
    # (added in fa_007). NULL for topics created without going through the
    # Candidates inbox.
    Column('source_candidate_id', Integer,
           ForeignKey('topic_candidates.id', ondelete='SET NULL')),
    # Consensus-topic lifecycle (fa_010). A tracked topic is a CLAIM whose
    # consensus is the forecast basis; the loop formalizes it, analyzes each
    # cycle, and retires it once evidence/coverage dies down.
    #   claim_statement     — the documented claim being tracked
    #   basis_consensus_pct — source-consensus % at formalization (the basis)
    #   formalized_at       — when promoted to a tracked consensus topic
    #   last_evidence_cycle — period_label of the last cycle with new events
    #   dormant_since       — period_label when it first went evidence-quiet
    Column('claim_statement', Text),
    Column('basis_consensus_pct', Float),
    Column('formalized_at', DateTime(timezone=True)),
    Column('last_evidence_cycle', String(64)),
    Column('dormant_since', String(64)),
    # Existing corpus topics that back this (possibly decoupled) deck name,
    # set by the Add-Topic wizard (fa_011). The forecast assessment reads
    # these to pull its post-forecast article window from the real corpus
    # when the deck name itself tags no articles. NULL = fall back to deck name.
    Column('source_topics', JSONB),
    Column('created_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    Column('updated_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    Index('idx_topic_metadata_status', 'status'),
    Index('idx_topic_metadata_owner', 'owner'),
)

# Candidate-topics inbox — emerging clusters that the relevance judge
# scored against the Wiley organizational profile. Analysts triage via
# the Topics dashboard. Promoted candidates become formal topics in
# forecast_topic_metadata, with source_candidate_id pointing back here.
t_topic_candidates = Table(
    'topic_candidates', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('emerging_topic_id', Integer,
           ForeignKey('emerging_topics.id', ondelete='CASCADE'), nullable=False),
    Column('org_profile_id', Integer,
           ForeignKey('organizational_profiles.id', ondelete='CASCADE'), nullable=False),
    Column('relevance_verdict', String(16), nullable=False),  # 'in_scope' | 'adjacent' | 'off_scope'
    Column('relevance_score', Float),
    Column('relevance_rationale', Text),
    Column('proposed_topic_name', Text),
    Column('proposed_description', Text),
    Column('proposed_tags', JSONB),
    Column('triage_status', String(16), nullable=False,
           server_default=text("'pending'")),
    Column('snooze_until', Date),
    Column('rejected_reason', Text),
    Column('promoted_to_topic', Text),
    Column('triaged_by', Text),
    Column('triaged_at', DateTime(timezone=True)),
    Column('created_at', DateTime(timezone=True),
           server_default=text('NOW()'), nullable=False),
    Column('updated_at', DateTime(timezone=True),
           server_default=text('NOW()'), nullable=False),
    UniqueConstraint('emerging_topic_id', 'org_profile_id',
                     name='uq_topic_candidates_topic_profile'),
    Index('idx_topic_candidates_triage_status', 'triage_status'),
    Index('idx_topic_candidates_verdict', 'relevance_verdict'),
    Index('idx_topic_candidates_snooze_until', 'snooze_until'),
)

# LLM Error Handling and Circuit Breaker Tables

t_llm_retry_state = Table(
    'llm_retry_state', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('model_name', String(255), nullable=False, unique=True),
    Column('consecutive_failures', Integer, server_default=text('0')),
    Column('last_failure_time', TIMESTAMP),
    Column('last_success_time', TIMESTAMP),
    Column('circuit_state', String(50), server_default=text("'closed'")),  # 'closed', 'open', 'half_open'
    Column('circuit_opened_at', TIMESTAMP),
    Column('failure_rate', Float, server_default=text('0.0')),
    Column('last_updated', TIMESTAMP, server_default=text('CURRENT_TIMESTAMP')),
    Column('metadata', JSONB),
    Index('idx_llm_retry_model_name', 'model_name'),
    Index('idx_llm_retry_circuit_state', 'circuit_state')
)

t_llm_processing_errors = Table(
    'llm_processing_errors', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('article_id', Integer, ForeignKey('articles.id', ondelete='CASCADE')),
    Column('error_type', String(255), nullable=False),
    Column('error_message', Text, nullable=False),
    Column('severity', String(50), nullable=False),  # 'fatal', 'recoverable', 'skippable', 'degraded'
    Column('model_name', String(255), nullable=False),
    Column('retry_count', Integer, server_default=text('0')),
    Column('will_retry', Boolean, server_default=text('false')),
    Column('context', JSONB),
    Column('timestamp', TIMESTAMP, nullable=False),
    Column('created_at', TIMESTAMP, server_default=text('CURRENT_TIMESTAMP')),
    Index('idx_llm_errors_article_id', 'article_id'),
    Index('idx_llm_errors_model_name', 'model_name'),
    Index('idx_llm_errors_severity', 'severity'),
    Index('idx_llm_errors_timestamp', 'timestamp')
)

t_processing_jobs = Table(
    'processing_jobs', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('job_id', String(255), nullable=False, unique=True),
    Column('job_type', String(50), nullable=False),  # 'batch_ingest', 'analysis', 'bulk_research'
    Column('status', String(50), nullable=False),  # 'running', 'completed', 'error', 'partial'
    Column('total_items', Integer, server_default=text('0')),
    Column('processed_items', Integer, server_default=text('0')),
    Column('failed_items', Integer, server_default=text('0')),
    Column('error_summary', JSONB),
    Column('started_at', TIMESTAMP, server_default=text('CURRENT_TIMESTAMP')),
    Column('completed_at', TIMESTAMP),
    Column('metadata', JSONB),
    Index('idx_processing_jobs_job_id', 'job_id'),
    Index('idx_processing_jobs_status', 'status'),
    Index('idx_processing_jobs_job_type', 'job_type')
)

# Auspex Research Tables
t_auspex_research_sessions = Table(
    'auspex_research_sessions', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('chat_id', Integer, ForeignKey('auspex_chats.id', ondelete='CASCADE')),
    Column('username', Text, ForeignKey('users.username', ondelete='CASCADE'), nullable=False),
    Column('query', Text, nullable=False),
    Column('topic', String(255), nullable=False),
    Column('status', String(50), server_default=text("'pending'"), nullable=False),
    Column('objectives', JSONB),
    Column('findings', JSONB),
    Column('report', Text),
    Column('metadata', JSONB),
    Column('created_at', DateTime, server_default=text('CURRENT_TIMESTAMP')),
    Column('completed_at', DateTime),
    Index('ix_auspex_research_sessions_username', 'username'),
    Index('ix_auspex_research_sessions_chat_id', 'chat_id'),
    Index('ix_auspex_research_sessions_status', 'status'),
    Index('ix_auspex_research_sessions_created_at', 'created_at')
)

t_auspex_tool_usage = Table(
    'auspex_tool_usage', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('chat_id', Integer, ForeignKey('auspex_chats.id', ondelete='SET NULL')),
    Column('tool_name', String(100), nullable=False),
    Column('tool_version', String(20)),
    Column('parameters', JSONB),
    Column('result_summary', JSONB),
    Column('execution_ms', Integer),
    Column('created_at', DateTime, server_default=text('CURRENT_TIMESTAMP')),
    Index('ix_auspex_tool_usage_tool_name', 'tool_name'),
    Index('ix_auspex_tool_usage_created_at', 'created_at')
)

t_auspex_search_routing = Table(
    'auspex_search_routing', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('query', Text, nullable=False),
    Column('topic', String(255)),
    Column('recommended_source', String(50), nullable=False),
    Column('actual_source', String(50), nullable=False),
    Column('confidence', Float),
    Column('signals', JSONB),
    Column('result_quality', Float),  # For feedback loop
    Column('created_at', DateTime, server_default=text('CURRENT_TIMESTAMP')),
    Index('ix_auspex_search_routing_created_at', 'created_at'),
    Index('ix_auspex_search_routing_recommended_source', 'recommended_source')
)


# Emerging Topics Detection Tables
t_emerging_topics = Table(
    'emerging_topics', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('topic_label', String(255), nullable=False),
    Column('topic_description', Text),
    Column('detection_date', DateTime, nullable=False),
    Column('detection_type', String(50), nullable=False),  # 'new_cluster', 'splitting', 'accelerating', 'proto_cluster'

    # Cluster identification
    Column('cluster_id', String(100)),
    Column('parent_cluster_id', Integer, ForeignKey('emerging_topics.id', ondelete='SET NULL')),

    # Cluster metrics (centroid_embedding is vector(1536), accessed via raw SQL)
    Column('article_count', Integer, default=0),
    Column('avg_novelty_score', Float),
    Column('cluster_density', Float),
    Column('cluster_radius', Float),

    # Velocity/growth metrics
    Column('growth_rate', Float),
    Column('velocity', String(20)),  # 'accelerating', 'stable', 'decelerating'
    Column('velocity_change_pct', Float),

    # LLM-generated analysis
    Column('key_themes', JSONB),
    Column('representative_keywords', JSONB),
    Column('related_existing_topics', JSONB),
    Column('emergence_rationale', Text),

    # Status and confidence
    Column('status', String(20), default='active'),  # 'active', 'merged', 'declined', 'confirmed'
    Column('confidence_score', Float),

    # Article references
    Column('article_uris', ARRAY(Text)),
    Column('sample_article_uris', ARRAY(Text)),

    # Optional topic filter
    Column('topic_filter', String(255)),

    # Processing metadata
    Column('model_used', String(100)),
    Column('config', JSONB),

    # Timestamps
    Column('created_at', DateTime, server_default=text('CURRENT_TIMESTAMP')),
    Column('updated_at', DateTime, server_default=text('CURRENT_TIMESTAMP')),

    Index('ix_emerging_topics_date', 'detection_date'),
    Index('ix_emerging_topics_type', 'detection_type'),
    Index('ix_emerging_topics_status', 'status'),
    Index('ix_emerging_topics_confidence', 'confidence_score'),
    Index('ix_emerging_topics_topic_filter', 'topic_filter')
)

t_article_novelty_scores = Table(
    'article_novelty_scores', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('article_uri', Text, ForeignKey('articles.uri', ondelete='CASCADE'), nullable=False),
    Column('calculation_date', DateTime, nullable=False),

    # Component scores (0-100)
    Column('knn_distance_score', Float, nullable=False),
    Column('density_score', Float, nullable=False),
    Column('centroid_distance_score', Float, nullable=False),
    Column('composite_novelty_score', Float, nullable=False),

    # KNN calculation details
    Column('k_neighbors', Integer, default=10),
    Column('avg_knn_distance', Float),
    Column('min_knn_distance', Float),
    Column('max_knn_distance', Float),

    # Density calculation details
    Column('local_density', Float),
    Column('density_radius', Float),

    # Cluster assignment
    Column('nearest_cluster_id', String(100)),
    Column('distance_to_nearest_cluster', Float),
    Column('is_outlier', Boolean, default=False),

    # Link to emerging topic if assigned
    Column('emerging_topic_id', Integer, ForeignKey('emerging_topics.id', ondelete='SET NULL')),

    # Timestamps
    Column('created_at', DateTime, server_default=text('CURRENT_TIMESTAMP')),

    Index('ix_novelty_scores_article', 'article_uri'),
    Index('ix_novelty_scores_date', 'calculation_date'),
    Index('ix_novelty_scores_composite', 'composite_novelty_score'),
    Index('ix_novelty_scores_outlier', 'is_outlier', 'calculation_date'),
    UniqueConstraint('article_uri', 'calculation_date', name='uq_novelty_scores_article_date')
)

t_cluster_snapshots = Table(
    'cluster_snapshots', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('snapshot_date', DateTime, nullable=False),
    Column('cluster_id', String(100), nullable=False),

    # Cluster state (centroid_embedding is vector(1536), accessed via raw SQL)
    Column('article_count', Integer),
    Column('avg_internal_distance', Float),
    Column('cluster_radius', Float),

    # Evolution metrics
    Column('centroid_drift', Float),
    Column('size_change', Integer),
    Column('composition_similarity', Float),

    # Cluster status flags
    Column('is_new', Boolean, default=False),
    Column('is_splitting', Boolean, default=False),
    Column('is_merging', Boolean, default=False),

    # Parent/child tracking
    Column('parent_cluster_ids', JSONB),
    Column('child_cluster_ids', JSONB),

    # Article membership
    Column('article_uris', ARRAY(Text)),

    # Optional topic filter
    Column('topic_filter', String(255)),

    # LLM-generated label
    Column('cluster_label', String(255)),

    # Timestamps
    Column('created_at', DateTime, server_default=text('CURRENT_TIMESTAMP')),

    Index('ix_cluster_snapshots_date', 'snapshot_date'),
    Index('ix_cluster_snapshots_cluster', 'cluster_id'),
    Index('ix_cluster_snapshots_topic', 'topic_filter'),
    UniqueConstraint('snapshot_date', 'cluster_id', 'topic_filter', name='uq_cluster_snapshots_date_cluster')
)


# RSS Feed Tables
t_rss_feeds = Table(
    'rss_feeds', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String(255), nullable=False),
    Column('url', Text, nullable=False),
    Column('topic', String(255), nullable=False),
    Column('description', Text),

    # Schedule settings
    Column('is_active', Boolean, server_default=text('true'), nullable=False),
    Column('check_interval', Integer, server_default=text('60'), nullable=False),
    Column('interval_unit', String(20), server_default=text("'minutes'")),

    # Relevance filtering (0 = skip filtering, 1-100 = threshold percentage)
    Column('relevance_threshold', Integer, server_default=text('0'), nullable=False),

    # Source credibility - factual reporting level to set on enriched articles
    Column('default_factual_reporting', String(50)),

    # Tracking
    Column('last_checked_at', DateTime(timezone=True)),
    Column('last_article_date', DateTime(timezone=True)),
    Column('articles_fetched', Integer, server_default=text('0'), nullable=False),
    Column('articles_enriched', Integer, server_default=text('0'), nullable=False),
    Column('last_error', Text),

    # Timestamps
    Column('created_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    Column('updated_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),

    Index('ix_rss_feeds_topic', 'topic'),
    Index('ix_rss_feeds_is_active', 'is_active'),
    Index('ix_rss_feeds_last_checked', 'last_checked_at')
)

t_rss_feed_monitor_status = Table(
    'rss_feed_monitor_status', metadata,
    Column('id', Integer, primary_key=True),
    Column('is_running', Boolean, server_default=text('false'), nullable=False),
    Column('last_check_time', DateTime(timezone=True)),
    Column('next_check_time', DateTime(timezone=True)),
    Column('feeds_checked', Integer, server_default=text('0')),
    Column('articles_fetched', Integer, server_default=text('0')),
    Column('last_error', Text),
    Column('last_run_duration_seconds', Float),
    Column('created_at', DateTime(timezone=True), server_default=text('NOW()')),
    Column('updated_at', DateTime(timezone=True), server_default=text('NOW()'))
)


# Geopolitical Hotspots Tables
t_geopolitical_hotspots = Table(
    'geopolitical_hotspots', metadata,
    Column('id', Integer, primary_key=True),
    Column('location_name', Text, nullable=False),
    Column('location_type', Text, nullable=False),  # city, region, country
    Column('country_code', String(2), nullable=True),  # ISO 3166-1 alpha-2
    Column('country_name', Text, nullable=True),
    Column('latitude', Float, nullable=False),
    Column('longitude', Float, nullable=False),
    Column('intensity_score', Float, nullable=False, server_default=text('0')),  # 0-100
    Column('risk_level', Text, nullable=False, server_default=text("'low'")),  # critical, high, medium, low, info
    Column('trend', Text, server_default=text("'stable'")),  # escalating, stable, de-escalating
    Column('article_count', Integer, nullable=False, server_default=text('0')),
    Column('recent_article_count', Integer, nullable=False, server_default=text('0')),  # 7 days
    Column('primary_category', Text, nullable=True),
    Column('tags', JSONB, nullable=True),
    Column('topic', Text, nullable=True),
    Column('last_article_date', DateTime(timezone=True), nullable=True),
    Column('created_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    Column('updated_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    Index('idx_geopolitical_hotspots_location', 'location_name'),
    Index('idx_geopolitical_hotspots_country', 'country_code'),
    Index('idx_geopolitical_hotspots_risk', 'risk_level'),
    Index('idx_geopolitical_hotspots_intensity', 'intensity_score'),
    Index('idx_geopolitical_hotspots_category', 'primary_category'),
    Index('idx_geopolitical_hotspots_topic', 'topic'),
    Index('idx_geopolitical_hotspots_coords', 'latitude', 'longitude'),
)

t_hotspot_articles = Table(
    'hotspot_articles', metadata,
    Column('id', Integer, primary_key=True),
    Column('hotspot_id', Integer, ForeignKey('geopolitical_hotspots.id', ondelete='CASCADE'), nullable=False),
    Column('article_uri', Text, ForeignKey('articles.uri', ondelete='CASCADE'), nullable=False),
    Column('relevance_score', Float, nullable=True),  # 0-1
    Column('mention_type', Text, nullable=True),  # primary, secondary, background
    Column('extracted_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    UniqueConstraint('hotspot_id', 'article_uri', name='uq_hotspot_article'),
    Index('idx_hotspot_articles_hotspot', 'hotspot_id'),
    Index('idx_hotspot_articles_article', 'article_uri'),
)

t_hotspot_daily_stats = Table(
    'hotspot_daily_stats', metadata,
    Column('id', Integer, primary_key=True),
    Column('date', DateTime, nullable=False),
    Column('hotspot_id', Integer, ForeignKey('geopolitical_hotspots.id', ondelete='CASCADE'), nullable=False),
    Column('article_count', Integer, nullable=False, server_default=text('0')),
    Column('intensity_score', Float, nullable=True),
    Column('trend', Text, nullable=True),
    Column('updated_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    UniqueConstraint('date', 'hotspot_id', name='uq_hotspot_daily_stats'),
    Index('idx_hotspot_daily_stats_date', 'date'),
    Index('idx_hotspot_daily_stats_hotspot', 'hotspot_id'),
)

t_country_hotspot_stats = Table(
    'country_hotspot_stats', metadata,
    Column('id', Integer, primary_key=True),
    Column('country_code', String(2), nullable=False, unique=True),
    Column('country_name', Text, nullable=False),
    Column('total_hotspots', Integer, nullable=False, server_default=text('0')),
    Column('total_articles', Integer, nullable=False, server_default=text('0')),
    Column('heat_value', Float, nullable=False, server_default=text('0')),  # 0-100
    Column('max_risk_level', Text, nullable=True),
    Column('primary_category', Text, nullable=True),
    Column('topic', Text, nullable=True),
    Column('updated_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    Index('idx_country_hotspot_stats_code', 'country_code'),
    Index('idx_country_hotspot_stats_heat', 'heat_value'),
    Index('idx_country_hotspot_stats_topic', 'topic'),
)

t_geopolitical_insights = Table(
    'geopolitical_insights', metadata,
    Column('id', Integer, primary_key=True),
    Column('topic', Text, nullable=True),
    Column('insight_type', Text, nullable=False),  # overview, regional, category, trend
    Column('content', Text, nullable=False),
    Column('metadata', JSONB, nullable=True),
    Column('model_used', Text, nullable=True),
    Column('hotspot_ids', ARRAY(Integer), nullable=True),
    Column('created_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    Column('expires_at', DateTime(timezone=True), nullable=True),
    Index('idx_geopolitical_insights_type', 'insight_type'),
    Index('idx_geopolitical_insights_topic', 'topic'),
    Index('idx_geopolitical_insights_created', 'created_at'),
)

# Adaptive Classification Training Tables
t_enrichment_training_samples = Table(
    'enrichment_training_samples', metadata,
    Column('id', Integer, primary_key=True),
    Column('article_uri', Text, ForeignKey('articles.uri', ondelete='CASCADE'), nullable=False),
    Column('topic', Text, nullable=False),
    Column('field_name', Text, nullable=False),  # 'sentiment', 'time_to_impact', etc.
    Column('field_value', Text, nullable=False),
    Column('source', Text, nullable=False),  # 'llm_bootstrap', 'human_verified'
    Column('model_used', Text),  # 'gpt-5.4-mini'
    Column('confidence', Float),
    Column('created_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    UniqueConstraint('article_uri', 'field_name', name='uq_training_sample_article_field'),
    Index('idx_training_samples_topic', 'topic'),
    Index('idx_training_samples_field', 'field_name'),
    Index('idx_training_samples_source', 'source'),
    Index('idx_training_samples_topic_field', 'topic', 'field_name'),
)

t_training_sample_counts = Table(
    'training_sample_counts', metadata,
    Column('id', Integer, primary_key=True),
    Column('topic', Text, nullable=False),
    Column('field_name', Text, nullable=False),
    Column('field_value', Text, nullable=False),
    Column('sample_count', Integer, nullable=False, server_default=text('0')),
    Column('last_updated', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    UniqueConstraint('topic', 'field_name', 'field_value', name='uq_sample_counts_topic_field_value'),
    Index('idx_sample_counts_topic', 'topic'),
    Index('idx_sample_counts_field', 'field_name'),
    Index('idx_sample_counts_topic_field', 'topic', 'field_name'),
)

t_training_runs = Table(
    'training_runs', metadata,
    Column('id', Integer, primary_key=True),
    Column('run_id', Text, nullable=False, unique=True),
    Column('status', Text, nullable=False, server_default=text("'pending'")),  # pending, running, completed, failed, deployed
    Column('topics_included', JSONB),
    Column('fields_included', JSONB),
    Column('sample_count', Integer),
    Column('metrics', JSONB),  # accuracy, f1, etc.
    Column('started_at', DateTime(timezone=True)),
    Column('completed_at', DateTime(timezone=True)),
    Column('model_path', Text),
    Column('error_message', Text),
    Column('created_at', DateTime(timezone=True), server_default=text('NOW()'), nullable=False),
    Index('idx_training_runs_status', 'status'),
    Index('idx_training_runs_created', 'created_at'),
)
