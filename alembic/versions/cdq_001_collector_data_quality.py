"""Collector data quality: checkpoints, run records, identity, dates, backoff.

Additive only. Every column is nullable or defaulted and every table is new,
so an older collector keeps running against the upgraded schema. Nothing is
backfilled here: attempt timestamps are not evidence of coverage (work
package 1), and dates are repaired from source payloads, not guessed.

What each piece is for (docs/COLLECTOR_DATA_QUALITY_SPEC.md):

- rss_feeds backoff and checkpoint columns: work packages 1, 2, 21, 29.
- articles date, content, identity and quarantine columns: 7, 8, 4, 22.
- collection_runs: the durable run record, work package 14.
- collection_checkpoints: fixed intervals with continuation and a lease, 1.
- rejected_candidates: the early-gate ledger, work package 19.
- article_observations / article_url_aliases: identity and merging, 4 and 30.
- pending_feed_entries: the durable pending batch for long feeds, 2 and 16.

Revision ID: cdq_001
Revises: si_001
Create Date: 2026-10-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB

revision = 'cdq_001'
down_revision = 'si_001'
branch_labels = None
depends_on = None


def _has_table(name):
    return inspect(op.get_bind()).has_table(name)


def _has_column(table, column):
    bind = op.get_bind()
    return column in {c['name'] for c in inspect(bind).get_columns(table)}


def _add(table, column):
    if not _has_column(table, column.name):
        op.add_column(table, column)


def upgrade():
    # -- rss_feeds: scheduling state apart from coverage state --------------
    for col in (
        sa.Column('consecutive_error_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('polling_status', sa.String(20), server_default='ok', nullable=False),
        sa.Column('first_failed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_failed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_poll_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_attempt_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('coverage_through', sa.DateTime(timezone=True), nullable=True),
        sa.Column('etag', sa.Text(), nullable=True),
        sa.Column('last_modified', sa.Text(), nullable=True),
        sa.Column('parse_partial_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('pending_batch', JSONB(), nullable=True),
        sa.Column('needs_attention_reason', sa.Text(), nullable=True),
    ):
        _add('rss_feeds', col)
    op.execute("CREATE INDEX IF NOT EXISTS ix_rss_feeds_polling_status ON rss_feeds (polling_status)")

    # -- articles: dates with precision, content kind, identity, quarantine --
    for col in (
        sa.Column('published_at_raw', sa.Text(), nullable=True),
        sa.Column('publication_date_precision', sa.String(8), nullable=True),
        sa.Column('date_provenance', sa.String(32), nullable=True),
        sa.Column('source_indexed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('future_date_flag', sa.Boolean(), nullable=True),
        sa.Column('content_kind', sa.String(16), nullable=True),
        sa.Column('extraction_status', sa.String(32), nullable=True),
        sa.Column('identity_method', sa.String(24), nullable=True),
        sa.Column('canonical_url', sa.Text(), nullable=True),
        sa.Column('record_type', sa.String(16), nullable=True),
        sa.Column('enrichment_block_reason', sa.Text(), nullable=True),
        sa.Column('enrichment_attempts', sa.Integer(), server_default='0', nullable=True),
    ):
        _add('articles', col)
    op.execute("CREATE INDEX IF NOT EXISTS ix_articles_canonical_url ON articles (canonical_url) "
               "WHERE canonical_url IS NOT NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_articles_quarantine ON articles (topic, ingest_status) "
               "WHERE ingest_status IN ('quarantined_config', 'enrichment_failed')")
    op.execute("CREATE INDEX IF NOT EXISTS ix_articles_first_seen ON articles (first_seen_at) "
               "WHERE first_seen_at IS NOT NULL")

    # -- collection_runs: the durable run record (work package 14) ----------
    if not _has_table('collection_runs'):
        op.create_table(
            'collection_runs',
            sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column('provider', sa.String(40), nullable=False),
            sa.Column('scope_kind', sa.String(32), nullable=True),
            sa.Column('scope_id', sa.Text(), nullable=True),
            sa.Column('status', sa.String(12), nullable=False),
            sa.Column('interval_start', sa.DateTime(timezone=True), nullable=True),
            sa.Column('interval_end', sa.DateTime(timezone=True), nullable=True),
            sa.Column('coverage_complete', sa.Boolean(), nullable=True),
            sa.Column('checkpoint_before', sa.DateTime(timezone=True), nullable=True),
            sa.Column('checkpoint_after', sa.DateTime(timezone=True), nullable=True),
            sa.Column('continuation', JSONB(), nullable=True),
            sa.Column('counts', JSONB(), nullable=True),
            sa.Column('item_count', sa.Integer(), nullable=True),
            sa.Column('duration_ms', sa.Integer(), nullable=True),
            sa.Column('error_code', sa.String(32), nullable=True),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('truncated_reason', sa.String(32), nullable=True),
            sa.Column('parse_partial', sa.Boolean(), server_default=sa.text('false'), nullable=False),
            sa.Column('diagnostics', JSONB(), nullable=True),
            sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('finished_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        )
        op.create_index('ix_collection_runs_provider_time', 'collection_runs', ['provider', 'finished_at'])
        op.create_index('ix_collection_runs_scope', 'collection_runs', ['scope_kind', 'scope_id', 'finished_at'])
        op.create_index('ix_collection_runs_status', 'collection_runs', ['status', 'finished_at'])

    # -- collection_checkpoints: fixed intervals, continuation, lease --------
    if not _has_table('collection_checkpoints'):
        op.create_table(
            'collection_checkpoints',
            sa.Column('provider', sa.String(40), nullable=False),
            sa.Column('scope_key', sa.Text(), nullable=False),
            sa.Column('interval_start', sa.DateTime(timezone=True), nullable=True),
            sa.Column('interval_end', sa.DateTime(timezone=True), nullable=True),
            sa.Column('coverage_through', sa.DateTime(timezone=True), nullable=True),
            sa.Column('coverage_unknown_before', sa.DateTime(timezone=True), nullable=True),
            sa.Column('continuation', JSONB(), nullable=True),
            sa.Column('version', sa.Integer(), server_default='0', nullable=False),
            sa.Column('lease_owner', sa.Text(), nullable=True),
            sa.Column('lease_until', sa.DateTime(timezone=True), nullable=True),
            sa.Column('last_attempt_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('consecutive_failures', sa.Integer(), server_default='0', nullable=False),
            sa.Column('last_error_code', sa.String(32), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
            sa.PrimaryKeyConstraint('provider', 'scope_key'),
        )

    # -- rejected_candidates: the early-gate ledger (work package 19) -------
    if not _has_table('rejected_candidates'):
        op.create_table(
            'rejected_candidates',
            sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column('canonical_url', sa.Text(), nullable=False),
            sa.Column('group_id', sa.Integer(), nullable=False),
            sa.Column('gate_version', sa.String(64), nullable=False),
            sa.Column('score', sa.Float(), nullable=True),
            sa.Column('threshold', sa.Float(), nullable=True),
            sa.Column('evaluated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
            sa.Column('hits', sa.Integer(), server_default='0', nullable=False),
            sa.UniqueConstraint('canonical_url', 'group_id', name='uq_rejected_candidates_url_group'),
        )
        op.create_index('ix_rejected_candidates_evaluated', 'rejected_candidates', ['evaluated_at'])

    # -- observations and aliases (work packages 4, 8, 30) -------------------
    if not _has_table('article_observations'):
        op.create_table(
            'article_observations',
            sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column('article_uri', sa.Text(), sa.ForeignKey('articles.uri', ondelete='CASCADE'), nullable=False),
            sa.Column('provider', sa.String(40), nullable=False),
            sa.Column('external_id', sa.Text(), nullable=True),
            sa.Column('observation_key', sa.Text(), nullable=False),
            sa.Column('url', sa.Text(), nullable=True),
            sa.Column('content_kind', sa.String(16), nullable=True),
            sa.Column('truncated', sa.Boolean(), nullable=True),
            sa.Column('extraction_method', sa.String(32), nullable=True),
            sa.Column('published_at_raw', sa.Text(), nullable=True),
            sa.Column('observed_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
            sa.Column('payload', JSONB(), nullable=True),
            sa.UniqueConstraint('observation_key', name='uq_article_observations_key'),
        )
        op.create_index('ix_article_observations_article', 'article_observations', ['article_uri'])

    if not _has_table('article_url_aliases'):
        op.create_table(
            'article_url_aliases',
            sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column('article_uri', sa.Text(), sa.ForeignKey('articles.uri', ondelete='CASCADE'), nullable=False),
            sa.Column('url', sa.Text(), nullable=False),
            sa.Column('canonical_url', sa.Text(), nullable=False),
            sa.Column('registry_version', sa.String(32), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
            sa.UniqueConstraint('url', name='uq_article_url_aliases_url'),
        )
        op.create_index('ix_article_url_aliases_canonical', 'article_url_aliases', ['canonical_url'])
        op.create_index('ix_article_url_aliases_article', 'article_url_aliases', ['article_uri'])

    # -- pending_feed_entries: durable batch for long feeds (2, 16) ---------
    if not _has_table('pending_feed_entries'):
        op.create_table(
            'pending_feed_entries',
            sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column('feed_id', sa.Integer(), sa.ForeignKey('rss_feeds.id', ondelete='CASCADE'), nullable=False),
            sa.Column('entry_key', sa.Text(), nullable=False),
            sa.Column('payload', JSONB(), nullable=False),
            sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
            sa.Column('last_error', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
            sa.UniqueConstraint('feed_id', 'entry_key', name='uq_pending_feed_entries'),
        )


def downgrade():
    for table in ('pending_feed_entries', 'article_url_aliases', 'article_observations',
                  'rejected_candidates', 'collection_checkpoints', 'collection_runs'):
        op.execute(f"DROP TABLE IF EXISTS {table}")
    op.execute("DROP INDEX IF EXISTS ix_articles_first_seen")
    op.execute("DROP INDEX IF EXISTS ix_articles_quarantine")
    op.execute("DROP INDEX IF EXISTS ix_articles_canonical_url")
    for col in ('published_at_raw', 'publication_date_precision', 'date_provenance', 'source_indexed_at',
                'first_seen_at', 'last_seen_at', 'future_date_flag', 'content_kind', 'extraction_status',
                'identity_method', 'canonical_url', 'record_type', 'enrichment_block_reason',
                'enrichment_attempts'):
        if _has_column('articles', col):
            op.drop_column('articles', col)
    op.execute("DROP INDEX IF EXISTS ix_rss_feeds_polling_status")
    for col in ('consecutive_error_count', 'polling_status', 'first_failed_at', 'last_failed_at',
                'next_poll_at', 'last_attempt_at', 'last_success_at', 'coverage_through', 'etag',
                'last_modified', 'parse_partial_count', 'pending_batch', 'needs_attention_reason'):
        if _has_column('rss_feeds', col):
            op.drop_column('rss_feeds', col)
