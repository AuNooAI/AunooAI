"""add signal reports and extend signal_instructions

Revision ID: sr_001
Revises: ks_001
Create Date: 2025-12-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'sr_001'
down_revision: Union[str, None] = 'ks_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add report generation columns to signal_instructions
    op.add_column('signal_instructions',
        sa.Column('generate_report', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('signal_instructions',
        sa.Column('report_prompt', sa.Text(), nullable=True))
    op.add_column('signal_instructions',
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    # Add reasoning column to signal_alerts
    op.add_column('signal_alerts',
        sa.Column('reasoning', sa.Text(), nullable=True))

    # Create saved_signal_reports table
    op.create_table(
        'saved_signal_reports',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('instruction_id', sa.Integer(), nullable=True),
        sa.Column('instruction_name', sa.Text(), nullable=False),
        sa.Column('topic', sa.Text(), nullable=True),
        sa.Column('username', sa.Text(), nullable=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),

        # Report content
        sa.Column('report_prompt', sa.Text(), nullable=True),
        sa.Column('report_content', sa.Text(), nullable=True),

        # Data context
        sa.Column('alerts_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('article_uris', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('articles_used', sa.Integer(), nullable=True),

        # Metadata
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('model_used', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),

        # Constraints
        sa.ForeignKeyConstraint(['instruction_id'], ['signal_instructions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['username'], ['users.username'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('topic', 'username', 'name', name='uq_saved_signal_reports_topic_user_name')
    )

    # Create indexes
    op.create_index('idx_saved_signal_reports_topic', 'saved_signal_reports', ['topic'], unique=False)
    op.create_index('idx_saved_signal_reports_user', 'saved_signal_reports', ['username'], unique=False)
    op.create_index('idx_saved_signal_reports_instruction', 'saved_signal_reports', ['instruction_id'], unique=False)
    op.create_index('idx_saved_signal_reports_created', 'saved_signal_reports', ['created_at'], unique=False)


def downgrade() -> None:
    # Drop saved_signal_reports indexes
    op.drop_index('idx_saved_signal_reports_created', table_name='saved_signal_reports')
    op.drop_index('idx_saved_signal_reports_instruction', table_name='saved_signal_reports')
    op.drop_index('idx_saved_signal_reports_user', table_name='saved_signal_reports')
    op.drop_index('idx_saved_signal_reports_topic', table_name='saved_signal_reports')

    # Drop saved_signal_reports table
    op.drop_table('saved_signal_reports')

    # Remove columns from signal_alerts
    op.drop_column('signal_alerts', 'reasoning')

    # Remove columns from signal_instructions
    op.drop_column('signal_instructions', 'config')
    op.drop_column('signal_instructions', 'report_prompt')
    op.drop_column('signal_instructions', 'generate_report')
