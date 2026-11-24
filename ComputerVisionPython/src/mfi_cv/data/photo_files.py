from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import BinaryIO
from warnings import catch_warnings, simplefilter

from PIL import Image

PHOTO_EXTENSIONS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}


@contextmanager
def open_photo(source: Path | BinaryIO, *, max_pixels: int | None = None) -> Iterator[Image.Image]:
    """Valida a estrutura e entrega uma fotografia estática já decodificada."""
    with ExitStack() as resources:
        try:
            with catch_warnings():
                simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(source, formats=tuple(PHOTO_EXTENSIONS)) as header:
                    image_format = header.format
                    if image_format not in PHOTO_EXTENSIONS or getattr(header, "is_animated", False):
                        raise ValueError("Esperada uma imagem estática JPEG, PNG ou WebP.")
                    if max_pixels is not None and header.width * header.height > max_pixels:
                        raise PhotoSizeError("A imagem excede o limite de pixels.")
                    header.verify()
                # verify() consome o arquivo. Reabra para validar a decodificação.
                photo = resources.enter_context(Image.open(source, formats=(image_format,)))
                photo.load()
        except (OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise ValueError("Imagem inválida ou fora dos formatos JPEG, PNG e WebP.") from exc
        yield photo


class PhotoSizeError(ValueError):
    """A foto excede o limite de pixels solicitado."""
