"""Add policy tracker narratives and imports tables

Revision ID: pt_002
Revises: pt_001
Create Date: 2026-01-20

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'pt_002'
down_revision = 'pt_001'
branch_labels = None
depends_on = None


def upgrade():
    # Create policy_tracker_narratives table - stores generated narrative analyses
    op.create_table(
        'policy_tracker_narratives',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('topic', sa.Text(), nullable=False),
        sa.Column('narrative', sa.Text(), nullable=False),
        sa.Column('data_summary', postgresql.JSONB(), nullable=True),
        sa.Column('days_back', sa.Integer(), nullable=True),
        sa.Column('date_range_start', sa.Date(), nullable=True),
        sa.Column('date_range_end', sa.Date(), nullable=True),
        sa.Column('generated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('idx_policy_tracker_narratives_topic', 'policy_tracker_narratives', ['topic'])
    op.create_index('idx_policy_tracker_narratives_generated_at', 'policy_tracker_narratives', ['generated_at'])

    # Create policy_tracker_imports table - tracks CSV/URL import operations
    op.create_table(
        'policy_tracker_imports',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('topic', sa.Text(), nullable=False),
        sa.Column('import_type', sa.Text(), nullable=False),  # 'file_upload' or 'url_import'
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('filename', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), server_default='pending', nullable=False),  # pending, processing, completed, failed
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rows_processed', sa.Integer(), server_default='0', nullable=False),
        sa.Column('articles_created', sa.Integer(), server_default='0', nullable=False),
        sa.Column('articles_updated', sa.Integer(), server_default='0', nullable=False),
        sa.Column('categories_added', sa.Integer(), server_default='0', nullable=False),
        sa.Column('errors', sa.Integer(), server_default='0', nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('run_llm_classification', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('narrative_id', sa.Integer(), sa.ForeignKey('policy_tracker_narratives.id', ondelete='SET NULL'), nullable=True),
    )
    op.create_index('idx_policy_tracker_imports_topic', 'policy_tracker_imports', ['topic'])
    op.create_index('idx_policy_tracker_imports_status', 'policy_tracker_imports', ['status'])
    op.create_index('idx_policy_tracker_imports_started_at', 'policy_tracker_imports', ['started_at'])


def downgrade():
    op.drop_table('policy_tracker_imports')
    op.drop_table('policy_tracker_narratives')
