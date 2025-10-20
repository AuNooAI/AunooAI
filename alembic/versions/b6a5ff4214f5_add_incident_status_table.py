"""add_incident_status_table

Revision ID: b6a5ff4214f5
Revises: 1745b4f22f68
Create Date: 2025-10-20 17:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b6a5ff4214f5'
down_revision: Union[str, None] = '8eadb2079747'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create incident_status table
    op.create_table('incident_status',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('incident_name', sa.Text(), nullable=False),
        sa.Column('topic', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False, server_default='active'),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('incident_name', 'topic')
    )

    # Create signal_instructions table
    op.create_table('signal_instructions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('instruction', sa.Text(), nullable=False),
        sa.Column('topic', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='1'),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )

    # Create signal_alerts table
    op.create_table('signal_alerts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('article_uri', sa.Text(), nullable=False),
        sa.Column('instruction_id', sa.Integer(), nullable=False),
        sa.Column('instruction_name', sa.Text(), nullable=False),
        sa.Column('confidence', sa.REAL(), nullable=False),
        sa.Column('threat_level', sa.Text(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('detected_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('is_acknowledged', sa.Boolean(), server_default='0'),
        sa.Column('acknowledged_at', sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(['instruction_id'], ['signal_instructions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('article_uri', 'instruction_id')
    )


def downgrade() -> None:
    op.drop_table('signal_alerts')
    op.drop_table('signal_instructions')
    op.drop_table('incident_status')
