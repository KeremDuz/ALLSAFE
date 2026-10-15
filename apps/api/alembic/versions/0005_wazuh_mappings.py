"""Add manager-scoped explicit Wazuh device mappings."""

import sqlalchemy as sa

from alembic import op

revision: str = "0005_wazuh_mappings"
down_revision: str | None = "0004_phishcatch_scans"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "wazuh_device_mappings",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("server_scope", sa.String(64), nullable=False),
        sa.Column("device_id", sa.String(36), nullable=False),
        sa.Column("agent_id", sa.String(32), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("server_scope", "agent_id"),
        sa.UniqueConstraint("server_scope", "device_id"),
    )
    op.create_index(
        "ix_wazuh_device_mappings_server_scope", "wazuh_device_mappings", ["server_scope"]
    )


def downgrade() -> None:
    op.drop_index("ix_wazuh_device_mappings_server_scope", table_name="wazuh_device_mappings")
    op.drop_table("wazuh_device_mappings")
