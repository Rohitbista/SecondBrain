"""Initial users and notes table

Revision ID: c1332f46acf4
Revises: 
Create Date: 2026-10-16 11:48:56.789288

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = 'c1332f46acf4'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 384  # For embedding model = BAAI/bge-small-en-v1.5

def upgrade() -> None:
    # pgvector extension (needs to be installed on the Postgres server)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
 
    # Shared trigger function so updated_at is refreshed on ANY update,
    # not only updates that go through SQLAlchemy's ORM
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
 
    # ---------- users ----------
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column(
            "is_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )
    op.execute(
        """
        CREATE TRIGGER trg_users_updated_at
        BEFORE UPDATE ON users
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        """
    )
 
    # ---------- notes ----------
    op.create_table(
        "notes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_notes_user_id", "notes", ["user_id"])
    op.execute(
        """
        CREATE TRIGGER trg_notes_updated_at
        BEFORE UPDATE ON notes
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        """
    )
 
    # Approximate nearest-neighbour index (cosine distance)
    op.execute(
        """
        CREATE INDEX ix_notes_embedding_hnsw
        ON notes USING hnsw (embedding vector_cosine_ops);
        """
    )
 
 
def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_notes_embedding_hnsw")
    op.execute("DROP TRIGGER IF EXISTS trg_notes_updated_at ON notes")
    op.drop_index("ix_notes_user_id", table_name="notes")
    op.drop_table("notes")
 
    op.execute("DROP TRIGGER IF EXISTS trg_users_updated_at ON users")
    op.drop_table("users")
 
    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")
    # The vector extension is intentionally left installed, since other
    # tables or databases may depend on it.
