from random import Random

from PIL import Image, ImageEnhance

from .preprocessing import PADDING_COLOR, prepare_image

ROTATION_DEGREES = 8.0
BRIGHTNESS_RANGE = (0.85, 1.15)
SCALE_RANGE = (0.85, 1.0)


def augment_training_image(photo: Image.Image, size: int, rng: Random) -> Image.Image:
    """Aplica variações à foto de treino, mantendo a cena inteira."""
    angle = rng.uniform(-ROTATION_DEGREES, ROTATION_DEGREES)
    brightness = rng.uniform(*BRIGHTNESS_RANGE)
    scaled_size = max(1, round(size * rng.uniform(*SCALE_RANGE)))

    def transform(rgb: Image.Image) -> Image.Image:
        adjusted = ImageEnhance.Brightness(rgb).enhance(brightness)
        return adjusted.rotate(
            angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=PADDING_COLOR,
        )

    processed = prepare_image(photo, size=scaled_size, transform=transform)
    canvas = Image.new("RGB", (size, size), PADDING_COLOR)
    offset = (size - scaled_size) // 2
    canvas.paste(processed, (offset, offset))
    return canvas
