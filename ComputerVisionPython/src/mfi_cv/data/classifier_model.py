import torch
from PIL import Image
from torch import Tensor, nn
from torchvision.models import MobileNetV3, MobileNet_V3_Small_Weights, mobilenet_v3_small

from .preprocessing import normalize_rgb

ARCHITECTURE = "mobilenet_v3_small"


def build_classifier(
    class_count: int, weights: MobileNet_V3_Small_Weights | None = None
) -> MobileNetV3:
    model = mobilenet_v3_small(weights=weights)
    model.classifier[-1] = nn.Linear(model.classifier[-1].in_features, class_count)
    return model


def standardize_image(photo: Image.Image, mean: Tensor, std: Tensor) -> Tensor:
    pixels = torch.frombuffer(normalize_rgb(photo), dtype=torch.float32)
    return (pixels.view(3, photo.height, photo.width) - mean) / std
