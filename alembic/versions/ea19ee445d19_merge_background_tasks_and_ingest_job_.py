"""merge background tasks and ingest job tracking heads

Revision ID: ea19ee445d19
Revises: background_tasks_001, ingest_job_tracking_001
Create Date: 2025-11-17 15:55:13.562436

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ea19ee445d19'
down_revision: Union[str, None] = ('background_tasks_001', 'ingest_job_tracking_001')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
