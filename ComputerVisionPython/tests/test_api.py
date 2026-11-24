import asyncio
from collections.abc import AsyncIterator, Iterator
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy.engine import Engine

httpx = pytest.importorskip("httpx")
torch = pytest.importorskip("torch")
pytest.importorskip("torchvision")
pytest.importorskip("fastapi")

from mfi_cv import api
from mfi_cv.data import MotorModel
from mfi_cv.data.classifier_model import ARCHITECTURE, build_classifier
from mfi_cv.data.database import create_database_engine
from mfi_cv.data.repository import MotorRepository
from mfi_cv.data.schema import metadata


@pytest.fixture(scope="module")
def api_checkpoint(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("api") / "demo.pt"
    model = build_classifier(2)
    torch.save({
        "state_dict": model.state_dict(),
        "config": {
            "architecture": ARCHITECTURE,
            "class_ids": ["demo/a", "demo-b"],
            "demo": True,
            "preprocessing": {
                "size": 32, "exif_orientation": True, "resize": "letterbox_lanczos",
                "padding_rgb": [114, 114, 114], "scale": 255,
                "mean": [0.485, 0.456, 0.406], "std": [0.229, 0.224, 0.225],
            },
        },
    }, path)
    return path


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Engine]:
    engine = create_database_engine(f"sqlite:///{(tmp_path / 'catalog.sqlite3').as_posix()}")
    try:
        metadata.create_all(engine)
        with engine.begin() as connection:
            MotorRepository(connection).add_model(MotorModel(
                "demo/a", "Fabricante fictício", "Linha fictícia", "Modelo fictício",
                "Fonte fictícia para testes", {"campo_demo": 42},
            ))
        yield engine
    finally:
        engine.dispose()


def _image_bytes(image_format: str) -> bytes:
    with BytesIO() as file:
        Image.new("RGB", (24, 20), "gray").save(file, format=image_format)
        return file.getvalue()


def test_serves_catalog_inference_and_openapi(api_checkpoint: Path, database: Engine) -> None:
    app = api.create_app(checkpoint=api_checkpoint, database=database)

    async def check() -> None:
        async with app.router.lifespan_context(app), httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            health = await client.get("/health")
            assert health.status_code == 200
            assert health.json() == {"status": "ok", "classifier_ready": True, "catalog_ready": True}
            assert (await client.get("/models")).json() == {"model_ids": ["demo/a", "demo-b"], "demo": True}
            motor = await client.get("/motors/demo%2Fa")
            assert motor.status_code == 200
            assert motor.json()["technical_specs"] == {"campo_demo": 42}
            missing = await client.get("/motors/ausente")
            assert missing.status_code == 404 and "detail" in missing.json()

            for media_type, image_format in api.IMAGE_MEDIA_TYPES.items():
                response = await client.post(
                    "/predict", content=_image_bytes(image_format), headers={"Content-Type": media_type},
                )
                assert response.status_code == 200, response.text
                prediction = response.json()
                assert len(prediction["candidates"]) == 2
                assert prediction["status"] in {"unknown", "accepted", "needs_confirmation"}

            schema = (await client.get("/openapi.json")).json()
            assert set(schema["paths"]) == {
                "/health", "/models", "/predict", "/motors", "/motors/{motor_id}",
            }
            catalog_schema = schema["paths"]["/motors"]["get"]["responses"]["200"]["content"]
            assert catalog_schema["application/json"]["schema"]["type"] == "array"
            upload = schema["paths"]["/predict"]["post"]["requestBody"]["content"]
            assert set(upload) == set(api.IMAGE_MEDIA_TYPES)
            assert all(entry["schema"]["format"] == "binary" for entry in upload.values())

    asyncio.run(check())


