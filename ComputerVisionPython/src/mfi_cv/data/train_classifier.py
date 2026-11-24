import argparse
import json
from math import isfinite
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory

import torch
import torchvision
from torch import Tensor, nn
from torch.utils.data import DataLoader, Dataset
from torchvision.models import MobileNet_V3_Small_Weights

from .classifier_dataset import make_demo_dataset, read_dataset
from .classifier_model import ARCHITECTURE, build_classifier, standardize_image
from .photo_files import open_photo
from .preprocessing import DEFAULT_SIZE, PADDING_COLOR, prepare_image
from .training_augmentation import (
    BRIGHTNESS_RANGE,
    ROTATION_DEGREES,
    SCALE_RANGE,
    augment_training_image,
)

WEIGHTS = MobileNet_V3_Small_Weights.IMAGENET1K_V1


class TrainingPhotos(Dataset[tuple[Tensor, int]]):
    def __init__(
        self, samples: list[tuple[Path, int]], size: int, *, augmentation_rng: Random | None = None
    ) -> None:
        self.samples = samples
        self.size = size
        self.augmentation_rng = augmentation_rng
        preset = WEIGHTS.transforms()
        self.mean = torch.tensor(preset.mean).view(3, 1, 1)
        self.std = torch.tensor(preset.std).view(3, 1, 1)

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int) -> tuple[Tensor, int]:
        path, label = self.samples[index]
        with open_photo(path) as original:
            if self.augmentation_rng is None:
                rgb = prepare_image(original, size=self.size)
            else:
                rgb = augment_training_image(original, self.size, self.augmentation_rng)
        return standardize_image(rgb, self.mean, self.std), label


def _epoch(
    model: nn.Module, loader: DataLoader, device: torch.device,
    optimizer: torch.optim.Optimizer | None = None,
) -> tuple[float, float]:
    # A base congelada permanece em avaliação para preservar as estatísticas de BatchNorm.
    loss_sum = 0.0
    correct = 0
    total = 0
    with torch.set_grad_enabled(optimizer is not None):
        for pixels, labels in loader:
            pixels, labels = pixels.to(device), labels.to(device)
            if optimizer is not None:
                optimizer.zero_grad()
            logits = model(pixels)
            loss = nn.functional.cross_entropy(logits, labels)
            if optimizer is not None:
                loss.backward()
                optimizer.step()
            total += labels.numel()
            loss_sum += loss.item() * labels.numel()
            correct += (logits.argmax(dim=1) == labels).sum().item()
    return loss_sum / total, correct / total


def train(
    root: Path, output: Path, *, epochs: int, batch_size: int, size: int,
    seed: int, requested_device: str, demo: bool = False, augment: bool = False,
) -> None:
    if min(epochs, batch_size, size) < 1 or not 0 <= seed < 2**63:
        raise ValueError("Use épocas, lote e tamanho positivos e seed entre 0 e 2**63 - 1.")
    if output.exists():
        raise ValueError(f"A pasta de saída já existe: {output}")
    has_cuda = torch.cuda.is_available()
    if requested_device == "cuda" and not has_cuda:
        raise ValueError("CUDA indisponível nesta instalação do PyTorch.")
    if requested_device == "auto":
        requested_device = "cuda" if has_cuda else "cpu"
    device = torch.device(requested_device)
    dataset = read_dataset(root.resolve())
    labels, samples = dataset.labels, dataset.samples
    torch.manual_seed(seed)
    train_loader = DataLoader(
        TrainingPhotos(samples["train"], size, augmentation_rng=Random(seed) if augment else None),
        batch_size=batch_size, shuffle=True,
        generator=torch.Generator().manual_seed(seed),
    )
    val_loader = DataLoader(TrainingPhotos(samples["val"], size), batch_size=batch_size)
    model = build_classifier(len(labels), weights=WEIGHTS)
    model.requires_grad_(False)
    model.classifier[-1].requires_grad_(True)
    model.to(device).eval()
    learning_rate = 0.001
    optimizer = torch.optim.Adam(model.classifier[-1].parameters(), lr=learning_rate)
    preset = WEIGHTS.transforms()
    config = {
        "demo": demo, "architecture": ARCHITECTURE, "initial_weights": WEIGHTS.name,
        "epochs": epochs, "batch_size": batch_size, "learning_rate": learning_rate,
        "seed": seed, "device": str(device), "cuda_available": has_cuda, "class_ids": labels,
        "torch_version": str(torch.__version__), "torchvision_version": str(torchvision.__version__),
        "manifest_sha256": dataset.manifest_sha256,
        "image_counts": {key: len(value) for key, value in samples.items()},
        "augmentation": {
            "enabled": augment, "rotation_degrees": ROTATION_DEGREES,
            "brightness_range": list(BRIGHTNESS_RANGE), "scale_range": list(SCALE_RANGE),
            "horizontal_flip": False,
        },
        "preprocessing": {
            "size": size, "exif_orientation": True, "resize": "letterbox_lanczos",
            "padding_rgb": list(PADDING_COLOR), "scale": 255, "mean": preset.mean, "std": preset.std,
        },
    }
    print(f"Modo {'demonstração sintética' if demo else 'catálogo'} | dispositivo {device}", flush=True)
    output.mkdir(parents=True)
    (output / "run.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    best_loss = float("inf")
    with (output / "metrics.jsonl").open("w", encoding="utf-8") as log:
        for epoch in range(1, epochs + 1):
            train_loss, train_accuracy = _epoch(model, train_loader, device, optimizer)
            val_loss, val_accuracy = _epoch(model, val_loader, device)
            if not isfinite(train_loss) or not isfinite(val_loss):
                raise ValueError(f"Perda não finita na época {epoch}.")
            metrics = {
                "epoch": epoch, "train_loss": train_loss, "train_accuracy": train_accuracy,
                "val_loss": val_loss, "val_accuracy": val_accuracy,
            }
            print(json.dumps(metrics), flush=True)
            log.write(json.dumps(metrics) + "\n")
            log.flush()
            if val_loss < best_loss:
                best_loss = val_loss
                temporary_weights = output / "best.pt.tmp"
                torch.save({"state_dict": model.state_dict(), "config": config, "metrics": metrics}, temporary_weights)
                temporary_weights.replace(output / "best.pt")


def main() -> None:
    parser = argparse.ArgumentParser(description="Treina o classificador MobileNetV3 Small do MFI.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--dataset", type=Path)
    source.add_argument("--demo", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--size", type=int, default=DEFAULT_SIZE)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--augment", action="store_true", help="Aplica variações apenas no treino.")
    args = parser.parse_args()
    options = dict(
        epochs=args.epochs, batch_size=args.batch_size, size=args.size, seed=args.seed,
        requested_device=args.device, demo=args.demo, augment=args.augment,
    )
    try:
        if args.demo:
            with TemporaryDirectory(prefix="mfi-training-demo-") as demo_dir:
                root = Path(demo_dir)
                make_demo_dataset(root)
                train(root, args.output, **options)
        else:
            train(args.dataset, args.output, **options)
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        parser.exit(1, f"Erro no treinamento: {error}\n")


if __name__ == "__main__":
    main()
