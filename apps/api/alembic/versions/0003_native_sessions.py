"""Separate native mobile bearer sessions from browser cookie sessions.

Revision ID: 0003_native_sessions
Revises: 0002_identity_access
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_native_sessions"
down_revision: str | None = "0002_identity_access"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_sessions", sa.Column("channel", sa.String(16), nullable=False, server_default="web")
    )


def downgrade() -> None:
    op.drop_column("user_sessions", "channel")
