"""add source_topics to forecast_topic_metadata

Revision ID: fa_011
Revises: fa_010
Create Date: 2026-05-27 22:30:00.000000

A tracked topic's deck name is now decoupled from the article ``topic`` tag
(the Add-Topic wizard lets an analyst name "Quantum Advantage" while the
seed articles are tagged "Quantum Computing"). ``source_topics`` records
which existing corpus topics back the tracked topic so downstream consumers
— principally the forecast assessment's post-forecast article window — can
look up the real corpus instead of the (untagged) deck name.

NULL/empty means "no explicit sources": consumers fall back to an exact
match on the deck name, preserving prior behaviour for topics whose name
already matches the article tag.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'fa_011'
down_revision: Union[str, None] = 'fa_010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'forecast_topic_metadata',
        sa.Column('source_topics', postgresql.JSONB(astext_type=sa.Text()),
                  nullable=True),
    )


def downgrade() -> None:
    op.drop_column('forecast_topic_metadata', 'source_topics')
