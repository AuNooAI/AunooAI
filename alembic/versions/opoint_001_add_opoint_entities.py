"""Add opoint_entities column to articles for Opoint entity/topic enrichment

Revision ID: opoint_001
Revises: dbc_001
Create Date: 2026-06-18

Adds:
- articles.opoint_entities (JSONB) — per-article entity/topic enrichment from the
  Opoint collector (organizations/people/locations tagged with Wikidata, Crunchbase,
  PermID, LEI and FIGI identifiers, plus topics and source country). This is the
  structured brand/competitor signal Opoint provides; it lives in its own column so
  the downstream LLM/bias enrichment never clobbers it.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'opoint_001'
down_revision = 'dbc_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'articles',
        sa.Column('opoint_entities', postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('articles', 'opoint_entities')
