import argparse
import json
from dataclasses import asdict, dataclass, field
from hashlib import file_digest
from math import isfinite
from os import walk
from pathlib import Path
from statistics import pvariance

from PIL import Image

from .photo_files import open_photo

SHARPNESS_MAX_EDGE = 512
DEFAULT_MIN_SIDE = 640
DEFAULT_MIN_SHARPNESS = 100.0


@dataclass
class PhotoReview:
    path: str
    sha256: str | None = None
    width: int | None = None
    height: int | None = None
    sharpness: float | None = None
    issues: list[str] = field(default_factory=list)


@dataclass
class QualityReport:
    min_side: int
    min_sharpness: float
    sharpness_max_edge: int = SHARPNESS_MAX_EDGE
    files: list[PhotoReview] = field(default_factory=list)
    duplicate_groups: list[list[str]] = field(default_factory=list)


def _sharpness(photo: Image.Image) -> float | None:
    grayscale = photo.convert("L")
    grayscale.thumbnail((SHARPNESS_MAX_EDGE, SHARPNESS_MAX_EDGE), Image.Resampling.LANCZOS)
    width, height = grayscale.size
    if min(width, height) < 3:
        return None

    pixels = grayscale.tobytes()
    # O Laplaciano mede quanto o pixel central difere dos quatro vizinhos.
    return pvariance(
        pixels[index - width] + pixels[index + width]
        + pixels[index - 1] + pixels[index + 1] - 4 * pixels[index]
        for row in range(1, height - 1)
        for index in range(row * width + 1, (row + 1) * width - 1)
    )


def _raise_walk_error(error: OSError) -> None:
    raise error


def review_photos(
    root: Path,
    *,
    min_side: int = DEFAULT_MIN_SIDE,
    min_sharpness: float = DEFAULT_MIN_SHARPNESS,
) -> QualityReport:
    """Gera um relatório de revisão sem alterar as imagens ou o catálogo."""
    if not root.is_dir():
        raise ValueError(f"Pasta de imagens inexistente ou inválida: {root}")
    if min_side < 1:
        raise ValueError("O tamanho mínimo deve ser pelo menos 1 pixel.")
    if not isfinite(min_sharpness) or min_sharpness < 0:
        raise ValueError("A nitidez mínima deve ser um número finito e não negativo.")

    report = QualityReport(min_side=min_side, min_sharpness=min_sharpness)
    by_hash: dict[str, list[PhotoReview]] = {}
    for directory, subdirs, filenames in walk(root, onerror=_raise_walk_error):
        subdirs[:] = [name for name in subdirs if not name.startswith(".")]
        for name in filenames:
            path = Path(directory) / name
            if name.startswith(".") or path.is_symlink() or not path.is_file():
                continue
            review = PhotoReview(path=path.relative_to(root).as_posix())
            report.files.append(review)
            try:
                with path.open("rb") as stream:
                    review.sha256 = file_digest(stream, "sha256").hexdigest()
            except OSError:
                review.issues.append("unreadable")
                continue

            by_hash.setdefault(review.sha256, []).append(review)
            try:
                with open_photo(path) as photo:
                    review.width, review.height = photo.size
                    score = _sharpness(photo)
            except ValueError:
                review.issues.append("invalid_image")
                continue

            if min(review.width, review.height) < min_side:
                review.issues.append("low_resolution")
            if score is not None:
                review.sharpness = round(score, 4)
                if score < min_sharpness:
                    review.issues.append("low_sharpness")

    for group in by_hash.values():
        if len(group) > 1:
            report.duplicate_groups.append(sorted(review.path for review in group))
            for review in group:
                review.issues.append("duplicate")
    report.files.sort(key=lambda review: review.path)
    report.duplicate_groups.sort()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera um relatório JSON de qualidade das imagens.")
    parser.add_argument("root", type=Path, nargs="?", default=Path("dataset/raw"))
    parser.add_argument("--min-side", type=int, default=DEFAULT_MIN_SIDE)
    parser.add_argument("--min-sharpness", type=float, default=DEFAULT_MIN_SHARPNESS)
    args = parser.parse_args()
    try:
        report = review_photos(args.root, min_side=args.min_side, min_sharpness=args.min_sharpness)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(json.dumps(asdict(report), indent=2))


if __name__ == "__main__":
    main()