def test_rejects_invalid_and_oversized_uploads(
    api_checkpoint: Path, database: Engine, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api, "MAX_IMAGE_PIXELS", 100)
    app = api.create_app(checkpoint=api_checkpoint, database=database)

    async def large_stream() -> AsyncIterator[bytes]:
        chunk = b"x" * (1024 * 1024)
        for _ in range(9):
            yield chunk

    async def check() -> None:
        async with app.router.lifespan_context(app), httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            standard_headers = {"Content-Type": "image/png"}
            for content, headers, status in (
                (b"", standard_headers, 400),
                (b"arquivo corrompido de teste", standard_headers, 400),
                (b"texto", {"Content-Type": "text/plain"}, 415),
                (_image_bytes("PNG"), standard_headers, 413),
                (b"x", {**standard_headers, "Content-Length": str(api.MAX_UPLOAD_BYTES + 1)}, 413),
                (large_stream(), standard_headers, 413),
            ):
                result = await client.post("/predict", content=content, headers=headers)
                assert result.status_code == status, result.text
                assert isinstance(result.json()["detail"], str)

            monkeypatch.setattr(api, "MAX_IMAGE_PIXELS", 24_000_000)
            mislabeled = await client.post(
                "/predict", content=_image_bytes("PNG"), headers={"Content-Type": "image/jpeg"},
            )
            assert mislabeled.status_code == 415

    asyncio.run(check())


def test_reports_unavailable_dependencies(tmp_path: Path, database: Engine) -> None:
    app = api.create_app(checkpoint=tmp_path / "missing.pt", database=database)
    empty = create_database_engine(f"sqlite:///{(tmp_path / 'empty.sqlite3').as_posix()}")
    without_catalog = api.create_app(checkpoint=tmp_path / "missing.pt", database=empty)

    async def check() -> None:
        async with app.router.lifespan_context(app), httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            health = await client.get("/health")
            assert health.status_code == 503
            assert health.json() == {
                "status": "unavailable", "classifier_ready": False, "catalog_ready": True,
            }
            assert (await client.get("/models")).status_code == 503
            assert (await client.post("/predict")).status_code == 503
            assert (await client.get("/motors/demo%2Fa")).status_code == 200
        async with without_catalog.router.lifespan_context(without_catalog), httpx.AsyncClient(
            transport=httpx.ASGITransport(app=without_catalog), base_url="http://test",
        ) as client:
            assert (await client.get("/health")).json()["catalog_ready"] is False
            assert (await client.get("/motors")).status_code == 503
            assert (await client.get("/motors/demo%2Fa")).status_code == 503

    try:
        asyncio.run(check())
    finally:
        empty.dispose()


def test_lists_catalog_with_no_checkpoint(database: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MFI_CHECKPOINT", raising=False)
    with database.begin() as connection:
        MotorRepository(connection).add_model(MotorModel(
            "demo-0", "Outro fabricante fictício", "Linha fictícia", "Outro modelo fictício",
            "Fonte fictícia para testes",
        ))
    app = api.create_app(database=database)

    async def check() -> None:
        async with app.router.lifespan_context(app), httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            assert (await client.get("/models")).status_code == 503
            response = await client.get("/motors")
            assert response.status_code == 200
            assert response.json() == [
                {
                    "model_id": "demo-0",
                    "manufacturer": "Outro fabricante fictício",
                    "product_line": "Linha fictícia",
                    "commercial_model": "Outro modelo fictício",
                },
                {
                    "model_id": "demo/a",
                    "manufacturer": "Fabricante fictício",
                    "product_line": "Linha fictícia",
                    "commercial_model": "Modelo fictício",
                },
            ]

    asyncio.run(check())


def test_lists_empty_catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MFI_CHECKPOINT", raising=False)
    database = create_database_engine(f"sqlite:///{(tmp_path / 'empty-catalog.sqlite3').as_posix()}")
    metadata.create_all(database)
    app = api.create_app(database=database)

    async def check() -> None:
        async with app.router.lifespan_context(app), httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            response = await client.get("/motors")
            assert response.status_code == 200
            assert response.json() == []

    try:
        asyncio.run(check())
    finally:
        database.dispose()
