"""Add short-lived consented desktop session metadata and device reservations."""

import sqlalchemy as sa

from alembic import op

revision: str = "0006_remote_desktop"
down_revision: str | None = "0005_wazuh_mappings"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "remote_desktop_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("device_id", sa.String(36), sa.ForeignKey("devices.id"), nullable=False),
        sa.Column("active_device_id", sa.String(36), sa.ForeignKey("devices.id"), unique=True),
        sa.Column(
            "requester_session_id", sa.String(36), sa.ForeignKey("user_sessions.id"), nullable=False
        ),
        sa.Column("operator_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("operator_name", sa.String(120), nullable=False),
        sa.Column("reason", sa.String(300), nullable=False),
        sa.Column("mode", sa.String(8), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_reason", sa.String(64)),
    )
    op.create_index(
        "ix_remote_desktop_sessions_device_id", "remote_desktop_sessions", ["device_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_remote_desktop_sessions_device_id", table_name="remote_desktop_sessions")
    op.drop_table("remote_desktop_sessions")
