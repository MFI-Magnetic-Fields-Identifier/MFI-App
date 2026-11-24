import json
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("torch")
pytest.importorskip("torchvision")

from mfi_cv.data.classifier_dataset import make_demo_dataset, read_dataset
from mfi_cv.data.evaluate_classifier import _classification_metrics, evaluate


def test_scores_confusion_matrix_and_macro_f1() -> None:
    metrics = _classification_metrics(["a", "b"], [[3, 1], [2, 4]], top5_hits=10)

    assert metrics["top1_accuracy"] == 0.7
    assert metrics["top5_accuracy"] is None
    assert metrics["per_model"]["a"] == pytest.approx({
        "support": 4, "predicted": 5, "precision": 3 / 5, "recall": 3 / 4, "f1": 6 / 9,
    })
    assert metrics["macro"]["f1"] == pytest.approx((6 / 9 + 8 / 11) / 2)
    assert metrics["confusion_matrix"]["counts"] == [[3, 1], [2, 4]]


def test_top5_and_coverage_limits() -> None:
    labels = list("abcdef")
    matrix = [[0] * 6 for _ in labels]
    matrix[0][0] = 1
    matrix[0][1] = 1
    metrics = _classification_metrics(labels, matrix, top5_hits=1)

    assert metrics["top5_accuracy"] == 0.5
    assert metrics["top1_accuracy"] == 0.5
    assert metrics["per_model"]["b"]["precision"] == 0.0
    assert metrics["per_model"]["b"]["recall"] is None
    assert metrics["macro"] == dict.fromkeys(("precision", "recall", "f1"))


def test_evaluates_only_reserved_photos(tmp_path: Path) -> None:
    make_demo_dataset(tmp_path)
    dataset = read_dataset(tmp_path)
    labels, digest = dataset.labels, dataset.manifest_sha256
    for split in ("train", "val"):
        for photo in (tmp_path / split).rglob("*.png"):
            photo.unlink()

    seen = []

    def predict(path: Path, *, top_k: int) -> dict:
        seen.append(path)
        assert top_k == 5
        ranked = [f"demo-{path.parent.name}", *labels]
        candidates = [{"model_id": label} for label in dict.fromkeys(ranked)]
        return {"candidates": candidates, "status": "unknown"}

    classifier = SimpleNamespace(
        class_ids=tuple(labels), manifest_sha256=digest, is_demo=True, predict=predict,
    )
    report = evaluate(classifier, tmp_path)

    assert len(seen) == report["image_count"] == 2
    assert all(path.parent.parent.name == "test" for path in seen)
    assert report["metrics"]["top1_accuracy"] == 1.0
    assert report["demo"]
    assert report["inference_time_ms"]["mean"] >= 0


@pytest.mark.parametrize(
    ("change", "message"), [
        ("hash", "SHA-256 divergente"),
        ("manifest", "difere do checkpoint"),
        ("empty", "partição de teste está vazia"),
    ],
)
def test_rejects_invalid_evaluation_inputs(tmp_path: Path, change: str, message: str) -> None:
    make_demo_dataset(tmp_path)
    dataset = read_dataset(tmp_path)
    labels, samples, digest = dataset.labels, dataset.samples, dataset.manifest_sha256
    if change == "hash":
        samples["test"][0][0].write_bytes(b"imagem alterada para teste")
    elif change == "manifest":
        digest = "0" * 64
    else:
        path = tmp_path / "manifest.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["images"] = [entry for entry in data["images"] if entry["split"] != "test"]
        path.write_text(json.dumps(data), encoding="utf-8")
        digest = read_dataset(tmp_path).manifest_sha256
    classifier = SimpleNamespace(class_ids=tuple(labels), manifest_sha256=digest)

    with pytest.raises(ValueError, match=message):
        evaluate(classifier, tmp_path)
