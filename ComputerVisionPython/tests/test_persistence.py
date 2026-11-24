from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import URL, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from mfi_cv.data import CaptureSession, MotorImage, MotorModel, MotorUnit, ValidationStatus
from mfi_cv.data.database import create_database_engine
from mfi_cv.data.repository import MotorRepository
from mfi_cv.data.schema import metadata


@pytest.fixture
def database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    url = URL.create("sqlite", database=str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("MFI_DATABASE_URL", url.render_as_string())
    config = Config(Path(__file__).resolve().parents[1] / "alembic.ini")
    command.upgrade(config, "head")
    engine = create_database_engine()
    try:
        yield engine, config
    finally:
        engine.dispose()


@pytest.fixture
def demo_image() -> MotorImage:
    model = MotorModel(
        "modelo-demo", "Fabricante fictício", "Linha fictícia", "Modelo fictício",
        "Fonte fictícia para testes", {"campo_demo": 42},
    )
    return MotorImage(
        "imagem-demo", Path("demo/foto.jpg"), MotorUnit("unidade-demo", model),
        CaptureSession("sessao-demo"), "Dados de demonstração",
        datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=-3))),
        capture_angle_deg=45, validation_status=ValidationStatus.APPROVED,
    )


def test_round_trip(database: tuple[Engine, Config], demo_image: MotorImage) -> None:
    engine, _ = database
    with engine.begin() as connection:
        repository = MotorRepository(connection)
        repository.add_model(demo_image.unit.model)
        repository.add_unit(demo_image.unit)
        repository.add_session(demo_image.session)
        repository.add_image(demo_image)

    with engine.connect() as connection:
        repository = MotorRepository(connection)
        assert repository.get_model(demo_image.model_id) == demo_image.unit.model
        assert repository.get_unit(demo_image.unit.unit_id) == demo_image.unit
        assert repository.get_session(demo_image.session.session_id) == demo_image.session
        image = repository.get_image(demo_image.image_id)
        assert image == demo_image
        assert image.registered_at.tzinfo is UTC


def test_transaction_rolls_back_on_duplicate(
    database: tuple[Engine, Config], demo_image: MotorImage
) -> None:
    engine, _ = database
    with pytest.raises(IntegrityError), engine.begin() as connection:
        repository = MotorRepository(connection)
        repository.add_model(demo_image.unit.model)
        repository.add_model(demo_image.unit.model)

    with engine.connect() as connection:
        repository = MotorRepository(connection)
        assert repository.get_model(demo_image.model_id) is None
        assert repository.get_unit("ausente") is None
        assert repository.get_session("ausente") is None
        assert repository.get_image("ausente") is None


def test_rejects_orphan_unit(database: tuple[Engine, Config], demo_image: MotorImage) -> None:
    engine, _ = database
    with pytest.raises(IntegrityError), engine.begin() as connection:
        MotorRepository(connection).add_unit(demo_image.unit)


def test_rejects_image_with_conflicting_model(
    database: tuple[Engine, Config], demo_image: MotorImage
) -> None:
    engine, _ = database
    with engine.begin() as connection:
        repository = MotorRepository(connection)
        repository.add_model(demo_image.unit.model)
        repository.add_unit(demo_image.unit)
        repository.add_session(demo_image.session)
        other_model = replace(demo_image.unit.model, model_id="outro-modelo")
        conflicting_image = replace(demo_image, unit=replace(demo_image.unit, model=other_model))

        with pytest.raises(ValueError, match="modelo do exemplar"):
            repository.add_image(conflicting_image)


def test_migration_can_be_reversed_and_reapplied(database: tuple[Engine, Config]) -> None:
    engine, config = database
    command.check(config)
    command.downgrade(config, "base")
    assert not set(metadata.tables).intersection(inspect(engine).get_table_names())
    command.upgrade(config, "head")
    assert set(metadata.tables).issubset(inspect(engine).get_table_names())
