import json
from pathlib import Path
from random import Random

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("torchvision")

from mfi_cv.data.classifier_dataset import make_demo_dataset, read_dataset
from mfi_cv.data.train_classifier import TrainingPhotos


def test_uses_manifest_labels_and_test_images_stay_unread(tmp_path: Path) -> None:
    make_demo_dataset(tmp_path)
    for path in (tmp_path / "test").rglob("*.png"):
        path.unlink()

    dataset = read_dataset(tmp_path)
    labels, samples, digest = dataset.labels, dataset.samples, dataset.manifest_sha256

    assert labels == ["demo-elipse", "demo-retangulo"]
    assert {split: len(items) for split, items in samples.items()} == {"train": 2, "val": 2, "test": 2}
    assert len(digest) == 64
    pixels, label = TrainingPhotos(samples["train"], 32)[0]
    assert pixels.shape == (3, 32, 32)
    assert label == 1


@pytest.mark.parametrize(
    ("field", "expected"), [
        ("session_id", "Vazamento entre partições"),
        ("sha256", "SHA-256 divergente"),
        ("images", "Classes sem imagens em val"),
    ],
)
def test_rejects_invalid_training_dataset(tmp_path: Path, field: str, expected: str) -> None:
    make_demo_dataset(tmp_path)
    path = tmp_path / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    images = manifest["images"]
    if field == "session_id":
        images[2][field] = images[0][field]
    elif field == "sha256":
        images[0][field] = "0" * 64
    else:
        images.pop(2)
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match=expected):
        read_dataset(tmp_path)


def test_augmentation_is_opt_in_for_training_samples(tmp_path: Path) -> None:
    make_demo_dataset(tmp_path)
    samples = read_dataset(tmp_path).samples
    baseline = TrainingPhotos(samples["train"], 64)
    varied = TrainingPhotos(samples["train"], 64, augmentation_rng=Random(42))
    validation = TrainingPhotos(samples["val"], 64)

    assert baseline[0][1] == varied[0][1]
    assert not torch.equal(baseline[0][0], varied[0][0])
    assert torch.equal(validation[0][0], validation[0][0])
