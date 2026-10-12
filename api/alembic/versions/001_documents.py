"""documents table

Revision ID: 001
"""

from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("kind", sa.String(), primary_key=True),
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("data", sa.String(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("documents")
