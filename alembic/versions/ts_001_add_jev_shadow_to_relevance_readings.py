"""Add TypeSafe Jev shadow columns to relevance_confidence_readings

Revision ID: ts_001
Revises: rel_001, mm_031
Create Date: 2026-09-19

Three nullable columns so the hybrid relevance cascade can record what the
TypeSafe Jev decision model would have said, next to the score that actually
decided. Nothing reads them on the decision path; they exist so a week of
readings can be compared against user_relevance_feedback before Jev is
allowed to take the Tier-4 decision.

    jev_on_topic   Noul probability (0-1) that the article is about the topic
    jev_score      Score answer normalised to 0-1 over the prompt's three bands
                   (unrelated / secondary mention / primarily about)
    jev_confidence how peaked the Score distribution was (0-1)

This revision also merges the two open heads (rel_001 and mm_031) so
``alembic upgrade head`` works again on this tenant.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'ts_001'
down_revision = ('rel_001', 'mm_031')
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('relevance_confidence_readings', sa.Column('jev_on_topic', sa.Float(), nullable=True))
    op.add_column('relevance_confidence_readings', sa.Column('jev_score', sa.Float(), nullable=True))
    op.add_column('relevance_confidence_readings', sa.Column('jev_confidence', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('relevance_confidence_readings', 'jev_confidence')
    op.drop_column('relevance_confidence_readings', 'jev_score')
    op.drop_column('relevance_confidence_readings', 'jev_on_topic')
