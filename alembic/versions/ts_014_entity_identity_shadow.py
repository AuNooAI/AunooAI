"""entity_identity_shadow — which company, if any, owns a social account

Revision ID: ts_014
Revises: ts_013
Create Date: 2026-09-21

Records what the TypeSafe Jev model thinks about an unmapped social account:
which of a code-chosen shortlist of companies owns it, whether it is a
company account at all, and whether the only evidence is a name resemblance.
Nothing reads these rows. bw_entity_social_identities is untouched.
"""
from alembic import op
import sqlalchemy as sa

revision = 'ts_014'
down_revision = 'ts_013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'entity_identity_shadow',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('batch_key', sa.String(32), nullable=False, index=True),
        sa.Column('social_account_id', sa.Integer(), nullable=False, index=True),
        sa.Column('platform', sa.Text(), nullable=True),
        sa.Column('handle', sa.Text(), nullable=True),
        sa.Column('display_name', sa.Text(), nullable=True),
        # What code offered and what a name-match proposer would have picked.
        sa.Column('candidate_brand_ids', sa.Text(), nullable=True),
        sa.Column('candidate_count', sa.Integer(), nullable=True),
        sa.Column('name_match_brand_id', sa.Integer(), nullable=True),
        sa.Column('name_match_exact', sa.Boolean(), nullable=True),
        # What Jev answered.
        sa.Column('jev_owner_brand_id', sa.Integer(), nullable=True),
        sa.Column('jev_owner_confidence', sa.Float(), nullable=True),
        # What a curator queue should do with it, which is a softer call than
        # ownership: propose_owned | propose_community | propose_person | leave
        sa.Column('jev_action', sa.Text(), nullable=True),
        sa.Column('jev_action_confidence', sa.Float(), nullable=True),
        sa.Column('evidence_beyond_name', sa.Boolean(), nullable=True),
        sa.Column('jev_company_account', sa.Float(), nullable=True),
        sa.Column('jev_person', sa.Float(), nullable=True),
        sa.Column('jev_community', sa.Float(), nullable=True),
        sa.Column('jev_name_only', sa.Float(), nullable=True),
        sa.Column('jev_impersonation', sa.Float(), nullable=True),
        sa.Column('jev_model', sa.Text(), nullable=True),
        sa.Column('jev_latency_ms', sa.Integer(), nullable=True),
        sa.Column('jev_error', sa.Text(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
    )


def downgrade() -> None:
    op.drop_table('entity_identity_shadow')
