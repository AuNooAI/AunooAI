"""merge: canonical head mm_026 with the art_text_001 branch

Canonical only. Customer sites are on the art_title_001 line and take
art_text_001 directly; do not copy this file to them.

Revision ID: mm_027
Revises: mm_026, art_text_001
Create Date: 2026-09-10
"""

revision = 'mm_027'
down_revision = ('mm_026', 'art_text_001')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
