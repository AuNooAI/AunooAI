"""Incident management with evidence locker

bw_incidents: managed adverse-media cases per brand with a lifecycle
(open/investigating/contained/resolved/closed), severity and owner.
bw_incident_events: append-only timeline (status/severity/owner changes, notes,
evidence captures). bw_incident_evidence: the locker — immutable server-side
snapshots of articles/social posts/alert events/risk findings taken at capture
time (sources get deleted or edited; the snapshot is the durable record), each
carrying a sha256 hash chained to the previous item so tampering with any
entry breaks the chain.

Revision ID: bw_013_incidents
Revises: bw_012_finding_reviews
Create Date: 2026-07-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'bw_013_incidents'
down_revision = 'bw_012_finding_reviews'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'bw_incidents',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('brand_id', sa.Integer(), sa.ForeignKey('bw_brands.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('severity', sa.Text(), nullable=False, server_default=sa.text("'medium'")),
        sa.Column('status', sa.Text(), nullable=False, server_default=sa.text("'open'")),
        sa.Column('owner', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('idx_bw_incidents_brand', 'bw_incidents', ['brand_id'])
    op.create_index('idx_bw_incidents_status', 'bw_incidents', ['status'])

    op.create_table(
        'bw_incident_events',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('incident_id', sa.Integer(), sa.ForeignKey('bw_incidents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('kind', sa.Text(), nullable=False),
        sa.Column('actor', sa.Text(), nullable=True),
        sa.Column('old_value', sa.Text(), nullable=True),
        sa.Column('new_value', sa.Text(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('idx_bw_incident_events_incident', 'bw_incident_events', ['incident_id'])

    op.create_table(
        'bw_incident_evidence',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('incident_id', sa.Integer(), sa.ForeignKey('bw_incidents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('evidence_type', sa.Text(), nullable=False),
        sa.Column('source_ref', sa.Text(), nullable=True),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('meta', JSONB(), nullable=True),
        sa.Column('content_sha256', sa.Text(), nullable=False),
        sa.Column('chain_sha256', sa.Text(), nullable=False),
        sa.Column('captured_by', sa.Text(), nullable=True),
        sa.Column('captured_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=False),
    )
    op.create_index('idx_bw_incident_evidence_incident', 'bw_incident_evidence', ['incident_id'])


def downgrade():
    op.drop_table('bw_incident_evidence')
    op.drop_table('bw_incident_events')
    op.drop_table('bw_incidents')
