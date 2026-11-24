import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from mfi_cv.data.preprocessing import (
    PADDING_COLOR,
    generate_previews,
    normalize_rgb,
    prepare_image,
)


def test_preserves_proportions_and_adds_centered_padding() -> None:
    original = Image.new("RGB", (80, 40), "red")
    processed = prepare_image(original, size=20)

    assert processed.size == (20, 20)
    assert processed.getpixel((0, 4)) == PADDING_COLOR
    assert processed.getpixel((0, 5)) == (255, 0, 0)
    assert processed.getpixel((19, 14)) == (255, 0, 0)
    assert processed.getpixel((19, 15)) == PADDING_COLOR
    assert original.size == (80, 40)


def test_applies_exif_orientation_before_resizing() -> None:
    original = Image.new("RGB", (8, 4), "red")
    original.getexif()[274] = 6  # Rotação EXIF de 90° no sentido horário.

    processed = prepare_image(original, size=8)

    assert processed.getpixel((1, 0)) == PADDING_COLOR
    assert processed.getpixel((2, 0)) == (255, 0, 0)
    assert processed.getpixel((5, 7)) == (255, 0, 0)
    assert processed.getpixel((6, 7)) == PADDING_COLOR
    assert original.getexif()[274] == 6


def test_handles_transparency_and_extreme_aspect_ratio() -> None:
    original = Image.new("RGBA", (1, 900), (255, 0, 0, 0))
    processed = prepare_image(original, size=8)

    assert processed.mode == "RGB"
    assert processed.getextrema() == ((114, 114), (114, 114), (114, 114))


def test_normalization_returns_channel_first_float32() -> None:
    photo = Image.new("RGB", (2, 1))
    photo.putpixel((0, 0), (0, 128, 255))
    photo.putpixel((1, 0), (255, 0, 64))

    normalized = normalize_rgb(photo)

    assert normalized.itemsize == 4
    assert list(normalized) == pytest.approx([0, 1, 128 / 255, 0, 1, 64 / 255])
    with pytest.raises(ValueError, match="RGB"):
        normalize_rgb(photo.convert("L"))


def test_cli_processes_a_batch_and_keeps_contrast_experimental(tmp_path: Path) -> None:
    photo = Image.new("RGB", (32, 32), (45, 45, 45))
    photo.paste((65, 65, 65), (16, 0, 32, 32))
    original = tmp_path / "escura.png"
    photo.save(original)
    second = tmp_path / "segunda.webp"
    photo.save(second)
    raw = [source.read_bytes() for source in (original, second)]
    output = tmp_path / "with-contrast"
    result = subprocess.run(
        [sys.executable, "-m", "mfi_cv.data.preprocessing", str(original), str(second),
         "--size", "32", "--output", str(output), "--compare-contrast"],
        capture_output=True, text=True, timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert len(list(output.glob("*.png"))) == 4
    with Image.open(output / "0001-comparison.png") as comparison:
        left = comparison.getpixel((680, 180))[0]
        right = comparison.getpixel((920, 180))[0]
        assert right - left > 20
    baseline = tmp_path / "baseline"
    generate_previews([original, second], baseline, size=32)
    for name in ("0001-processed.png", "0002-processed.png"):
        assert (output / name).read_bytes() == (baseline / name).read_bytes()
    assert [source.read_bytes() for source in (original, second)] == raw


def test_invalid_photo_does_not_publish_partial_output(tmp_path: Path) -> None:
    good = tmp_path / "good.png"
    Image.new("RGB", (8, 8)).save(good)
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"foto invalida de teste")
    output = tmp_path / "output"

    with pytest.raises(ValueError, match="bad.png"):
        generate_previews([good, bad], output)
    assert not output.exists()
    with pytest.raises(ValueError, match="inteiro positivo"):
        generate_previews([good], output, size=0)
