"""Add auspex research tables

Revision ID: auspex_enhance_001
Revises: 9c7373d1f370
Create Date: 2025-11-25

This migration adds tables for:
- Deep research session tracking
- Tool usage analytics
- Search routing analytics
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision = 'auspex_enhance_001'
down_revision = '9c7373d1f370'
branch_labels = None
depends_on = None


def upgrade():
    # Research sessions table
    # NOTE: Includes username for ownership tracking (security requirement)
    # Uses username (Text) as FK since users table has username as PK
    op.create_table(
        'auspex_research_sessions',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('chat_id', sa.Integer, sa.ForeignKey('auspex_chats.id', ondelete='CASCADE'), nullable=True),
        sa.Column('username', sa.Text, sa.ForeignKey('users.username', ondelete='CASCADE'), nullable=False),
        sa.Column('query', sa.Text, nullable=False),
        sa.Column('topic', sa.String(255), nullable=False),
        sa.Column('status', sa.String(50), server_default='pending', nullable=False),
        sa.Column('objectives', postgresql.JSONB, nullable=True),
        sa.Column('findings', postgresql.JSONB, nullable=True),
        sa.Column('report', sa.Text, nullable=True),
        sa.Column('metadata', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime, nullable=True),
    )
    # Add indexes for common queries
    op.create_index('ix_auspex_research_sessions_username', 'auspex_research_sessions', ['username'])
    op.create_index('ix_auspex_research_sessions_chat_id', 'auspex_research_sessions', ['chat_id'])
    op.create_index('ix_auspex_research_sessions_status', 'auspex_research_sessions', ['status'])
    op.create_index('ix_auspex_research_sessions_created_at', 'auspex_research_sessions', ['created_at'])

    # Tool usage tracking
    op.create_table(
        'auspex_tool_usage',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('chat_id', sa.Integer, sa.ForeignKey('auspex_chats.id', ondelete='SET NULL'), nullable=True),
        sa.Column('tool_name', sa.String(100), nullable=False),
        sa.Column('tool_version', sa.String(20), nullable=True),
        sa.Column('parameters', postgresql.JSONB, nullable=True),
        sa.Column('result_summary', postgresql.JSONB, nullable=True),
        sa.Column('execution_ms', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index('ix_auspex_tool_usage_tool_name', 'auspex_tool_usage', ['tool_name'])
    op.create_index('ix_auspex_tool_usage_created_at', 'auspex_tool_usage', ['created_at'])

    # Search routing analytics
    op.create_table(
        'auspex_search_routing',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('query', sa.Text, nullable=False),
        sa.Column('topic', sa.String(255), nullable=True),
        sa.Column('recommended_source', sa.String(50), nullable=False),
        sa.Column('actual_source', sa.String(50), nullable=False),
        sa.Column('confidence', sa.Float, nullable=True),
        sa.Column('signals', postgresql.JSONB, nullable=True),
        sa.Column('result_quality', sa.Float, nullable=True),  # For feedback loop
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index('ix_auspex_search_routing_created_at', 'auspex_search_routing', ['created_at'])
    op.create_index('ix_auspex_search_routing_recommended_source', 'auspex_search_routing', ['recommended_source'])


def downgrade():
    # Drop indexes first
    op.drop_index('ix_auspex_search_routing_recommended_source', table_name='auspex_search_routing')
    op.drop_index('ix_auspex_search_routing_created_at', table_name='auspex_search_routing')
    op.drop_index('ix_auspex_tool_usage_created_at', table_name='auspex_tool_usage')
    op.drop_index('ix_auspex_tool_usage_tool_name', table_name='auspex_tool_usage')
    op.drop_index('ix_auspex_research_sessions_created_at', table_name='auspex_research_sessions')
    op.drop_index('ix_auspex_research_sessions_status', table_name='auspex_research_sessions')
    op.drop_index('ix_auspex_research_sessions_chat_id', table_name='auspex_research_sessions')
    op.drop_index('ix_auspex_research_sessions_username', table_name='auspex_research_sessions')

    # Drop tables
    op.drop_table('auspex_search_routing')
    op.drop_table('auspex_tool_usage')
    op.drop_table('auspex_research_sessions')
