"""LLM usage ledger table.

Every litellm call (Router, direct, bare-alias) gets one row via the global
callbacks in app/services/llm_usage_logger.py. Port of the saas
``llm_usage_log`` pattern; created 2026-07-16 after the untracked-Bedrock
bill surprise.

Revision ID: llm_usage_01
Revises: bw_023_evidence_reassignment
"""

from alembic import op
import sqlalchemy as sa

revision = "llm_usage_01"
down_revision = "bw_023_evidence_reassignment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_usage_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("use_case", sa.Text, nullable=False, server_default="unknown"),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("resolved_model", sa.Text, nullable=True),
        sa.Column("provider", sa.Text, nullable=True),
        sa.Column("prompt_tokens", sa.Integer, server_default="0"),
        sa.Column("completion_tokens", sa.Integer, server_default="0"),
        sa.Column("total_tokens", sa.Integer, server_default="0"),
        sa.Column("cost_usd", sa.Float, server_default="0"),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("status", sa.Text, server_default="success"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("idx_llm_usage_created", "llm_usage_log", ["created_at"])
    op.create_index("idx_llm_usage_use_case", "llm_usage_log", ["use_case"])
    op.create_index("idx_llm_usage_model", "llm_usage_log", ["resolved_model"])


def downgrade() -> None:
    op.drop_index("idx_llm_usage_model", table_name="llm_usage_log")
    op.drop_index("idx_llm_usage_use_case", table_name="llm_usage_log")
    op.drop_index("idx_llm_usage_created", table_name="llm_usage_log")
    op.drop_table("llm_usage_log")
