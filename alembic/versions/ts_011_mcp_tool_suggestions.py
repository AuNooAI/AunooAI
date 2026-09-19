"""mcp_tool_suggestions — what the tool-suggestion pre-pass recommended

Revision ID: ts_011
Revises: ts_010
Create Date: 2026-09-19

One row per call to the ``suggest_tool`` MCP tool: who asked, the request
text, whether the decision model thought a tool was needed at all, the three
tools it shortlisted with their fit probabilities, and the one it suggested
(or none). Joined against the metered tool-call log by client and time, it
shows whether the assistant then called the suggested tool, which is the
measurement the skill-suggestion recipe reports. Nothing reads this table on
the request path.
"""
from alembic import op
import sqlalchemy as sa

revision = 'ts_011'
down_revision = 'ts_010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'mcp_tool_suggestions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('username', sa.Text(), nullable=True, index=True),
        sa.Column('api_key_id', sa.Integer(), nullable=True),
        sa.Column('request', sa.Text(), nullable=False),
        sa.Column('needs_tool', sa.Float(), nullable=True),
        sa.Column('needs_site_data', sa.Float(), nullable=True),
        sa.Column('shortlist', sa.JSON(), nullable=True),           # [{tool, p_rank, p_fit}] top three from call 1, re-read in call 2
        sa.Column('suggested', sa.Text(), nullable=True),           # tool name or NULL for "none"
        sa.Column('suggested_p', sa.Float(), nullable=True),
        sa.Column('jev_model', sa.Text(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
    )


def downgrade() -> None:
    op.drop_table('mcp_tool_suggestions')
