"""rename encrypted credential fields

Revision ID: 003
Revises: 002
Create Date: 2026-06-25

"""

from typing import Sequence, Union

from alembic import op

revision: str = "003"
down_revision: Union[str, Sequence[str], None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "user_selectel_credentials",
        "encrypted_service_user_password",
        new_column_name="service_user_password",
    )
    op.alter_column(
        "user_selectel_credentials",
        "selectel_token_encrypted",
        new_column_name="selectel_token",
    )


def downgrade() -> None:
    op.alter_column(
        "user_selectel_credentials",
        "service_user_password",
        new_column_name="encrypted_service_user_password",
    )
    op.alter_column(
        "user_selectel_credentials",
        "selectel_token",
        new_column_name="selectel_token_encrypted",
    )
