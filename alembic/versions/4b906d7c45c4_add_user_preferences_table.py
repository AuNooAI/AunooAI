"""add_user_preferences_table

Revision ID: 4b906d7c45c4
Revises: 47bbb2e52c81
Create Date: 2025-11-06 18:45:15.155419

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4b906d7c45c4'
down_revision: Union[str, None] = '47bbb2e52c81'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create user_preferences table
    op.create_table(
        'user_preferences',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.Text(), nullable=False),
        sa.Column('preference_key', sa.String(255), nullable=False),
        sa.Column('config_value', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['username'], ['users.username'], ondelete='CASCADE'),
        sa.UniqueConstraint('username', 'preference_key', name='uq_user_preference_key')
    )

    # Create index on username for faster lookups
    op.create_index('ix_user_preferences_username', 'user_preferences', ['username'])


def downgrade() -> None:
    # Drop index first
    op.drop_index('ix_user_preferences_username', table_name='user_preferences')

    # Drop table
    op.drop_table('user_preferences')
