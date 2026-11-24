import json
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

pytest.importorskip("torch")
pytest.importorskip("torchvision")

from mfi_cv.data.analyze_classifier_errors import _angle_sector, analyze_errors
from mfi_cv.data.classifier_dataset import make_demo_dataset, read_dataset
from mfi_cv.data.motor_classifier import DecisionThresholds


def test_groups_wrong_and_unrecognized_cases_by_capture_condition(tmp_path: Path) -> None:
    make_demo_dataset(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["images"]:
        if entry["split"] != "test":
            continue
        path = tmp_path / entry["path"]
        rectangular = entry["model_id"] == "demo-retangulo"
        luminance = 40 if rectangular else 210
        Image.new("L", (8, 8), luminance).save(path)
        entry["sha256"] = sha256(path.read_bytes()).hexdigest()
        if rectangular:
            entry["capture_angle_deg"] = 95.5
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    dataset = read_dataset(tmp_path)

    def predict(path: Path) -> dict:
        return {
            "candidates": [{"model_id": "demo-elipse", "score": 0.9 if path.parent.name == "retangulo" else 0.55}],
            "status": "accepted" if path.parent.name == "retangulo" else "unknown",
        }

    classifier = SimpleNamespace(
        class_ids=tuple(dataset.labels), manifest_sha256=dataset.manifest_sha256,
        is_demo=True, thresholds=DecisionThresholds(), predict=predict,
    )
    report = analyze_errors(classifier, tmp_path)

    assert report["totals"] == {
        "images": 2, "incorrect_top1": 1, "unknown": 1, "needs_confirmation": 0, "accepted": 1,
    }
    assert report["accepted_errors"] == 1
    assert report["confusions"] == [{"actual": "demo-retangulo", "predicted": "demo-elipse", "count": 1}]
    assert report["by_angle"]["90_to_under_180"]["incorrect_top1"] == 1
    assert report["by_angle"]["unknown"]["unknown"] == 1
    assert report["by_brightness"]["dark"]["images"] == 1
    assert report["by_brightness"]["bright"]["unknown"] == 1
    wrong = report["by_model"]["demo-retangulo"]["examples"][0]
    assert wrong["predicted_class_example"] == "test/elipse/demo.png"
    assert wrong["mean_luminance"] == 40
    rejected = report["by_model"]["demo-elipse"]["examples"][0]
    assert rejected["incorrect_top1"] is False and rejected["status"] == "unknown"
    assert rejected["capture_angle_deg"] is None


@pytest.mark.parametrize(
    ("angle", "expected"), [
        (0, "0_to_under_90"), (90, "90_to_under_180"), (359.99, "270_to_under_360"),
        (360, "unknown"), (None, "unknown"),
    ],
)
def test_angle_sectors(angle: float | None, expected: str) -> None:
    assert _angle_sector(angle) == expected
