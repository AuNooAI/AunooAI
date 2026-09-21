"""entity_identity_shadow: what connects a person to the company

Revision ID: ts_015
Revises: ts_014
Create Date: 2026-09-21

The shadow could tell an individual from a company account but not whether
the individual had anything to do with the company. On oviva it put ten
people in the person lane and only three had any connection: a coach and two
members. The rest had mentioned a brand once. These columns hold the answer
to the question that separates them.
"""
from alembic import op
import sqlalchemy as sa

revision = 'ts_015'
down_revision = 'ts_014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # not_a_person | none | employee | executive | customer | promoter | commentator
    op.add_column('entity_identity_shadow', sa.Column('jev_affiliation', sa.Text(), nullable=True))
    op.add_column('entity_identity_shadow', sa.Column('jev_affiliation_confidence', sa.Float(), nullable=True))
    # Whether the profile says so, rather than the reader inferring it.
    op.add_column('entity_identity_shadow', sa.Column('jev_affiliation_stated', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('entity_identity_shadow', 'jev_affiliation_stated')
    op.drop_column('entity_identity_shadow', 'jev_affiliation_confidence')
    op.drop_column('entity_identity_shadow', 'jev_affiliation')
