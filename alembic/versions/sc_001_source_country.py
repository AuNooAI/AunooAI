"""Publisher country registry, so a market topic can mean a country.

``keyword_groups.country`` has never filtered anything for the collectors that
matter. TheNewsAPI ignores ``locale`` on the endpoint we search, our own
firehose ignores it by design, and the only collector that honours ``country``
is out of credits. So country becomes a property of the publisher that we
resolve once and store, rather than a parameter we ask a vendor to respect.

``news_source_countries`` is the registry, keyed on the registrable domain.
``articles.source_country`` is the resolved code stamped on each row, with
``source_country_method`` recording which rung of the ladder answered so a
wrong code can be found rather than re-guessed.

Idempotent throughout: these trees have diverged and this migration is copied
between them with only its ``down_revision`` changed.

Revision ID: sc_001
"""
from alembic import op
import sqlalchemy as sa

revision = 'sc_001'
down_revision = 'ts_015'
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(name)


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table(table):
        return False
    return column in {c['name'] for c in insp.get_columns(table)}


def upgrade():
    if not _has_table('news_source_countries'):
        op.create_table(
            'news_source_countries',
            sa.Column('domain', sa.String(255), primary_key=True),
            # NULL is a real, cached answer: "we looked and could not tell".
            sa.Column('country', sa.String(2), nullable=True),
            # manual | tld | mediabias | model | model+ | unresolved
            sa.Column('method', sa.String(16), nullable=False,
                      server_default='unresolved'),
            sa.Column('resolver_version', sa.Integer(), nullable=False,
                      server_default=sa.text('1')),
            sa.Column('resolved_at', sa.TIMESTAMP(timezone=True),
                      server_default=sa.text('NOW()')),
            sa.Column('notes', sa.Text(), nullable=True),
        )
        op.create_index('ix_nsc_country', 'news_source_countries', ['country'])

    if not _has_column('articles', 'source_country'):
        op.add_column('articles', sa.Column('source_country', sa.String(2), nullable=True))
    if not _has_column('articles', 'source_country_method'):
        op.add_column('articles', sa.Column('source_country_method', sa.String(16), nullable=True))

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_articles_source_country "
        "ON articles (source_country) WHERE source_country IS NOT NULL"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_articles_source_country")
    if _has_column('articles', 'source_country_method'):
        op.drop_column('articles', 'source_country_method')
    if _has_column('articles', 'source_country'):
        op.drop_column('articles', 'source_country')
    if _has_table('news_source_countries'):
        op.drop_index('ix_nsc_country', table_name='news_source_countries')
        op.drop_table('news_source_countries')
