"""Add managed SSH terminal authorization metadata and unique device reservations."""

import sqlalchemy as sa

from alembic import op

revision: str = "0007_managed_access"
down_revision: str | None = "0006_remote_desktop"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "managed_terminal_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("device_id", sa.String(36), sa.ForeignKey("devices.id"), nullable=False),
        sa.Column("active_device_id", sa.String(36), sa.ForeignKey("devices.id"), unique=True),
        sa.Column(
            "requester_session_id", sa.String(36), sa.ForeignKey("user_sessions.id"), nullable=False
        ),
        sa.Column("operator_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reason", sa.String(300), nullable=False),
        sa.Column("account", sa.String(120), nullable=False),
        sa.Column("credential_hash", sa.String(64), nullable=False),
        sa.Column("profile_fingerprint", sa.String(64), nullable=False),
        sa.Column("cols", sa.Integer, nullable=False),
        sa.Column("rows", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_reason", sa.String(64)),
    )
    op.create_index(
        "ix_managed_terminal_sessions_device_id", "managed_terminal_sessions", ["device_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_managed_terminal_sessions_device_id", table_name="managed_terminal_sessions")
    op.drop_table("managed_terminal_sessions")
