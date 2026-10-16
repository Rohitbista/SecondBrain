"""Adding the user token table

Revision ID: 72f4475af75b
Revises: c1332f46acf4
Create Date: 2026-10-16 13:32:30.314895

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '72f4475af75b'
down_revision: Union[str, Sequence[str], None] = 'c1332f46acf4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
 
    op.create_table(
        "user_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("purpose", sa.String(30), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("token_hash", name="uq_user_tokens_token_hash"),
    )
    op.create_index("ix_user_tokens_user_id", "user_tokens", ["user_id"])
 
 
def downgrade() -> None:
    op.drop_index("ix_user_tokens_user_id", table_name="user_tokens")
    op.drop_table("user_tokens")
    op.drop_column("users", "is_verified")
