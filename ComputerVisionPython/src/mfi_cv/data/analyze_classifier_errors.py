from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

from PIL import ImageStat

from .classifier_dataset import read_test_dataset
from .classifier_report import write_test_report
from .motor_classifier import MotorClassifier
from .photo_files import open_photo


def _angle_sector(angle: object) -> str:
    if type(angle) not in (float, int) or not 0 <= angle < 360:
        return "unknown"
    lower = int(angle // 90) * 90
    return f"{lower}_to_under_{lower + 90}"


def _brightness(path: Path) -> tuple[str, float]:
    with open_photo(path) as photo:
        luminance = ImageStat.Stat(photo.convert("L")).mean[0]
    if luminance < 64:
        return "dark", luminance
    if luminance >= 192:
        return "bright", luminance
    return "mid", luminance


def _counts() -> Counter[str]:
    return Counter(images=0, incorrect_top1=0, unknown=0, needs_confirmation=0, accepted=0)


def _count(counts: Counter[str], wrong: bool, status: str) -> None:
    counts["images"] += 1
    counts["incorrect_top1"] += wrong
    counts[status] += 1


def analyze_errors(classifier: MotorClassifier, root: Path) -> dict[str, object]:
    """Agrupa erros e pedidos de revisão na partição de teste reservada."""
    dataset = read_test_dataset(root, classifier.class_ids, classifier.manifest_sha256)
    samples = dataset.samples["test"]
    reference_by_class: dict[str, str] = {}
    for path, label in samples:
        reference_by_class.setdefault(dataset.labels[label], dataset.metadata[path]["path"])

    totals = _counts()
    by_model = {label: _counts() for label in dataset.labels}
    by_angle = defaultdict(_counts)
    by_brightness = defaultdict(_counts)
    confusions: Counter[tuple[str, str]] = Counter()
    examples: dict[str, list[dict]] = {label: [] for label in dataset.labels}
    accepted_errors = 0
    for path, label in samples:
        actual = dataset.labels[label]
        entry = dataset.metadata[path]
        angle = entry.get("capture_angle_deg")
        sector = _angle_sector(angle)
        brightness_band, luminance = _brightness(path)
        prediction = classifier.predict(path)
        predicted = prediction["candidates"][0]["model_id"]
        status = prediction["status"]
        wrong = actual != predicted
        for counts in (totals, by_model[actual], by_angle[sector], by_brightness[brightness_band]):
            _count(counts, wrong, status)
        if wrong:
            confusions[actual, predicted] += 1
            accepted_errors += status == "accepted"
        if wrong or status != "accepted":
            examples[actual].append({
                "path": entry["path"],
                "source_path": entry.get("source_path"),
                "unit_id": entry["unit_id"],
                "session_id": entry["session_id"],
                "predicted_top1": predicted,
                "incorrect_top1": wrong,
                "status": status,
                "candidates": prediction["candidates"],
                "capture_angle_deg": angle if sector != "unknown" else None,
                "angle_sector": sector,
                "mean_luminance": round(luminance, 2),
                "brightness_band": brightness_band,
                "predicted_class_example": reference_by_class.get(predicted) if wrong else None,
            })

    limitations = [
        "O brilho médio descreve a imagem e também depende da superfície, do fundo e da exposição.",
        "As confusões indicam pares para comparação visual e não medem semelhança diretamente.",
        "Os casos unknown deste conjunto têm classe conhecida. A rejeição de classes novas exige dados próprios.",
    ]
    if classifier.is_demo:
        limitations.insert(0, "Demonstração sintética, sem evidência sobre motores reais.")
    missing_angles = by_angle.get("unknown", {}).get("images", 0)
    priorities = []
    if confusions:
        priorities.append("Compare as fotos dos pares confundidos e confira a placa e o rótulo.")
    if accepted_errors:
        priorities.append("Revise os erros aceitos antes de calibrar os limiares com dados reais.")
    if totals["unknown"] or totals["needs_confirmation"]:
        priorities.append("Revise enquadramento, placa visível e qualidade nos casos sem aceitação.")
    if missing_angles:
        limitations.append(f"Ângulo indisponível em {missing_angles} fotos.")
        priorities.append("Registre o ângulo nas próximas capturas e exportações para ampliar a análise.")
    if any(not counts["images"] for counts in by_model.values()):
        limitations.append("Algumas classes do checkpoint não têm exemplos na partição de teste.")

    return {
        "demo": classifier.is_demo,
        "split": "test",
        "manifest_sha256": dataset.manifest_sha256,
        "thresholds": asdict(classifier.thresholds),
        "totals": totals,
        "accepted_errors": accepted_errors,
        "by_model": {
            label: {"counts": counts, "examples": examples[label]} for label, counts in by_model.items()
        },
        "by_angle": dict(sorted(by_angle.items())),
        "by_brightness": dict(sorted(by_brightness.items())),
        "confusions": [
            {"actual": actual, "predicted": predicted, "count": count}
            for (actual, predicted), count in sorted(confusions.items(), key=lambda item: (-item[1], item[0]))
        ],
        "limitations": limitations,
        "review_priorities": priorities,
    }


def main() -> None:
    write_test_report("Agrupa erros e casos sem aceita??o do conjunto de teste.", analyze_errors)


if __name__ == "__main__":
    main()
