"""rename meta to metadata_json and add metadata_status

Revision ID: 2cd399fb57fe
Revises: 4057b9e31ba2
Create Date: 2026-02-16 17:54:49.927918

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2cd399fb57fe'
down_revision: Union[str, None] = '4057b9e31ba2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade() -> None:
    op.alter_column(
        "cases",
        "meta",
        new_column_name="metadata_json",
        existing_type=postgresql.JSONB(),
        existing_nullable=False,
    )
    op.add_column(
        "cases",
        sa.Column(
            "metadata_status",
            sa.String(length=25),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
    )

def downgrade() -> None:
    op.drop_column("cases", "metadata_status")

    op.alter_column(
        "cases",
        "metadata_json",
        new_column_name="meta",
        existing_type=postgresql.JSONB(),
        existing_nullable=False,
    )