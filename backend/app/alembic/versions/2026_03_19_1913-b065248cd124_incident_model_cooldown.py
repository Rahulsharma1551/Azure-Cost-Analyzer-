"""incident_model_cooldown

Revision ID: b065248cd124
Revises: f3a1b2c4d5e6
Create Date: 2026-03-19 19:13:29.560470

"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "f3a1b2c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "alert_event",
        sa.Column(
            "breach_started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "alert_event",
        sa.Column("breach_resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "alert_event",
        sa.Column("last_notified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "alert_event",
        sa.Column(
            "notification_count",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "alert_event",
        sa.Column(
            "cooldown_minutes",
            sa.Integer(),
            nullable=False,
            server_default="120",
        ),
    )

    op.execute(
        """
        UPDATE alert_event
        SET
            breach_started_at = triggered_at,
            last_notified_at  = triggered_at
        WHERE breach_started_at IS NULL
        """
    )

    op.alter_column("alert_event", "breach_started_at", nullable=False)
    op.alter_column("alert_event", "last_notified_at", nullable=False)

    op.drop_column("alert_event", "triggered_at")

    op.add_column(
        "alert_threshold",
        sa.Column("cooldown_minutes", sa.Integer(), nullable=True),
    )

    op.add_column(
        "anomaly_settings",
        sa.Column(
            "cooldown_minutes",
            sa.Integer(),
            nullable=False,
            server_default="120",
        ),
    )


def downgrade() -> None:
    op.drop_column("anomaly_settings", "cooldown_minutes")
    try:
        op.add_column(
            "anomaly_settings",
            sa.Column(
                "max_alerts_per_day",
                sa.Integer(),
                nullable=False,
                server_default="3",
            ),
        )
    except Exception:
        pass

    op.drop_column("alert_threshold", "cooldown_minutes")

    op.add_column(
        "alert_event",
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE alert_event SET triggered_at = breach_started_at")
    op.alter_column("alert_event", "triggered_at", nullable=False)

    op.drop_column("alert_event", "cooldown_minutes")
    op.drop_column("alert_event", "notification_count")
    op.drop_column("alert_event", "last_notified_at")
    op.drop_column("alert_event", "breach_resolved_at")
    op.drop_column("alert_event", "breach_started_at")
