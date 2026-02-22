"""make source_uri nullable

Revision ID: 4057b9e31ba2
Revises: f6bf2627759e
Create Date: 2026-02-16 16:47:06.883134

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4057b9e31ba2'
down_revision: Union[str, None] = 'f6bf2627759e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "cases",
        "source_uri",
        existing_type=sa.VARCHAR(length=255),
        nullable=True,
    )

def downgrade() -> None:
    op.alter_column(
        "cases",
        "source_uri",
        existing_type=sa.VARCHAR(length=255),
        nullable=False,
    )
