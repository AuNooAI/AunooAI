"""extracted_events: one record per real-world event

The extractor writes one row per article. Four rows described one Sanofi
deal with three different amounts, and one of four Taylor & Francis rows
said a separation review was a completed separation (16 Oct 2026 review).
A reconciliation pass now merges the rows that report the same event:
the kept row gets the agreed wording, amount and a state (proposed,
agreed, completed ...), the others point at it through merged_into and
leave the deck.

Branches off rt_001_runtime_tables, which every Wiley site has applied.

Revision ID: ev_001_event_state
Revises: rt_001_runtime_tables
Create Date: 2026-10-16
"""
from alembic import op
import sqlalchemy as sa

revision = "ev_001_event_state"
down_revision = "rt_001_runtime_tables"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("extracted_events", sa.Column("event_state", sa.Text(), nullable=True))
    op.add_column("extracted_events", sa.Column("merged_into", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("extracted_events", "merged_into")
    op.drop_column("extracted_events", "event_state")
