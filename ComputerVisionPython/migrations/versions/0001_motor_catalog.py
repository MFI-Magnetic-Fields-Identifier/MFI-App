"""Cria o catálogo de motores e os registros de captura."""

import sqlalchemy as sa
from alembic import op

revision = "0001_motor_catalog"
down_revision = None


def upgrade() -> None:
    op.create_table(
        "motor_models",
        sa.Column("model_id", sa.Text(), primary_key=True),
        sa.Column("manufacturer", sa.Text(), nullable=False),
        sa.Column("product_line", sa.Text(), nullable=False),
        sa.Column("commercial_model", sa.Text(), nullable=False),
        sa.Column("source_reference", sa.Text(), nullable=False),
        sa.Column("technical_specs", sa.JSON(), nullable=False),
    )
    op.create_table(
        "motor_units",
        sa.Column("unit_id", sa.Text(), primary_key=True),
        sa.Column("model_id", sa.Text(), sa.ForeignKey("motor_models.model_id"), nullable=False),
    )
    op.create_table("capture_sessions", sa.Column("session_id", sa.Text(), primary_key=True))
    op.create_table(
        "motor_images",
        sa.Column("image_id", sa.Text(), primary_key=True),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("unit_id", sa.Text(), sa.ForeignKey("motor_units.unit_id"), nullable=False),
        sa.Column("session_id", sa.Text(), sa.ForeignKey("capture_sessions.session_id"), nullable=False),
        sa.Column("origin", sa.Text(), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("capture_angle_deg", sa.Float()),
        sa.Column("validation_status", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "capture_angle_deg >= 0 AND capture_angle_deg < 360",
            name="ck_motor_images_capture_angle",
        ),
        sa.CheckConstraint(
            "validation_status IN ('pending', 'approved', 'rejected')",
            name="ck_motor_images_validation_status",
        ),
    )


def downgrade() -> None:
    op.drop_table("motor_images")
    op.drop_table("capture_sessions")
    op.drop_table("motor_units")
    op.drop_table("motor_models")
