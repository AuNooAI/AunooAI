"""Add saved_incidents and saved_narratives tables

Revision ID: nf_004
Revises: nf_003
Create Date: 2026-01-12

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'nf_004'
down_revision = 'nf_003'
branch_labels = None
depends_on = None


def upgrade():
    # Create saved_incidents table - stores full incident data for persistence
    op.create_table(
        'saved_incidents',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('incident_name', sa.Text(), nullable=False),
        sa.Column('topic', sa.Text(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('incident_data', postgresql.JSONB(), nullable=False),
        sa.Column('saved_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.UniqueConstraint('incident_name', 'topic', 'user_id', name='uq_saved_incident_name_topic_user')
    )
    op.create_index('idx_saved_incidents_topic', 'saved_incidents', ['topic'])
    op.create_index('idx_saved_incidents_user', 'saved_incidents', ['user_id'])
    op.create_index('idx_saved_incidents_saved_at', 'saved_incidents', ['saved_at'])

    # Create saved_narratives table - stores full narrative data for persistence
    op.create_table(
        'saved_narratives',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('narrative_name', sa.Text(), nullable=False),
        sa.Column('topic', sa.Text(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('narrative_data', postgresql.JSONB(), nullable=False),
        sa.Column('saved_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.UniqueConstraint('narrative_name', 'topic', 'user_id', name='uq_saved_narrative_name_topic_user')
    )
    op.create_index('idx_saved_narratives_topic', 'saved_narratives', ['topic'])
    op.create_index('idx_saved_narratives_user', 'saved_narratives', ['user_id'])
    op.create_index('idx_saved_narratives_saved_at', 'saved_narratives', ['saved_at'])


def downgrade():
    op.drop_table('saved_narratives')
    op.drop_table('saved_incidents')
