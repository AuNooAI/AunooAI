"""Swiss Election Watch: second scope (topic column) and social sources

Revision ID: sd_002
Revises: sd_001
Create Date: 2026-09-16

Two changes that go together:

1. `topic` on sd_extractions and sd_narratives, so the module can carry more
   than one watch. The first sibling is "European Election Interference" —
   Moldova, Bulgaria, Belarus, Kremlin technique — which is the playbook that
   gets aimed at Switzerland in 2027. Keeping it in the Swiss topic would mean
   loosening the Swiss on_topic rule and dragging the noise back in.

2. Social handles in sd_sources. A Bluesky handle IS a domain (pssuisse.ch,
   mediasch.bsky.social), so the existing domain->tier lookup works on social
   posts unchanged once the handle is used as the domain.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'sd_002'
down_revision: Union[str, None] = 'sd_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SWISS = "Swiss Federal Elections 2027 Disinfo Monitoring"
EUROPE = "European Election Interference"

# Bluesky handles seen on the Swiss topic, tiered by what the account is.
SOCIAL_SOURCES = [
    ('pssuisse.ch', 'SP Schweiz (Bluesky)', 'party', 'fr'),
    ('svp.ch', 'SVP (Bluesky)', 'party', 'de'),
    ('mediasch.bsky.social', 'Swiss media aggregator (Bluesky)', 'mainstream', 'fr'),
    ('blickmedia.bsky.social', 'Blick (Bluesky)', 'mainstream', 'de'),
    ('cyberveille-ch.bsky.social', 'Cyberveille CH (Bluesky)', 'institution', 'fr'),
]

# Trackers that carry European interference reporting, moved to the new scope.
EUROPE_SOURCES = [
    ('euvsdisinfo.eu', 'EUvsDisinfo', 'research', 'en'),
    ('dfrlab.org', 'DFRLab', 'research', 'en'),
    ('disinfo.eu', 'EU DisinfoLab', 'research', 'en'),
    ('hybridcoe.fi', 'Hybrid CoE', 'research', 'en'),
    ('isdglobal.org', 'ISD', 'research', 'en'),
]

EUROPE_TARGETS = [
    ('vote', 'Moldovan parliamentary elections', ['Moldova', 'Chisinau']),
    ('vote', 'Bulgarian elections', ['Bulgaria', 'Sofia']),
    ('vote', 'German federal politics', ['Bundestag', 'AfD']),
    ('vote', 'French elections', ['France', 'Assemblée nationale']),
    ('vote', 'European Parliament elections', ['European Parliament', 'EP elections']),
    ('institution', 'European Commission', ['EU Commission', 'Brussels']),
    ('institution', 'European External Action Service', ['EEAS', 'East StratCom']),
]


def upgrade() -> None:
    for table in ('sd_extractions', 'sd_narratives', 'sd_narrative_articles', 'sd_briefs'):
        op.add_column(table, sa.Column('topic', sa.Text(), nullable=True))
        op.execute(f"UPDATE {table} SET topic = '{SWISS}' WHERE topic IS NULL")
        op.alter_column(table, 'topic', nullable=False,
                        server_default=SWISS)
    op.create_index('ix_sd_extractions_topic', 'sd_extractions', ['topic'])
    op.create_index('ix_sd_narratives_topic', 'sd_narratives', ['topic'])
    op.create_index('ix_sd_narrative_articles_topic', 'sd_narrative_articles', ['topic'])

    # A schedule belongs to a scope too.
    op.add_column('sd_schedules', sa.Column('topic', sa.Text(), nullable=True))
    op.execute(f"UPDATE sd_schedules SET topic = '{SWISS}' WHERE topic IS NULL")

    conn = op.get_bind()
    for domain, name, tier, lang in SOCIAL_SOURCES + EUROPE_SOURCES:
        conn.execute(sa.text(
            "INSERT INTO sd_sources (domain, name, tier, language, seeded) "
            "VALUES (:d, :n, :t, :l, true) ON CONFLICT (domain) DO UPDATE "
            "SET tier = EXCLUDED.tier, name = COALESCE(sd_sources.name, EXCLUDED.name)"),
            {"d": domain, "n": name, "t": tier, "l": lang})
    for ttype, name, aliases in EUROPE_TARGETS:
        conn.execute(sa.text(
            "INSERT INTO sd_targets (type, name, aliases, seeded) VALUES (:t, :n, :a, true) "
            "ON CONFLICT ON CONSTRAINT uq_sd_target DO NOTHING"),
            {"t": ttype, "n": name, "a": aliases})
    conn.execute(sa.text(
        "INSERT INTO sd_schedules (name, topic, batch_size, model, schedule_enabled, "
        "schedule_type, schedule_interval, schedule_unit) VALUES "
        "(:n, :t, 50, 'gpt-5.4-mini', true, 'interval', 4, 'hours')"),
        {"n": "European interference watch", "t": EUROPE})


def downgrade() -> None:
    op.execute("DELETE FROM sd_schedules WHERE topic = :t".replace(":t", f"'{EUROPE}'"))
    op.drop_column('sd_schedules', 'topic')
    op.drop_index('ix_sd_narrative_articles_topic', table_name='sd_narrative_articles')
    op.drop_index('ix_sd_narratives_topic', table_name='sd_narratives')
    op.drop_index('ix_sd_extractions_topic', table_name='sd_extractions')
    for table in ('sd_briefs', 'sd_narrative_articles', 'sd_narratives', 'sd_extractions'):
        op.drop_column(table, 'topic')
