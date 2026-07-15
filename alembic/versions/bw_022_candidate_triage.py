"""Agent triage columns on bw_incident_enrichment_candidates.

Assistive triage (user-confirmed 2026-07-15): the enrichment agent scores
each staged candidate against the incident, auto-DISMISSES clear noise
(state='dismissed', decided_by='agent:triage' — candidates table only), and
marks high-confidence ones recommendation='attach' for a one-click human
accept. Locker writes stay human-gated.

ADD COLUMN IF NOT EXISTS so the same file applies cleanly on all tenants.

Revision ID: bw_022_candidate_triage
Revises: bw_021_backfill_embedding_meta
Create Date: 2026-07-15
"""
from alembic import op

revision = 'bw_022_candidate_triage'
down_revision = 'bw_021_backfill_embedding_meta'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE bw_incident_enrichment_candidates"
               " ADD COLUMN IF NOT EXISTS triage_score DOUBLE PRECISION")
    op.execute("ALTER TABLE bw_incident_enrichment_candidates"
               " ADD COLUMN IF NOT EXISTS triage_rationale TEXT")
    op.execute("ALTER TABLE bw_incident_enrichment_candidates"
               " ADD COLUMN IF NOT EXISTS recommendation TEXT")


def downgrade():
    op.execute("ALTER TABLE bw_incident_enrichment_candidates DROP COLUMN IF EXISTS recommendation")
    op.execute("ALTER TABLE bw_incident_enrichment_candidates DROP COLUMN IF EXISTS triage_rationale")
    op.execute("ALTER TABLE bw_incident_enrichment_candidates DROP COLUMN IF EXISTS triage_score")
