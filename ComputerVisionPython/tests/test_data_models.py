from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mfi_cv.data import CaptureSession, MotorImage, MotorModel, MotorUnit, ValidationStatus


@pytest.fixture
def demo_image() -> MotorImage:
    model = MotorModel(
        model_id="modelo-demo",
        manufacturer="Fabricante fictício",
        product_line="Linha fictícia",
        commercial_model="Modelo fictício",
        source_reference="Referência fictícia para testes",
    )
    return MotorImage(
        image_id="foto-demo",
        path=Path("demo.jpg"),
        unit=MotorUnit(unit_id="exemplar-demo-1", model=model),
        session=CaptureSession(session_id="sessao-demo"),
        origin="Dados de demonstração",
        registered_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_units_can_share_the_same_commercial_model(demo_image: MotorImage) -> None:
    other_image = replace(
        demo_image,
        image_id="outra-foto-demo",
        unit=MotorUnit(unit_id="exemplar-demo-2", model=demo_image.unit.model),
    )

    assert demo_image.unit.unit_id != other_image.unit.unit_id
    assert demo_image.model_id == other_image.model_id == "modelo-demo"
    assert demo_image.session.session_id == "sessao-demo"
    assert demo_image.validation_status is ValidationStatus.PENDING
    assert demo_image.capture_angle_deg is None
    assert demo_image.unit.model.technical_specs == {}


@pytest.mark.parametrize("angle", [0, 359.9])
def test_accepts_valid_angles(demo_image: MotorImage, angle: float) -> None:
    assert replace(demo_image, capture_angle_deg=angle).capture_angle_deg == angle


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("image_id", ""),
        ("path", Path(".")),
        ("unit", "exemplar-demo"),
        ("session", "sessao-demo"),
        ("origin", " "),
        ("registered_at", datetime(2026, 1, 1)),
        ("capture_angle_deg", -1),
        ("capture_angle_deg", 360),
        ("capture_angle_deg", float("nan")),
        ("capture_angle_deg", float("inf")),
        ("capture_angle_deg", True),
        ("validation_status", "unknown"),
    ],
)
def test_rejects_invalid_image_fields(
    demo_image: MotorImage, field_name: str, invalid_value: object
) -> None:
    with pytest.raises(ValueError, match=field_name):
        replace(demo_image, **{field_name: invalid_value})


@pytest.mark.parametrize(
    "field_name",
    ["model_id", "manufacturer", "product_line", "commercial_model", "source_reference"],
)
def test_rejects_blank_model_fields(demo_image: MotorImage, field_name: str) -> None:
    with pytest.raises(ValueError, match=field_name):
        replace(demo_image.unit.model, **{field_name: " "})


def test_rejects_blank_unit_id(demo_image: MotorImage) -> None:
    with pytest.raises(ValueError, match="unit_id"):
        replace(demo_image.unit, unit_id="")


def test_rejects_blank_session_id() -> None:
    with pytest.raises(ValueError, match="session_id"):
        CaptureSession(session_id="")
