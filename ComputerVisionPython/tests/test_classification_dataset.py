import json
import shutil
import subprocess
import sys
from collections import defaultdict
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from PIL import Image
from sqlalchemy import URL
from sqlalchemy.engine import Engine

from mfi_cv.data import CaptureSession, MotorImage, MotorModel, MotorUnit, ValidationStatus
from mfi_cv.data.classification_dataset import export_classification_dataset
from mfi_cv.data.database import create_database_engine
from mfi_cv.data.repository import MotorRepository


@pytest.fixture
def demo_catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Engine, Path]]:
    url = URL.create("sqlite", database=str(tmp_path / "catalog.sqlite3"))
    monkeypatch.setenv("MFI_DATABASE_URL", url.render_as_string())
    command.upgrade(Config(Path(__file__).resolve().parents[1] / "alembic.ini"), "head")
    engine = create_database_engine()
    source = tmp_path / "raw"
    source.mkdir()
    try:
        yield engine, source
    finally:
        engine.dispose()


def _register_demo(engine: Engine, source: Path, records: list[tuple[str, str, str, bool]]) -> None:
    models: dict[str, MotorModel] = {}
    units: dict[str, MotorUnit] = {}
    sessions: dict[str, CaptureSession] = {}
    with engine.begin() as connection:
        repository = MotorRepository(connection)
        for index, (model_id, unit_id, session_id, approved) in enumerate(records):
            if model_id not in models:
                models[model_id] = MotorModel(
                    model_id, "Fabricante fictício", "Linha fictícia",
                    "Modelo fictício", "Fonte fictícia para testes",
                )
                repository.add_model(models[model_id])
            if unit_id not in units:
                units[unit_id] = MotorUnit(unit_id, models[model_id])
                repository.add_unit(units[unit_id])
            if session_id not in sessions:
                sessions[session_id] = CaptureSession(session_id)
                repository.add_session(sessions[session_id])
            relative_path = Path(f"demo-{index}.png")
            if approved:
                Image.new("RGB", (16, 16), (index, 0, 0)).save(source / relative_path)
            repository.add_image(MotorImage(
                f"demo-{index:03d}", relative_path, units[unit_id], sessions[session_id],
                "Imagem sintética para teste", datetime(2026, 1, 1, tzinfo=UTC),
                capture_angle_deg=45.0,
                validation_status=ValidationStatus.APPROVED if approved else ValidationStatus.PENDING,
            ))


def test_reproducible_export_keeps_related_records_together(
    demo_catalog: tuple[Engine, Path], tmp_path: Path
) -> None:
    engine, source = demo_catalog
    records = [
        ("modelo/a", "a1", "s1", True),
        ("modelo/a", "a1", "s2", False),
        ("modelo-b", "b1", "s2", True),
        ("modelo-b", "b2", "s2", True),
        ("modelo/a", "a2", "s3", True),
        ("modelo/a", "a3", "s4", True),
        ("modelo-b", "b3", "s5", True),
        ("modelo-b", "b4", "s6", True),
    ]
    _register_demo(engine, source, records)
    first = export_classification_dataset(engine, source, tmp_path / "one", seed=7)
    second = export_classification_dataset(engine, source, tmp_path / "two", seed=7)
    assert first.read_bytes() == second.read_bytes()
    manifest = json.loads(first.read_text(encoding="utf-8"))
    assert manifest["seed"] == 7
    assert manifest["warnings"] == []
    assert len(manifest["images"]) == 7
    by_image = {item["image_id"]: item for item in manifest["images"]}
    assert "demo-001" not in by_image
    assert by_image["demo-000"]["group_id"] == by_image["demo-002"]["group_id"]
    assert by_image["demo-002"]["group_id"] == by_image["demo-003"]["group_id"]
    by_link = defaultdict(set)
    for item in manifest["images"]:
        assert item["capture_angle_deg"] == 45.0
        for key in ("unit_id", "session_id"):
            by_link[key, item[key]].add(item["split"])
        assert (first.parent / item["path"]).read_bytes() == (source / item["source_path"]).read_bytes()
    assert all(len(splits) == 1 for splits in by_link.values())
    for info in manifest["classes"].values():
        assert info["independent_groups"] == 3
        assert all(info["image_counts"].values())


def test_cli_reports_insufficient_groups_and_groups_legacy_duplicates(
    demo_catalog: tuple[Engine, Path], tmp_path: Path
) -> None:
    engine, source = demo_catalog
    _register_demo(engine, source, [
        ("modelo-a", "a1", "s1", True), ("modelo-a", "a2", "s2", True),
    ])
    shutil.copyfile(source / "demo-0.png", source / "demo-1.png")
    output = tmp_path / "classification"
    result = subprocess.run(
        [sys.executable, "-m", "mfi_cv.data.classification_dataset",
         "--source", str(source), "--output", str(output), "--seed", "9"],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "Aviso:" in result.stdout
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    info = manifest["classes"]["modelo-a"]
    assert info["independent_groups"] == 1
    assert info["image_counts"] == {"train": 2, "val": 0, "test": 0}
    assert info["missing_splits"] == ["val", "test"]
    assert (output / "val").is_dir() and (output / "test").is_dir()
    with pytest.raises(ValueError, match="saída inexistente"):
        export_classification_dataset(engine, source, output)


def test_empty_catalog_does_not_publish_output(
    demo_catalog: tuple[Engine, Path], tmp_path: Path
) -> None:
    engine, source = demo_catalog
    output = tmp_path / "classification"
    with pytest.raises(ValueError, match="não contém imagens aprovadas"):
        export_classification_dataset(engine, source, output)
    assert not output.exists()


def test_corrupt_file_does_not_publish_partial_dataset(
    demo_catalog: tuple[Engine, Path], tmp_path: Path
) -> None:
    engine, source = demo_catalog
    _register_demo(engine, source, [
        ("modelo-a", "a1", "s1", True), ("modelo-a", "a2", "s2", True),
    ])
    (source / "demo-1.png").write_bytes(b"arquivo invalido para teste")
    output = tmp_path / "classification"
    with pytest.raises(ValueError, match="Imagem inválida"):
        export_classification_dataset(engine, source, output)
    assert not output.exists()
    assert not list(tmp_path.glob(".export-*"))
