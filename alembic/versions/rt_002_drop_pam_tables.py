"""Drop the PAM (Power, Attention & Money) tables

PAM was removed from the code on 14 Oct 2026 (commit 634f7f19); nothing reads or writes these
tables any more. Sites that still run the PAM code (wiley, wileytest on 15 Oct 2026) must not
apply this until their code has been updated past that removal.

Bugfixing's data was saved first: backups/pam_tables_test_20261015.sql.gz (pg_dump of the nine
tables). Downgrade cannot bring data back; restore that file with psql if it is ever needed.

Revision ID: rt_002_drop_pam_tables
Revises: rt_001_runtime_tables
Create Date: 2026-10-15
"""
from alembic import op

revision = "rt_002_drop_pam_tables"
down_revision = "rt_001_runtime_tables"
branch_labels = None
depends_on = None

PAM_TABLES = (
    "pam_analysis_runs", "pam_article_datasets", "pam_entities", "pam_financial_events",
    "pam_metrics_timeseries", "pam_pillar_queries", "pam_regulatory_events",
    "pam_saved_dashboards", "pam_trend_snapshots",
)


def upgrade():
    op.execute("DROP TABLE IF EXISTS " + ", ".join(PAM_TABLES))


def downgrade():
    # The tables and their data can't be rebuilt from here. Restore the pg_dump named in the
    # docstring if they are ever needed again.
    pass
