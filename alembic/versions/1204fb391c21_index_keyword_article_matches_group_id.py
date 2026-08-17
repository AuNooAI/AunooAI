"""index keyword_article_matches group_id

Revision ID: 1204fb391c21
Revises: fsv_horizon_16
Create Date: 2026-08-11 11:30:43.043673

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1204fb391c21'
down_revision: Union[str, None] = 'fsv_horizon_16'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # CONCURRENTLY so the per-group stats queries and live ingest writes are
    # not blocked while the index builds (785k rows on wileytest). Requires
    # running outside a transaction, hence the autocommit block.
    with op.get_context().autocommit_block():
        op.create_index(
            'idx_keyword_article_matches_group_id',
            'keyword_article_matches',
            ['group_id'],
            unique=False,
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            'idx_keyword_article_matches_group_id',
            table_name='keyword_article_matches',
            postgresql_concurrently=True,
            if_exists=True,
        )
