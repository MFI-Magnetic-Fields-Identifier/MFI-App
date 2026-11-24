import argparse
from array import array
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw, ImageOps

from .photo_files import open_photo

DEFAULT_SIZE = 224
PADDING_COLOR = (114, 114, 114)


def _oriented_rgb(photo: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(photo)
    if image.has_transparency_data:
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, PADDING_COLOR)
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return image.convert("RGB")


def _resize_to_fit(photo: Image.Image, size: int) -> Image.Image:
    scale = size / max(photo.size)
    dimensions = tuple(max(1, round(length * scale)) for length in photo.size)
    return photo.resize(dimensions, Image.Resampling.LANCZOS)


def _letterbox(photo: Image.Image, size: int) -> Image.Image:
    resized = _resize_to_fit(photo, size)
    canvas = Image.new("RGB", (size, size), PADDING_COLOR)
    canvas.paste(resized, ((size - resized.width) // 2, (size - resized.height) // 2))
    return canvas


def prepare_image(
    photo: Image.Image, *, size: int = DEFAULT_SIZE,
    transform: Callable[[Image.Image], Image.Image] | None = None,
) -> Image.Image:
    """Orienta e redimensiona uma imagem RGB mantendo a cena inteira."""
    if type(size) is not int or size < 1:
        raise ValueError("O tamanho deve ser um inteiro positivo.")
    rgb = _oriented_rgb(photo)
    return _letterbox(transform(rgb) if transform is not None else rgb, size)


def normalize_rgb(photo: Image.Image) -> array[float]:
    """Retorna float32 em ordem CHW (R, G, B), com valores de 0 a 1."""
    if photo.mode != "RGB":
        raise ValueError("A normalização requer uma imagem RGB.")
    return array("f", (value / 255 for channel in photo.split() for value in channel.tobytes()))


def _adjust_contrast(photo: Image.Image) -> Image.Image:
    # Ajuste só a luminância, preservando os canais de crominância.
    luminance, cb, cr = photo.convert("YCbCr").split()
    contrasted = ImageOps.autocontrast(luminance, cutoff=1)
    return Image.merge("YCbCr", (contrasted, cb, cr)).convert("RGB")


def _preview(panels: list[tuple[str, Image.Image]]) -> Image.Image:
    panel_size = 320
    label_height = 28
    preview = Image.new("RGB", (panel_size * len(panels), panel_size + label_height), "#272727")
    draw = ImageDraw.Draw(preview)
    for index, (label, photo) in enumerate(panels):
        tile = _resize_to_fit(photo, panel_size)
        left = index * panel_size
        draw.text((left + 8, 7), label, fill="white")
        preview.paste(tile, (
            left + (panel_size - tile.width) // 2,
            label_height + (panel_size - tile.height) // 2,
        ))
    return preview


def generate_previews(
    sources: list[Path], output: Path, *, size: int = DEFAULT_SIZE, compare_contrast: bool = False
) -> None:
    """Grava os PNGs processados e as comparações em uma nova pasta."""
    if not sources:
        raise ValueError("Informe pelo menos uma fotografia.")
    if type(size) is not int or size < 1:
        raise ValueError("O tamanho deve ser um inteiro positivo.")
    if output.exists():
        raise ValueError(f"A pasta de saída já existe: {output}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".preprocess-", dir=output.parent) as temp:
        staging = Path(temp) / "result"
        staging.mkdir()
        for index, source in enumerate(sources, 1):
            try:
                with open_photo(source) as photo:
                    original = _oriented_rgb(photo)
            except ValueError as error:
                raise ValueError(f"{source}: {error}") from error
            processed = _letterbox(original, size)
            panels = [("Original orientado", original), ("Redimensionado", processed)]
            if compare_contrast:
                panels.append(("Contraste experimental", _letterbox(_adjust_contrast(original), size)))
            processed.save(staging / f"{index:04d}-processed.png")
            _preview(panels).save(staging / f"{index:04d}-comparison.png")
        staging.rename(output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepara fotos e gera comparações visuais.")
    parser.add_argument("sources", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, default=Path("dataset/processed"))
    parser.add_argument("--size", type=int, default=DEFAULT_SIZE)
    parser.add_argument("--compare-contrast", action="store_true")
    args = parser.parse_args()
    try:
        generate_previews(
            args.sources, args.output, size=args.size, compare_contrast=args.compare_contrast,
        )
    except (OSError, ValueError) as error:
        parser.exit(1, f"Erro no pré-processamento: {error}\n")
    for index, source in enumerate(args.sources, 1):
        print(f"{source} -> {args.output / f'{index:04d}-comparison.png'}")


if __name__ == "__main__":
    main()
