"""merge multiple heads

Revision ID: 19e016650e9f
Revises: multi_collector_001, perf001, simple_multiuser_v2
Create Date: 2025-10-22 10:16:36.309456

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '19e016650e9f'
down_revision: Union[str, None] = ('multi_collector_001', 'perf001', 'simple_multiuser_v2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
