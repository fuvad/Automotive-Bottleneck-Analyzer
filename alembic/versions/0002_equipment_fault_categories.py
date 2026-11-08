"""Extend allowed equipment fault categories without changing existing records.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_fault_category", "fault_event", type_="check")
    op.create_check_constraint(
        "ck_fault_category",
        "fault_event",
        "category IN ('robot_fault','quality_stop','material_shortage',"
        "'mechanical_fault','electrical_fault','sensor_fault','other_equipment_fault')",
    )


def downgrade() -> None:
    raise RuntimeError("Downgrade would invalidate new equipment categories; review data manually")
