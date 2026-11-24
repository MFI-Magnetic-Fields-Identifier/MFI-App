from sqlalchemy import CheckConstraint, Column, DateTime, Float, ForeignKey, Index, JSON, MetaData, Table, Text

metadata = MetaData()

motor_models = Table(
    "motor_models",
    metadata,
    Column("model_id", Text, primary_key=True),
    Column("manufacturer", Text, nullable=False),
    Column("product_line", Text, nullable=False),
    Column("commercial_model", Text, nullable=False),
    Column("source_reference", Text, nullable=False),
    Column("technical_specs", JSON, nullable=False),
)

motor_units = Table(
    "motor_units",
    metadata,
    Column("unit_id", Text, primary_key=True),
    Column("model_id", Text, ForeignKey("motor_models.model_id"), nullable=False),
)

capture_sessions = Table(
    "capture_sessions",
    metadata,
    Column("session_id", Text, primary_key=True),
)

motor_images = Table(
    "motor_images",
    metadata,
    Column("image_id", Text, primary_key=True),
    Column("path", Text, nullable=False),
    Column("unit_id", Text, ForeignKey("motor_units.unit_id"), nullable=False),
    Column("session_id", Text, ForeignKey("capture_sessions.session_id"), nullable=False),
    Column("origin", Text, nullable=False),
    Column("registered_at", DateTime(timezone=True), nullable=False),
    Column("capture_angle_deg", Float),
    Column("validation_status", Text, nullable=False),
    Column("sha256", Text),
    Column("original_filename", Text),
    Index("uq_motor_images_sha256", "sha256", unique=True),
    CheckConstraint(
        "capture_angle_deg >= 0 AND capture_angle_deg < 360",
        name="ck_motor_images_capture_angle",
    ),
    CheckConstraint(
        "validation_status IN ('pending', 'approved', 'rejected')",
        name="ck_motor_images_validation_status",
    ),
)
