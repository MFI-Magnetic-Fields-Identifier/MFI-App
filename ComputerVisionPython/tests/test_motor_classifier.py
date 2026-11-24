import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

torch = pytest.importorskip("torch")
pytest.importorskip("torchvision")

from mfi_cv.data.classifier_model import ARCHITECTURE, build_classifier
from mfi_cv.data.motor_classifier import (
    DecisionThresholds,
    InvalidPhotoError,
    ModelUnavailableError,
    MotorClassifier,
)


@pytest.fixture(scope="module")
def demo_checkpoint(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("classifier") / "demo.pt"
    model = build_classifier(3)
    # Pontuações controladas para testar o contrato sem depender do treino.
    with torch.no_grad():
        model.classifier[-1].weight.zero_()
        model.classifier[-1].bias.copy_(torch.tensor([0.10, 0.75, 0.15]).log())
    torch.save({
        "config": {
            "architecture": ARCHITECTURE,
            "class_ids": ["modelo-demo-a", "modelo-demo-b", "modelo-demo-c"],
            "demo": True,
            "preprocessing": {
                "size": 32, "exif_orientation": True, "resize": "letterbox_lanczos",
                "padding_rgb": [114, 114, 114], "scale": 255,
                "mean": [0.485, 0.456, 0.406], "std": [0.229, 0.224, 0.225],
            },
        },
        "state_dict": model.state_dict(),
    }, path)
    return path


@pytest.fixture
def demo_photo(tmp_path: Path) -> Path:
    path = tmp_path / "figura-sintetica.png"
    Image.new("RGB", (45, 25), "gray").save(path)
    return path


def test_loads_checkpoint_and_returns_ranked_top_k(demo_checkpoint: Path, demo_photo: Path) -> None:
    classifier = MotorClassifier(demo_checkpoint)
    result = classifier.predict(str(demo_photo), top_k=10)

    assert classifier.is_demo
    assert [candidate["model_id"] for candidate in result["candidates"]] == [
        "modelo-demo-b", "modelo-demo-c", "modelo-demo-a",
    ]
    assert [candidate["score"] for candidate in result["candidates"]] == pytest.approx([0.75, 0.15, 0.10])
    assert result["status"] == "needs_confirmation"


@pytest.mark.parametrize(
    ("thresholds", "status"), [
        (DecisionThresholds(0.6, 0.7, 0.5), "accepted"),
        (DecisionThresholds(0.8, 0.9, 0.1), "unknown"),
        (DecisionThresholds(0.6, 0.7, 0.7), "needs_confirmation"),
    ],
)
def test_decision_uses_runner_up_even_with_top_one(
    demo_checkpoint: Path, demo_photo: Path, thresholds: DecisionThresholds, status: str
) -> None:
    result = MotorClassifier(demo_checkpoint, thresholds=thresholds).predict(demo_photo, top_k=1)

    assert len(result["candidates"]) == 1
    assert result["status"] == status


def test_handles_invalid_images_and_top_k(
    demo_checkpoint: Path, demo_photo: Path, tmp_path: Path
) -> None:
    classifier = MotorClassifier(demo_checkpoint)
    corrupted = tmp_path / "invalida.jpg"
    corrupted.write_bytes(b"arquivo invalido de teste")
    for path in (corrupted, tmp_path / "ausente.jpg"):
        with pytest.raises(InvalidPhotoError, match="Fotografia inválida"):
            classifier.predict(path)
    with pytest.raises(ValueError, match="Top-K"):
        classifier.predict(demo_photo, top_k=0)


def test_handles_unavailable_or_incompatible_checkpoints(tmp_path: Path) -> None:
    corrupted = tmp_path / "invalido.pt"
    corrupted.write_bytes(b"checkpoint invalido de teste")
    incompatible = tmp_path / "outro-modelo.pt"
    torch.save({"config": {"architecture": "incompativel"}}, incompatible)
    for path in (corrupted, incompatible, tmp_path / "ausente.pt"):
        with pytest.raises(ModelUnavailableError, match="Checkpoint indisponível"):
            MotorClassifier(path)


def test_cli_returns_json_and_labels_the_demo(demo_checkpoint: Path, demo_photo: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "mfi_cv.data.motor_classifier", str(demo_photo),
         "--checkpoint", str(demo_checkpoint), "--top-k", "1"],
        capture_output=True, text=True, timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["candidates"][0]["model_id"] == "modelo-demo-b"
    assert "Checkpoint de demonstra" in result.stderr


def test_validates_threshold_order_and_margin() -> None:
    with pytest.raises(ValueError, match="rejeição"):
        DecisionThresholds(rejection=0.9, acceptance=0.8)
    with pytest.raises(ValueError, match="margem"):
        DecisionThresholds(margin=float("nan"))
