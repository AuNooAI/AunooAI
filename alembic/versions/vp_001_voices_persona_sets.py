"""voices_persona_sets: a site's audience personas, edited on a settings page

Until now a site's Voices audiences (patient, clinician, author, librarian
...) were fixed in code: the standard list, or a named set picked with
VOICES_PERSONAS. This table holds a set someone defined on the settings page
(/voices/personas, admins only). Each save is a new row and the newest active
row wins; older rows stay as history. With no active row the site behaves as
before.

content is JSON: {"audiences": [{"key", "label", "definition", "reason",
"show": "column" | "button" | "hidden", "group"}], "guide": "...",
"open_pairs": [["a", "b"], ...], "person_roles": [...]}.

Revision ID: vp_001
Revises: soa_002
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'vp_001'
down_revision = 'soa_002'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'voices_persona_sets',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('content', postgresql.JSONB(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('updated_by', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
    )
    op.execute("CREATE UNIQUE INDEX uq_voices_persona_sets_active "
               "ON voices_persona_sets (active) WHERE active")


def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_voices_persona_sets_active")
    op.drop_table('voices_persona_sets')
