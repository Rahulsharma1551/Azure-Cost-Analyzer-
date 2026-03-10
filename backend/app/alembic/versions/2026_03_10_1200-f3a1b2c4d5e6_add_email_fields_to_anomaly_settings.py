"""add email fields to anomaly_settings

Revision ID: f3a1b2c4d5e6
Revises: ea4edfd99168
Create Date: 2026-03-10 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f3a1b2c4d5e6"
down_revision: Union[str, Sequence[str], None] = "ea4edfd99168"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add receiver_email and email_enabled columns to anomaly_settings."""
    op.add_column(
        "anomaly_settings",
        sa.Column("receiver_email", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "anomaly_settings",
        sa.Column(
            "email_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    """Remove receiver_email and email_enabled from anomaly_settings."""
    op.drop_column("anomaly_settings", "email_enabled")
    op.drop_column("anomaly_settings", "receiver_email")
