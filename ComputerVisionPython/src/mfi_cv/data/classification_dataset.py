import argparse
import json
from collections import Counter
from hashlib import file_digest
from pathlib import Path
from random import Random
from shutil import copyfile
from tempfile import TemporaryDirectory

from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from .database import create_database_engine
from .models import MotorImage, ValidationStatus
from .photo_files import PHOTO_EXTENSIONS, open_photo
from .repository import MotorRepository

SPLITS = ("train", "val", "test")


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def _source_path(root: Path, image: MotorImage) -> Path:
    path = (root / image.path).resolve()
    if image.path.anchor or not path.is_relative_to(root):
        raise ValueError(f"Caminho fora do armazenamento para a imagem {image.image_id}: {image.path}")
    return path


def _related_groups(
    images: list[MotorImage], hashes: dict[str, str]
) -> list[list[MotorImage]]:
    # Vínculos transitivos unem sessões, exemplares e cópias exatas.
    parents = list(range(len(images)))
    first_seen: dict[tuple[str, str], int] = {}

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    for index, image in enumerate(images):
        links = [("unit", image.unit.unit_id), ("session", image.session.session_id)]
        digest = hashes.get(image.image_id, image.sha256)
        if digest is not None:
            links.append(("sha256", digest))
        for link in links:
            first = first_seen.setdefault(link, index)
            parents[find(index)] = find(first)

    groups: dict[int, list[MotorImage]] = {}
    for index, image in enumerate(images):
        if image.image_id in hashes:
            groups.setdefault(find(index), []).append(image)
    return list(groups.values())


def _allocate_groups(
    groups: list[list[MotorImage]], seed: int
) -> tuple[list[str], Counter[str]]:
    classes = [{image.model_id for image in group} for group in groups]
    counts = Counter(model for group_classes in classes for model in group_classes)
    train_counts = counts.copy()
    allocations = ["train"] * len(groups)
    order = list(range(len(groups)))
    Random(seed).shuffle(order)
    by_model: dict[str, list[int]] = {model: [] for model in counts}
    for index in order:
        for model in classes[index]:
            by_model[model].append(index)

    assigned: dict[str, Counter[str]] = {"val": Counter(), "test": Counter()}
    eligible = sorted(
        (model for model in counts if counts[model] >= 3),
        key=lambda model: (counts[model], model),
    )
    # Cubra primeiro as classes nas duas partições. Depois aproxime 15%
    # dos grupos por classe, mantendo ao menos um grupo de treino por classe.
    for coverage_only in (True, False):
        for split in ("test", "val"):
            for model in eligible:
                target = 1 if coverage_only else max(1, round(counts[model] * 0.15))
                candidates = by_model[model]
                if coverage_only:
                    candidates = sorted(candidates, key=lambda index: -sum(
                        counts[label] >= 3 and assigned[split][label] == 0
                        for label in classes[index]
                    ))
                for index in candidates:
                    if assigned[split][model] >= target:
                        break
                    if allocations[index] != "train" or any(
                        train_counts[label] <= 1 for label in classes[index]
                    ):
                        continue
                    allocations[index] = split
                    assigned[split].update(classes[index])
                    train_counts.subtract(classes[index])
    return allocations, counts


def export_classification_dataset(
    engine: Engine, source_root: Path, output: Path, *, seed: int = 42
) -> Path:
    """Exporta as fotos aprovadas e retorna o caminho do manifesto."""
    source_root = source_root.resolve(strict=True)
    if not source_root.is_dir():
        raise ValueError(f"Pasta de imagens inválida: {source_root}")
    output = output.resolve()
    if output.exists() or output.is_relative_to(source_root):
        raise ValueError("Escolha uma saída inexistente e fora da pasta de imagens originais.")

    with engine.connect() as connection:
        images = MotorRepository(connection).list_images()
    approved = [image for image in images if image.validation_status is ValidationStatus.APPROVED]
    if not approved:
        raise ValueError("O catálogo não contém imagens aprovadas para exportação.")

    sources = {image.image_id: _source_path(source_root, image) for image in approved}
    hashes = {}
    for image in approved:
        digest = _sha256(sources[image.image_id])
        if image.sha256 is not None and image.sha256 != digest:
            raise ValueError(f"SHA-256 divergente para a imagem {image.image_id}: {image.path}")
        hashes[image.image_id] = digest

    groups = _related_groups(images, hashes)
    allocations, group_counts = _allocate_groups(groups, seed)
    # Nomes gerados evitam colisões e caracteres de caminho dos IDs de catálogo.
    folders = {model: f"class_{index:04d}" for index, model in enumerate(sorted(group_counts))}
    image_counts = {model: dict.fromkeys(SPLITS, 0) for model in folders}
    entries = []

    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".export-", dir=output.parent) as temp:
        building = Path(temp) / "dataset"
        for split in SPLITS:
            (building / split).mkdir(parents=True)
        for group_id, (group, split) in enumerate(zip(groups, allocations, strict=True)):
            for image in group:
                path = building / split / folders[image.model_id]
                path.mkdir(exist_ok=True)
                staged = path / f"image_{len(entries):06d}"
                copyfile(sources[image.image_id], staged)
                digest = hashes[image.image_id]
                if _sha256(staged) != digest:
                    raise ValueError(f"A imagem {image.image_id} mudou durante a exportação.")
                with open_photo(staged) as photo:
                    extension = PHOTO_EXTENSIONS[photo.format]
                destination = staged.rename(staged.with_suffix(extension))
                image_counts[image.model_id][split] += 1
                entries.append({
                    "image_id": image.image_id,
                    "model_id": image.model_id,
                    "unit_id": image.unit.unit_id,
                    "session_id": image.session.session_id,
                    "group_id": group_id,
                    "split": split,
                    "path": destination.relative_to(building).as_posix(),
                    "source_path": image.path.as_posix(),
                    "original_filename": image.original_filename,
                    "origin": image.origin,
                    "capture_angle_deg": image.capture_angle_deg,
                    "sha256": digest,
                })

        classes = {}
        for model, folder in folders.items():
            counts = image_counts[model]
            classes[model] = {
                "directory": folder,
                "independent_groups": group_counts[model],
                "image_counts": counts,
                "missing_splits": [split for split in SPLITS if counts[split] == 0],
            }
        warnings = [
            f"{model}: sem imagens em {', '.join(info['missing_splits'])} "
            f"na divisão gerada ({info['independent_groups']} grupos independentes)."
            for model, info in classes.items() if info["missing_splits"]
        ]
        if len(classes) < 2:
            warnings.append("O dataset tem menos de duas classes aprovadas.")
        manifest = {"seed": seed, "classes": classes, "images": entries, "warnings": warnings}
        (building / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
        )
        building.rename(output)
    return output / "manifest.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Exporta um dataset de classificação a partir do catálogo.")
    parser.add_argument("--source", type=Path, default=Path("dataset/raw"))
    parser.add_argument("--output", type=Path, default=Path("dataset/classification"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    try:
        engine = create_database_engine()
        try:
            manifest = export_classification_dataset(engine, args.source, args.output, seed=args.seed)
        finally:
            engine.dispose()
    except (OSError, ValueError, SQLAlchemyError) as error:
        parser.exit(1, f"Erro na exportação: {error}\n")
    print(manifest)
    for warning in json.loads(manifest.read_text(encoding="utf-8"))["warnings"]:
        print(f"Aviso: {warning}")


if __name__ == "__main__":
    main()
