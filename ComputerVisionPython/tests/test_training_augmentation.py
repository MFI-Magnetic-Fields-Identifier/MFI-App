from random import Random
from unittest.mock import Mock

import pytest
from PIL import Image, ImageDraw

from mfi_cv.data.preprocessing import PADDING_COLOR, prepare_image
from mfi_cv.data.training_augmentation import augment_training_image


@pytest.fixture
def synthetic_photo() -> Image.Image:
    photo = Image.new("RGB", (80, 40), (80, 90, 100))
    ImageDraw.Draw(photo).rectangle((0, 0, 23, 16), fill=(190, 25, 20))
    return photo


def test_augmentation_is_reproducible_without_changing_source(synthetic_photo: Image.Image) -> None:
    original = synthetic_photo.tobytes()
    first_rng, second_rng = Random(42), Random(42)
    first = [augment_training_image(synthetic_photo, 80, first_rng).tobytes() for _ in range(2)]
    second = [augment_training_image(synthetic_photo, 80, second_rng).tobytes() for _ in range(2)]

    assert first == second
    assert first[0] != first[1]
    assert synthetic_photo.tobytes() == original


@pytest.mark.parametrize("parameters", [(8, 1, 1), (0, 0.85, 1), (0, 1, 0.85)])
def test_each_operation_modifies_pixels(parameters: tuple[float, ...], synthetic_photo: Image.Image) -> None:
    rng = Mock(spec=Random)
    rng.uniform.side_effect = parameters

    result = augment_training_image(synthetic_photo, 80, rng)

    assert result.size == (80, 80)
    assert result.tobytes() != prepare_image(synthetic_photo, size=80).tobytes()
    assert result.getpixel((0, 0)) == PADDING_COLOR
