"""add chat runtime contract fields

Revision ID: c1a2b3d4e5f6
Revises: b9f3c7d1e4a2
Create Date: 2026-09-23 15:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c1a2b3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "b9f3c7d1e4a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("chat_sessions", sa.Column("channel", sa.String(length=32), nullable=False, server_default="web"))
    op.add_column("chat_sessions", sa.Column("status", sa.String(length=32), nullable=False, server_default="active"))
    op.add_column("chat_sessions", sa.Column("last_active_at", sa.DateTime(), nullable=True))
    op.create_index("idx_user_last_active", "chat_sessions", ["user_id", "last_active_at"], unique=False)

    op.add_column("chat_messages", sa.Column("message_id", sa.String(length=64), nullable=True))
    op.add_column("chat_messages", sa.Column("user_id", sa.String(length=64), nullable=True))
    op.add_column("chat_messages", sa.Column("turn_id", sa.String(length=64), nullable=True))
    op.add_column("chat_messages", sa.Column("objects_json", sa.Text(), nullable=True))
    op.create_index("idx_session_created_message", "chat_messages", ["session_id", "created_at", "message_id"], unique=False)
    op.create_index("idx_user_session", "chat_messages", ["user_id", "session_id"], unique=False)
    op.create_unique_constraint("uq_chat_messages_message_id", "chat_messages", ["message_id"])


def downgrade() -> None:
    op.drop_constraint("uq_chat_messages_message_id", "chat_messages", type_="unique")
    op.drop_index("idx_user_session", table_name="chat_messages")
    op.drop_index("idx_session_created_message", table_name="chat_messages")
    op.drop_column("chat_messages", "objects_json")
    op.drop_column("chat_messages", "turn_id")
    op.drop_column("chat_messages", "user_id")
    op.drop_column("chat_messages", "message_id")

    op.drop_index("idx_user_last_active", table_name="chat_sessions")
    op.drop_column("chat_sessions", "last_active_at")
    op.drop_column("chat_sessions", "status")
    op.drop_column("chat_sessions", "channel")
