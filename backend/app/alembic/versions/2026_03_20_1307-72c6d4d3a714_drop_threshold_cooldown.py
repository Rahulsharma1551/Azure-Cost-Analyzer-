"""incident_model_cooldown

Revision ID: 72c6d4d3a714
Revises: b1c2d3e4f5a6
Create Date: 2026-03-20 13:07:06.470500

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "72c6d4d3a714"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("alert_threshold", "cooldown_minutes")
    op.drop_column("alert_event", "acknowledged_at")
    # ### end Alembic commands ###


def downgrade() -> None:
    op.add_column(
        "alert_threshold",
        sa.Column("cooldown_minutes", sa.Integer(), nullable=True),
    )
    op.add_column(
        "alert_event",
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
    )
    # ### end Alembic commands ###
