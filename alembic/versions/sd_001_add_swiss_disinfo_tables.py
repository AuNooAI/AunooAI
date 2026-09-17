"""Swiss election disinformation monitor: tables and seed rows

Revision ID: sd_001
Revises: mm_028
Create Date: 2026-09-15

One structured extraction per approved article of the Swiss election topic,
narratives matched across languages by embedding, outlets as actors with a
tier, pre-seeded targets, a schedules table on the GeoHotspots pattern, and
saved weekly briefs. See docs/SWISS_ELECTION_DISINFO_MONITOR_SPEC.md.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'sd_001'
down_revision: Union[str, None] = 'mm_028'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SEED_SOURCES = [
    # domain, name, tier, language
    ('de.rt.com', 'RT DE', 'state_media', 'de'),
    ('rt.com', 'RT', 'state_media', 'en'),
    ('sputniknews.com', 'Sputnik', 'state_media', 'en'),
    ('uncutnews.ch', 'Uncut-News', 'alt_media', 'de'),
    ('uncut-news.ch', 'Uncut-News', 'alt_media', 'de'),
    ('lesobservateurs.ch', 'Les Observateurs', 'alt_media', 'fr'),
    ('arretsurinfo.ch', 'Arrêt sur Info', 'alt_media', 'fr'),
    ('schweizerzeit.ch', 'Schweizerzeit', 'alt_media', 'de'),
    ('weltwoche.ch', 'Weltwoche', 'alt_media', 'de'),
    ('infosperber.ch', 'Infosperber', 'alt_media', 'de'),
    ('insideparadeplatz.ch', 'Inside Paradeplatz', 'alt_media', 'de'),
    ('journal21.ch', 'Journal21', 'mainstream', 'de'),
    ('republik.ch', 'Republik', 'mainstream', 'de'),
    ('nzz.ch', 'NZZ', 'mainstream', 'de'),
    ('srf.ch', 'SRF', 'mainstream', 'de'),
    ('rts.ch', 'RTS', 'mainstream', 'fr'),
    ('rsi.ch', 'RSI', 'mainstream', 'it'),
    ('swissinfo.ch', 'Swissinfo', 'mainstream', 'en'),
    ('bluewin.ch', 'bluewin', 'mainstream', 'de'),
    ('20min.ch', '20 Minuten', 'mainstream', 'de'),
    ('blick.ch', 'Blick', 'mainstream', 'de'),
    ('tagesanzeiger.ch', 'Tages-Anzeiger', 'mainstream', 'de'),
    ('letemps.ch', 'Le Temps', 'mainstream', 'fr'),
    ('tdg.ch', 'Tribune de Genève', 'mainstream', 'fr'),
    ('24heures.ch', '24 heures', 'mainstream', 'fr'),
    ('cdt.ch', 'Corriere del Ticino', 'mainstream', 'it'),
    ('woz.ch', 'WOZ', 'mainstream', 'de'),
    ('beobachter.ch', 'Beobachter', 'mainstream', 'de'),
    ('svp.ch', 'SVP', 'party', 'de'),
    ('sp-ps.ch', 'SP', 'party', 'de'),
    ('fdp.ch', 'FDP', 'party', 'de'),
    ('die-mitte.ch', 'Die Mitte', 'party', 'de'),
    ('gruene.ch', 'Grüne', 'party', 'de'),
    ('grunliberale.ch', 'GLP', 'party', 'de'),
    ('mimikama.org', 'Mimikama', 'fact_checker', 'de'),
    ('correctiv.org', 'Correctiv', 'fact_checker', 'de'),
    ('faktencheck.afp.com', 'AFP Faktencheck', 'fact_checker', 'de'),
    ('factuel.afp.com', 'AFP Factuel', 'fact_checker', 'fr'),
    ('euvsdisinfo.eu', 'EUvsDisinfo', 'research', 'en'),
    ('disinfo.eu', 'EU DisinfoLab', 'research', 'en'),
    ('dfrlab.org', 'DFRLab', 'research', 'en'),
    ('alliance4europe.eu', 'Alliance4Europe', 'research', 'en'),
    ('bellingcat.com', 'Bellingcat', 'research', 'en'),
    ('rsf-ch.ch', 'RSF Schweiz', 'research', 'de'),
    ('admin.ch', 'Swiss federal administration', 'institution', 'de'),
    ('parlament.ch', 'Swiss Parliament', 'institution', 'de'),
]

SEED_TARGETS = [
    # type, name, aliases
    ('vote', 'Neutrality initiative (27 Sep 2026)', ['Neutralitätsinitiative', 'initiative sur la neutralité', 'iniziativa sulla neutralità', 'neutrality initiative']),
    ('vote', 'Federal votes 29 Nov 2026', ['Abstimmung 29. November', 'votation 29 novembre']),
    ('vote', 'Federal Elections 2027', ['eidgenössische Wahlen 2027', 'élections fédérales 2027', 'elezioni federali 2027', 'Swiss federal elections']),
    ('policy', 'EU treaty package (Bilaterals III)', ['EU-Vertragspaket', 'Bilaterale III', 'paquet d''accords UE', 'EU package']),
    ('institution', 'Federal Council', ['Bundesrat', 'Conseil fédéral', 'Consiglio federale']),
    ('institution', 'Federal Chancellery', ['Bundeskanzlei', 'Chancellerie fédérale']),
    ('institution', 'Federal Intelligence Service', ['Nachrichtendienst des Bundes', 'NDB', 'SRC', 'Service de renseignement de la Confédération']),
    ('party', 'SVP', ['UDC', 'Schweizerische Volkspartei', 'Swiss People''s Party']),
    ('party', 'SP', ['PS', 'Sozialdemokratische Partei', 'Parti socialiste']),
    ('party', 'FDP', ['PLR', 'FDP.Die Liberalen', 'Les Libéraux-Radicaux']),
    ('party', 'Die Mitte', ['Le Centre', 'Il Centro']),
    ('party', 'Grüne', ['Les Vert-e-s', 'GPS', 'Greens']),
    ('party', 'GLP', ['PVL', 'Grünliberale', 'Vert''libéraux']),
    ('person', 'Karin Keller-Sutter', []),
    ('person', 'Guy Parmelin', []),
    ('person', 'Ignazio Cassis', []),
    ('person', 'Albert Rösti', []),
    ('person', 'Elisabeth Baume-Schneider', []),
    ('person', 'Beat Jans', []),
    ('person', 'Martin Pfister', []),
    ('person', 'Christoph Blocher', []),
    ('person', 'Marcel Dettling', []),
]


def upgrade() -> None:
    op.create_table(
        'sd_narratives',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('statement', sa.Text(), nullable=False),
        sa.Column('attribution', sa.String(40), nullable=True),
        sa.Column('attribution_confidence', sa.Float(), nullable=True),
        sa.Column('first_seen', sa.Date(), nullable=True),
        sa.Column('last_seen', sa.Date(), nullable=True),
        sa.Column('article_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('languages', postgresql.ARRAY(sa.String(8)), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # pgvector column: the sqlalchemy pgvector package is not installed in the
    # tenant venv, so the column is added with plain DDL. 768 matches
    # articles.embedding (vector_dims checked 2026-09-15).
    op.execute("ALTER TABLE sd_narratives ADD COLUMN embedding vector(768)")

    op.create_table(
        'sd_narrative_articles',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('narrative_id', sa.Integer(), sa.ForeignKey('sd_narratives.id', ondelete='CASCADE'), nullable=False),
        sa.Column('article_uri', sa.Text(), nullable=False),
        sa.Column('stance', sa.String(16), nullable=False),  # promotes | reports | debunks
        sa.Column('language', sa.String(8), nullable=True),
        sa.Column('source_domain', sa.String(255), nullable=True),
        sa.Column('source_tier', sa.String(32), nullable=True),
        sa.Column('article_date', sa.Date(), nullable=True),
        sa.Column('detected_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('narrative_id', 'article_uri', name='uq_sd_narrative_article'),
    )
    op.create_index('ix_sd_narrative_articles_narrative', 'sd_narrative_articles', ['narrative_id'])
    op.create_index('ix_sd_narrative_articles_date', 'sd_narrative_articles', ['article_date'])

    op.create_table(
        'sd_extractions',
        sa.Column('article_uri', sa.Text(), primary_key=True),
        sa.Column('language', sa.String(8), nullable=True),
        sa.Column('source_domain', sa.String(255), nullable=True),
        sa.Column('source_tier', sa.String(32), nullable=True),
        sa.Column('attribution', sa.String(40), nullable=True),
        sa.Column('attribution_confidence', sa.Float(), nullable=True),
        sa.Column('techniques', postgresql.ARRAY(sa.String(40)), server_default='{}', nullable=False),
        sa.Column('targets', postgresql.JSONB(), server_default='[]', nullable=False),
        sa.Column('narratives', postgresql.JSONB(), server_default='[]', nullable=False),
        sa.Column('fact_check', postgresql.JSONB(), nullable=True),
        sa.Column('response', postgresql.JSONB(), nullable=True),
        sa.Column('model', sa.String(100), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('article_date', sa.Date(), nullable=True),
        sa.Column('extracted_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_sd_extractions_date', 'sd_extractions', ['article_date'])

    op.create_table(
        'sd_sources',
        sa.Column('domain', sa.String(255), primary_key=True),
        sa.Column('name', sa.String(200), nullable=True),
        sa.Column('tier', sa.String(32), nullable=False, server_default='unknown'),
        sa.Column('language', sa.String(8), nullable=True),
        sa.Column('seeded', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('first_seen', sa.Date(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
    )

    op.create_table(
        'sd_targets',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('type', sa.String(20), nullable=False),  # vote | party | person | institution | policy
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('aliases', postgresql.ARRAY(sa.Text()), server_default='{}', nullable=False),
        sa.Column('seeded', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.UniqueConstraint('type', 'name', name='uq_sd_target'),
    )

    op.create_table(
        'sd_briefs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('brief_text', sa.Text(), nullable=False),
        sa.Column('sections', postgresql.JSONB(), nullable=True),
        sa.Column('narrative_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('article_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('days_back', sa.Integer(), server_default='7', nullable=False),
        sa.Column('model', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        'sd_schedules',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('batch_size', sa.Integer(), server_default='50', nullable=False),
        sa.Column('model', sa.String(100), server_default='gpt-5.4-mini', nullable=False),
        sa.Column('process_all', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('schedule_enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('schedule_type', sa.String(20), server_default='interval', nullable=True),
        sa.Column('schedule_interval', sa.Integer(), nullable=True),
        sa.Column('schedule_unit', sa.String(20), server_default='hours', nullable=True),
        sa.Column('schedule_time', sa.Time(), nullable=True),
        sa.Column('notify_on_complete', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_run_status', sa.String(20), nullable=True),
        sa.Column('last_run_error', sa.Text(), nullable=True),
        sa.Column('last_run_articles_processed', sa.Integer(), server_default='0', nullable=False),
        sa.Column('last_run_narratives_created', sa.Integer(), server_default='0', nullable=False),
        sa.Column('run_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_sd_schedules_next_run', 'sd_schedules', ['next_run_at'])

    conn = op.get_bind()
    for domain, name, tier, lang in SEED_SOURCES:
        conn.execute(sa.text(
            "INSERT INTO sd_sources (domain, name, tier, language, seeded) "
            "VALUES (:d, :n, :t, :l, true) ON CONFLICT (domain) DO NOTHING"),
            {"d": domain, "n": name, "t": tier, "l": lang})
    for ttype, name, aliases in SEED_TARGETS:
        conn.execute(sa.text(
            "INSERT INTO sd_targets (type, name, aliases, seeded) "
            "VALUES (:t, :n, :a, true) ON CONFLICT ON CONSTRAINT uq_sd_target DO NOTHING"),
            {"t": ttype, "n": name, "a": aliases})
    # One default schedule, every 2 hours, so the monitor runs without setup.
    conn.execute(sa.text(
        "INSERT INTO sd_schedules (name, batch_size, model, schedule_enabled, schedule_type, "
        "schedule_interval, schedule_unit) VALUES "
        "('Swiss election watch (default)', 50, 'gpt-5.4-mini', true, 'interval', 2, 'hours')"))


def downgrade() -> None:
    op.drop_index('ix_sd_schedules_next_run', table_name='sd_schedules')
    op.drop_table('sd_schedules')
    op.drop_table('sd_briefs')
    op.drop_table('sd_targets')
    op.drop_table('sd_sources')
    op.drop_index('ix_sd_extractions_date', table_name='sd_extractions')
    op.drop_table('sd_extractions')
    op.drop_index('ix_sd_narrative_articles_date', table_name='sd_narrative_articles')
    op.drop_index('ix_sd_narrative_articles_narrative', table_name='sd_narrative_articles')
    op.drop_table('sd_narrative_articles')
    op.drop_table('sd_narratives')
