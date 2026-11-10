"""Add non-sensitive conversation context."""

import sqlalchemy as sa
from alembic import op

revision = "0002_conversation_context"
down_revision = "0001_single_clinic"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column("context_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_column("chat_sessions", "context_json")
