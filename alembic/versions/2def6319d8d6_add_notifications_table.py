"""add_notifications_table

Revision ID: 2def6319d8d6
Revises: 4b906d7c45c4
Create Date: 2025-11-08 11:34:24.476351

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2def6319d8d6'
down_revision: Union[str, None] = '4b906d7c45c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create notifications table
    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.Text(), nullable=True),  # NULL for system-wide notifications, references users.username
        sa.Column('type', sa.String(length=50), nullable=False),  # e.g., 'evaluation_complete', 'article_analysis', 'system'
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('link', sa.String(length=500), nullable=True),  # URL to navigate to when clicked
        sa.Column('read', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['username'], ['users.username'], ondelete='CASCADE')
    )

    # Create indexes for performance
    op.create_index('ix_notifications_username', 'notifications', ['username'])
    op.create_index('ix_notifications_read', 'notifications', ['read'])
    op.create_index('ix_notifications_created_at', 'notifications', ['created_at'])
    op.create_index('ix_notifications_username_read', 'notifications', ['username', 'read'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_notifications_username_read', 'notifications')
    op.drop_index('ix_notifications_created_at', 'notifications')
    op.drop_index('ix_notifications_read', 'notifications')
    op.drop_index('ix_notifications_username', 'notifications')

    # Drop table
    op.drop_table('notifications')
