"""extracted_events.date_basis: where the event date came from

The extractor stamped every event with whatever date it had, usually the
article's publication date, and the exports presented that as the date the
development happened (an award finalised on 16 September became a 7 October
event, 16 Oct 2026 review). The extractor now reports the development's own
date when the article states it, and says so: date_basis is "stated" (the
article gives the date), "inferred" (from the publication date plus
"yesterday" or "last week") or "article" (no date in the text; the
publication date stands in and the exports say "reported").

Revision ID: ev_002_date_basis
Revises: ev_001_event_state
Create Date: 2026-10-16
"""
from alembic import op
import sqlalchemy as sa

revision = "ev_002_date_basis"
down_revision = "ev_001_event_state"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("extracted_events", sa.Column("date_basis", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("extracted_events", "date_basis")
