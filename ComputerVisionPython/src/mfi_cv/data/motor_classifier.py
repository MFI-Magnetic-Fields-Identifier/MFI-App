import argparse
import json
import sys
from contextlib import ExitStack
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from pickle import UnpicklingError
from typing import Literal, TypedDict

import torch
from PIL import Image

from .classifier_model import ARCHITECTURE, build_classifier, standardize_image
from .photo_files import open_photo
from .preprocessing import PADDING_COLOR, prepare_image

PredictionStatus = Literal["accepted", "needs_confirmation", "unknown"]


class Candidate(TypedDict):
    model_id: str
    score: float


class Prediction(TypedDict):
    candidates: list[Candidate]
    status: PredictionStatus


class ModelUnavailableError(RuntimeError):
    """O checkpoint está ausente, ilegível ou incompatível."""


class InvalidPhotoError(ValueError):
    """A fotografia está ausente, ilegível ou em formato incompatível."""


@dataclass(frozen=True)
class DecisionThresholds:
    rejection: float = 0.60
    acceptance: float = 0.85
    margin: float = 0.15

    def __post_init__(self) -> None:
        if not 0 <= self.rejection <= self.acceptance <= 1:
            raise ValueError("Use 0 <= rejeição <= aceitação <= 1.")
        if not 0 <= self.margin <= 1:
            raise ValueError("Use uma margem entre 0 e 1.")

    def classify(self, first: float, second: float) -> PredictionStatus:
        if first < self.rejection:
            return "unknown"
        if first >= self.acceptance and first - second >= self.margin:
            return "accepted"
        return "needs_confirmation"


def _normalization_values(values: object, name: str) -> list[float]:
    if not isinstance(values, (list, tuple)) or len(values) != 3 or any(
        type(value) not in (float, int) or not isfinite(value) for value in values
    ):
        raise ValueError(f"Normalização {name} inválida.")
    return [float(value) for value in values]


class MotorClassifier:
    """Carrega um checkpoint do MFI e classifica fotografias em CPU."""

    def __init__(
        self, checkpoint: str | Path, *, thresholds: DecisionThresholds = DecisionThresholds()
    ) -> None:
        path = Path(checkpoint)
        try:
            data = torch.load(path, map_location="cpu", weights_only=True)
            config = data["config"]
            if config["architecture"] != ARCHITECTURE:
                raise ValueError("Arquitetura incompatível.")
            labels = config["class_ids"]
            if not isinstance(labels, list) or len(labels) < 2 or any(
                not isinstance(label, str) or not label.strip() for label in labels
            ) or len(set(labels)) != len(labels):
                raise ValueError("O checkpoint deve registrar pelo menos duas classes únicas.")

            recipe = config["preprocessing"]
            size = recipe["size"]
            if (
                type(size) is not int or size < 1
                or recipe["exif_orientation"] is not True
                or recipe["resize"] != "letterbox_lanczos"
                or recipe["padding_rgb"] != list(PADDING_COLOR)
                or recipe["scale"] != 255
            ):
                raise ValueError("Receita de pré-processamento incompatível.")
            mean = _normalization_values(recipe["mean"], "mean")
            std = _normalization_values(recipe["std"], "std")
            if any(value <= 0 for value in std):
                raise ValueError("O desvio padrão precisa ser positivo nos três canais.")

            model = build_classifier(len(labels))
            model.load_state_dict(data["state_dict"])
        except (OSError, EOFError, UnpicklingError, RuntimeError, KeyError, TypeError, ValueError) as error:
            raise ModelUnavailableError(f"Checkpoint indisponível ou incompatível: {path}. {error}") from error

        self.model = model.eval()
        self.class_ids = tuple(labels)
        self.is_demo = config.get("demo") is True
        self.manifest_sha256: str | None = config.get("manifest_sha256")
        self.size = size
        self.mean = torch.tensor(mean, dtype=torch.float32).view(3, 1, 1)
        self.std = torch.tensor(std, dtype=torch.float32).view(3, 1, 1)
        self.thresholds = thresholds

    def predict(self, image: str | Path, *, top_k: int = 3) -> Prediction:
        path = Path(image)
        with ExitStack() as resources:
            try:
                photo = resources.enter_context(open_photo(path))
            except (OSError, ValueError) as error:
                raise InvalidPhotoError(f"Fotografia inválida: {path}. {error}") from error
            return self.predict_photo(photo, top_k=top_k)

    @torch.inference_mode()
    def predict_photo(self, photo: Image.Image, *, top_k: int = 3) -> Prediction:
        if type(top_k) is not int or top_k < 1:
            raise ValueError("Top-K deve ser um inteiro positivo.")
        rgb = prepare_image(photo, size=self.size)
        tensor = standardize_image(rgb, self.mean, self.std)
        scores = self.model(tensor.unsqueeze(0)).softmax(dim=1)[0].tolist()
        if not all(isfinite(score) for score in scores):
            raise ModelUnavailableError("O modelo produziu pontuações não finitas.")
        # A ordem das classes do checkpoint desempata pontuações idênticas.
        ranked = sorted(range(len(scores)), key=scores.__getitem__, reverse=True)
        status = self.thresholds.classify(scores[ranked[0]], scores[ranked[1]])
        candidates = [
            Candidate(model_id=self.class_ids[index], score=scores[index])
            for index in ranked[:top_k]
        ]
        return Prediction(candidates=candidates, status=status)


def main() -> None:
    parser = argparse.ArgumentParser(description="Lista os modelos candidatos para uma fotografia.")
    parser.add_argument("image", type=Path)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--reject-below", type=float, default=DecisionThresholds.rejection)
    parser.add_argument("--accept-at", type=float, default=DecisionThresholds.acceptance)
    parser.add_argument("--min-margin", type=float, default=DecisionThresholds.margin)
    args = parser.parse_args()
    try:
        thresholds = DecisionThresholds(args.reject_below, args.accept_at, args.min_margin)
        classifier = MotorClassifier(args.checkpoint, thresholds=thresholds)
        prediction = classifier.predict(args.image, top_k=args.top_k)
    except (ModelUnavailableError, ValueError) as error:
        parser.exit(1, f"Erro na identificação: {error}\n")
    if classifier.is_demo:
        print("Checkpoint de demonstração sintética. Classes de teste.", file=sys.stderr)
    print(json.dumps(prediction, indent=2))


if __name__ == "__main__":
    main()
