"""Add auspex_saved_snippets table for saving chat text selections

Revision ID: auspex_snippets_001
Revises: None
Create Date: 2024-12-18
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'auspex_snippets_001'
down_revision = None
branch_labels = ('auspex_snippets',)
depends_on = None


def upgrade() -> None:
    # Create auspex_saved_snippets table
    op.create_table(
        'auspex_saved_snippets',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Text(), nullable=True),  # Can be null for anonymous sessions
        sa.Column('chat_id', sa.Integer(), nullable=False),
        sa.Column('message_id', sa.Integer(), nullable=True),  # Optional link to specific message
        sa.Column('selected_text', sa.Text(), nullable=False),
        sa.Column('context_before', sa.Text(), nullable=True),  # ~100 chars before selection
        sa.Column('context_after', sa.Text(), nullable=True),   # ~100 chars after selection
        sa.Column('note', sa.Text(), nullable=True),            # User's optional note
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    )

    # Create indexes for faster lookups
    op.create_index('ix_auspex_snippets_user_id', 'auspex_saved_snippets', ['user_id'])
    op.create_index('ix_auspex_snippets_chat_id', 'auspex_saved_snippets', ['chat_id'])
    op.create_index('ix_auspex_snippets_created_at', 'auspex_saved_snippets', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_auspex_snippets_created_at', table_name='auspex_saved_snippets')
    op.drop_index('ix_auspex_snippets_chat_id', table_name='auspex_saved_snippets')
    op.drop_index('ix_auspex_snippets_user_id', table_name='auspex_saved_snippets')
    op.drop_table('auspex_saved_snippets')
