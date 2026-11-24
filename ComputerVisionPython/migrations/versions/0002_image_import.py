"""Registra a origem e o hash das fotografias importadas."""

import sqlalchemy as sa
from alembic import op

revision = "0002_image_import"
down_revision = "0001_motor_catalog"


def upgrade() -> None:
    op.add_column("motor_images", sa.Column("sha256", sa.Text()))
    op.add_column("motor_images", sa.Column("original_filename", sa.Text()))
    op.create_index("uq_motor_images_sha256", "motor_images", ["sha256"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_motor_images_sha256", table_name="motor_images")
    op.drop_column("motor_images", "original_filename")
    op.drop_column("motor_images", "sha256")
