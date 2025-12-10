"""add keyword_suggestions table for relevance feedback loop

Revision ID: ks_001
Revises: eb_001
Create Date: 2025-12-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'ks_001'
down_revision: Union[str, None] = 'eb_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'keyword_suggestions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('keyword_id', sa.Integer(), nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('suggestion_type', sa.String(20), nullable=False),  # 'replace', 'add', 'exclude'
        sa.Column('suggested_keyword', sa.Text(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('status', sa.String(20), server_default='pending', nullable=False),  # 'pending', 'approved', 'rejected', 'expired'
        sa.Column('analyzed_articles', sa.Integer(), nullable=True),
        sa.Column('avg_relevance_at_creation', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_by', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['keyword_id'], ['monitored_keywords.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['group_id'], ['keyword_groups.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("suggestion_type IN ('replace', 'add', 'exclude')", name='ck_suggestion_type'),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected', 'expired')", name='ck_suggestion_status'),
    )
    op.create_index('idx_keyword_suggestions_status', 'keyword_suggestions', ['status'], unique=False)
    op.create_index('idx_keyword_suggestions_keyword', 'keyword_suggestions', ['keyword_id'], unique=False)
    op.create_index('idx_keyword_suggestions_group', 'keyword_suggestions', ['group_id'], unique=False)
    op.create_index('idx_keyword_suggestions_created', 'keyword_suggestions', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_keyword_suggestions_created', table_name='keyword_suggestions')
    op.drop_index('idx_keyword_suggestions_group', table_name='keyword_suggestions')
    op.drop_index('idx_keyword_suggestions_keyword', table_name='keyword_suggestions')
    op.drop_index('idx_keyword_suggestions_status', table_name='keyword_suggestions')
    op.drop_table('keyword_suggestions')
