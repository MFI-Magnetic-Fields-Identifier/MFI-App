from datetime import UTC
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.engine import Connection, RowMapping
from sqlalchemy.sql import Select

from .models import CaptureSession, MotorImage, MotorModel, MotorUnit, ValidationStatus
from .schema import capture_sessions, motor_images, motor_models, motor_units


def _model_from_row(row: RowMapping) -> MotorModel:
    return MotorModel(
        model_id=row["model_id"],
        manufacturer=row["manufacturer"],
        product_line=row["product_line"],
        commercial_model=row["commercial_model"],
        source_reference=row["source_reference"],
        technical_specs=row["technical_specs"],
    )


def _image_from_row(row: RowMapping) -> MotorImage:
    registered_at = row["registered_at"]
    # O SQLite devolve o valor sem fuso. A gravação sempre usa UTC.
    if registered_at.tzinfo is None:
        registered_at = registered_at.replace(tzinfo=UTC)
    return MotorImage(
        image_id=row["image_id"],
        path=Path(row["path"]),
        unit=MotorUnit(row["unit_id"], _model_from_row(row)),
        session=CaptureSession(row["session_id"]),
        origin=row["origin"],
        registered_at=registered_at.astimezone(UTC),
        capture_angle_deg=row["capture_angle_deg"],
        validation_status=ValidationStatus(row["validation_status"]),
        sha256=row["sha256"],
        original_filename=row["original_filename"],
    )


def _select_images() -> Select:
    return (
        select(motor_images, motor_models)
        .join_from(motor_images, motor_units)
        .join_from(motor_units, motor_models)
    )


class MotorRepository:
    """Cadastro e consulta dentro de uma conexão controlada pelo chamador."""

    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def add_model(self, model: MotorModel) -> None:
        self.connection.execute(motor_models.insert().values(
            model_id=model.model_id,
            manufacturer=model.manufacturer,
            product_line=model.product_line,
            commercial_model=model.commercial_model,
            source_reference=model.source_reference,
            technical_specs=dict(model.technical_specs),
        ))

    def get_model(self, model_id: str) -> MotorModel | None:
        statement = select(motor_models).where(motor_models.c.model_id == model_id)
        row = self.connection.execute(statement).mappings().one_or_none()
        return _model_from_row(row) if row is not None else None

    def list_models(self) -> list[MotorModel]:
        statement = select(motor_models).order_by(motor_models.c.model_id)
        return [_model_from_row(row) for row in self.connection.execute(statement).mappings()]

    def add_unit(self, unit: MotorUnit) -> None:
        self.connection.execute(motor_units.insert().values(
            unit_id=unit.unit_id, model_id=unit.model.model_id,
        ))

    def get_unit(self, unit_id: str) -> MotorUnit | None:
        statement = select(motor_units.c.unit_id, motor_models).join(motor_models)
        row = self.connection.execute(
            statement.where(motor_units.c.unit_id == unit_id)
        ).mappings().one_or_none()
        return MotorUnit(unit_id, _model_from_row(row)) if row is not None else None

    def add_session(self, session: CaptureSession) -> None:
        self.connection.execute(capture_sessions.insert().values(session_id=session.session_id))

    def get_session(self, session_id: str) -> CaptureSession | None:
        statement = select(capture_sessions.c.session_id).where(
            capture_sessions.c.session_id == session_id
        )
        stored_id = self.connection.execute(statement).scalar_one_or_none()
        return CaptureSession(stored_id) if stored_id is not None else None

    def add_image(self, image: MotorImage) -> None:
        statement = select(motor_units.c.model_id).where(
            motor_units.c.unit_id == image.unit.unit_id
        )
        stored_model_id = self.connection.execute(statement).scalar_one_or_none()
        if stored_model_id is not None and stored_model_id != image.model_id:
            raise ValueError("O modelo da imagem difere do modelo do exemplar cadastrado.")
        self.connection.execute(motor_images.insert().values(
            image_id=image.image_id,
            path=image.path.as_posix(),
            unit_id=image.unit.unit_id,
            session_id=image.session.session_id,
            origin=image.origin,
            registered_at=image.registered_at.astimezone(UTC),
            capture_angle_deg=image.capture_angle_deg,
            validation_status=image.validation_status.value,
            sha256=image.sha256,
            original_filename=image.original_filename,
        ))

    def find_image_id_by_sha256(self, sha256: str) -> str | None:
        statement = select(motor_images.c.image_id).where(motor_images.c.sha256 == sha256)
        return self.connection.execute(statement).scalar_one_or_none()

    def get_image(self, image_id: str) -> MotorImage | None:
        statement = _select_images().where(motor_images.c.image_id == image_id)
        row = self.connection.execute(statement).mappings().one_or_none()
        return _image_from_row(row) if row is not None else None

    def list_images(self) -> list[MotorImage]:
        statement = _select_images().order_by(motor_images.c.image_id)
        return [_image_from_row(row) for row in self.connection.execute(statement).mappings()]
