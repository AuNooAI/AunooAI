"""merge bw_005 and ti_001

Revision ID: 63b7c68885f9
Revises: bw_005, ti_001
Create Date: 2026-04-27 11:40:53.014109

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '63b7c68885f9'
down_revision: Union[str, None] = ('bw_005', 'ti_001')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
