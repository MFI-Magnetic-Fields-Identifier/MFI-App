import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFilter

from mfi_cv.data.image_quality import review_photos


def test_reports_issues_in_stable_order_without_changing_files(tmp_path: Path) -> None:
    nested = tmp_path / "subpasta"
    nested.mkdir()
    original = nested / "original.png"
    Image.new("RGB", (16, 20), "gray").save(original)
    duplicate = tmp_path / "copia.png"
    shutil.copyfile(original, duplicate)
    corrupt = tmp_path / "invalida.png"
    corrupt.write_bytes(b"arquivo corrompido de teste")
    staging = tmp_path / ".import-demo"
    staging.mkdir()
    shutil.copyfile(original, staging / "photo")
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}

    report = review_photos(tmp_path)

    assert report == review_photos(tmp_path)
    assert report.duplicate_groups == [["copia.png", "subpasta/original.png"]]
    assert [review.path for review in report.files] == [
        "copia.png", "invalida.png", "subpasta/original.png",
    ]
    copy, invalid, original_review = report.files
    assert copy.issues == original_review.issues == ["low_resolution", "low_sharpness", "duplicate"]
    assert (copy.width, copy.height, copy.sharpness) == (16, 20, 0)
    assert copy.sha256 == original_review.sha256
    assert invalid.issues == ["invalid_image"]
    assert invalid.sharpness is None
    assert {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before


def test_blurring_reduces_sharpness_score(tmp_path: Path) -> None:
    photo = Image.new("L", (128, 128))
    ImageDraw.Draw(photo).rectangle((32, 32, 95, 95), fill=255)
    photo.save(tmp_path / "nitida.png")
    photo.filter(ImageFilter.GaussianBlur(4)).save(tmp_path / "desfocada.png")

    blurred, sharp = review_photos(tmp_path, min_side=128).files

    assert blurred.sharpness < sharp.sharpness
    assert blurred.issues == ["low_sharpness"]
    assert sharp.issues == []


def test_image_too_small_for_laplacian(tmp_path: Path) -> None:
    Image.new("L", (2, 2)).save(tmp_path / "pequena.png")

    review = review_photos(tmp_path).files[0]

    assert review.sharpness is None
    assert review.issues == ["low_resolution"]


def _run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "mfi_cv.data.image_quality", *arguments],
        capture_output=True, text=True, timeout=10,
    )


def test_cli_outputs_json_for_empty_directory(tmp_path: Path) -> None:
    result = _run_cli(str(tmp_path), "--min-side", "320", "--min-sharpness", "0")

    assert result.returncode == 0
    assert json.loads(result.stdout) == {
        "min_side": 320, "min_sharpness": 0.0, "sharpness_max_edge": 512,
        "files": [], "duplicate_groups": [],
    }


@pytest.mark.parametrize(
    "arguments", [("--min-side", "0"), ("--min-sharpness", "nan"), ("--min-sharpness", "-1")]
)
def test_cli_rejects_invalid_thresholds(tmp_path: Path, arguments: tuple[str, str]) -> None:
    assert _run_cli(str(tmp_path), *arguments).returncode == 2


def test_cli_rejects_missing_directory(tmp_path: Path) -> None:
    assert _run_cli(str(tmp_path / "ausente")).returncode == 2
