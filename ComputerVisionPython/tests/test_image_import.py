from collections.abc import Iterator
from hashlib import sha256
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from PIL import Image
from sqlalchemy import URL
from sqlalchemy.engine import Engine

from mfi_cv.data import CaptureSession, MotorImage, MotorModel, MotorUnit, ValidationStatus
from mfi_cv.data.database import create_database_engine
from mfi_cv.data.image_import import DuplicateImageError, import_photo
from mfi_cv.data.repository import MotorRepository


@pytest.fixture
def catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    url = URL.create("sqlite", database=str(tmp_path / "catalog.sqlite3"))
    monkeypatch.setenv("MFI_DATABASE_URL", url.render_as_string())
    command.upgrade(Config(Path(__file__).resolve().parents[1] / "alembic.ini"), "head")
    engine = create_database_engine()
    model = MotorModel("modelo-demo", "Fabricante fictício", "Linha fictícia",
                       "Modelo fictício", "Fonte fictícia para teste")
    try:
        with engine.begin() as connection:
            repository = MotorRepository(connection)
            repository.add_model(model)
            repository.add_unit(MotorUnit("exemplar-demo", model))
            repository.add_session(CaptureSession("sessao-demo"))
        yield engine
    finally:
        engine.dispose()


def _import_demo(
    catalog: Engine, source: Path, *, unit_id: str = "exemplar-demo",
    session_id: str = "sessao-demo",
) -> MotorImage:
    return import_photo(
        catalog, source, unit_id=unit_id, session_id=session_id,
        origin="Fotografia sintética de teste", storage_root=source.parent / "raw",
        capture_angle_deg=45,
    )


@pytest.mark.parametrize(
    ("image_format", "extension"), [("JPEG", ".jpg"), ("PNG", ".png"), ("WEBP", ".webp")]
)
def test_stores_original_bytes_and_metadata(
    catalog: Engine, tmp_path: Path, image_format: str, extension: str
) -> None:
    source = tmp_path / "foto-sem-extensao"
    Image.new("RGB", (16, 16), "blue").save(source, format=image_format)

    imported = _import_demo(catalog, source)

    assert imported.path.suffix == extension
    assert (tmp_path / "raw" / imported.path).read_bytes() == source.read_bytes()
    assert imported.sha256 == sha256(source.read_bytes()).hexdigest()
    assert imported.original_filename == source.name
    assert imported.model_id == "modelo-demo"
    assert imported.unit.unit_id == "exemplar-demo"
    assert imported.session.session_id == "sessao-demo"
    assert imported.validation_status is ValidationStatus.PENDING
    assert imported.capture_angle_deg == 45
    with catalog.connect() as connection:
        assert MotorRepository(connection).get_image(imported.image_id) == imported


def test_rejects_renamed_duplicate(catalog: Engine, tmp_path: Path) -> None:
    source = tmp_path / "original.png"
    Image.new("RGB", (16, 16)).save(source)
    imported = _import_demo(catalog, source)
    renamed = source.rename(tmp_path / "renomeada.png")

    with pytest.raises(DuplicateImageError) as error:
        _import_demo(catalog, renamed)

    assert error.value.image_id == imported.image_id
    assert list((tmp_path / "raw").rglob("*.png")) == [tmp_path / "raw" / imported.path]


@pytest.mark.parametrize("kind", ["text", "gif", "truncated"])
def test_rejects_invalid_or_unsupported_content(catalog: Engine, tmp_path: Path, kind: str) -> None:
    source = tmp_path / "foto.png"
    if kind == "text":
        source.write_bytes(b"imagem invalida")
    elif kind == "gif":
        Image.new("RGB", (16, 16)).save(source, format="GIF")
    else:
        Image.new("RGB", (16, 16)).save(source, format="PNG")
        source.write_bytes(source.read_bytes()[:40])

    with pytest.raises(ValueError, match="Imagem inválida"):
        _import_demo(catalog, source)

    assert not list((tmp_path / "raw").iterdir())


@pytest.mark.parametrize("field", ["unit_id", "session_id"])
def test_rejects_unknown_catalog_ids(catalog: Engine, tmp_path: Path, field: str) -> None:
    source = tmp_path / "foto.png"
    Image.new("RGB", (16, 16)).save(source)

    with pytest.raises(ValueError, match="não cadastr"):
        _import_demo(catalog, source, **{field: "ausente"})

    assert not list((tmp_path / "raw").iterdir())


def test_storage_failure_rolls_back_image(catalog: Engine, tmp_path: Path) -> None:
    source = tmp_path / "foto.png"
    Image.new("RGB", (16, 16)).save(source)
    digest = sha256(source.read_bytes()).hexdigest()
    storage_root = tmp_path / "raw"
    storage_root.mkdir()
    (storage_root / digest[:2]).touch()

    with pytest.raises(FileExistsError):
        _import_demo(catalog, source)

    with catalog.connect() as connection:
        assert MotorRepository(connection).find_image_id_by_sha256(digest) is None
