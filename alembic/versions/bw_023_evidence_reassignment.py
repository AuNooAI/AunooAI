"""Evidence reassignment marker.

Case splits can only COPY evidence (the locker is append-only and
hash-chained), so the source case keeps off-scope items forever and its
reports re-list them. ``reassigned_to`` marks an item as belonging to another
case: the row, its content, and its chain hashes are untouched (the marker is
case-organization metadata, not captured content), but the case view and
reports group it out of the working evidence list.

Revision ID: bw_023_evidence_reassignment
Revises: bw_022_candidate_triage
Create Date: 2026-07-15
"""
from alembic import op

revision = 'bw_023_evidence_reassignment'
down_revision = 'bw_022_candidate_triage'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE bw_incident_evidence"
               " ADD COLUMN IF NOT EXISTS reassigned_to INTEGER")


def downgrade():
    op.execute("ALTER TABLE bw_incident_evidence DROP COLUMN IF EXISTS reassigned_to")
