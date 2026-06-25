"""add selectel token fields

Revision ID: 002
Revises: 001
Create Date: 2026-06-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, Sequence[str], None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_selectel_credentials",
        sa.Column("selectel_token_encrypted", sa.Text(), nullable=True),
    )
    op.add_column(
        "user_selectel_credentials",
        sa.Column("selectel_token_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_selectel_credentials", "selectel_token_expires_at")
    op.drop_column("user_selectel_credentials", "selectel_token_encrypted")
