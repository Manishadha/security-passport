"""merge heads after share links + evidence lifecycle

Revision ID: 2c1e5575bdcb
Revises: 5e4ff79e5cb6, 89dd75d00851
Create Date: 2026-02-23 14:26:58.642333

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2c1e5575bdcb'
down_revision: Union[str, Sequence[str], None] = ('5e4ff79e5cb6', '89dd75d00851')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
