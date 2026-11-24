import argparse
import json
from collections.abc import Callable
from hashlib import file_digest
from pathlib import Path
from tempfile import TemporaryDirectory

from .classifier_dataset import make_demo_dataset
from .motor_classifier import ModelUnavailableError, MotorClassifier


def write_test_report(
    description: str, operation: Callable[[MotorClassifier, Path], dict[str, object]]
) -> dict[str, object]:
    """Executa um relatório sobre o mesmo dataset associado ao checkpoint."""
    parser = argparse.ArgumentParser(description=description)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--dataset", type=Path)
    source.add_argument("--demo", action="store_true")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        classifier = MotorClassifier(args.checkpoint)
        if args.demo != classifier.is_demo:
            raise ValueError("Use --demo com checkpoints sintéticos e --dataset com checkpoints reais.")
        if args.demo:
            with TemporaryDirectory(prefix="mfi-test-demo-") as temp:
                root = Path(temp)
                make_demo_dataset(root)
                report = operation(classifier, root)
        else:
            report = operation(classifier, args.dataset)
        with args.checkpoint.open("rb") as checkpoint:
            report["checkpoint_sha256"] = file_digest(checkpoint, "sha256").hexdigest()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8", newline="\n") as output:
            json.dump(report, output, indent=2, ensure_ascii=False)
            output.write("\n")
    except (OSError, ValueError, ModelUnavailableError, KeyError, TypeError) as error:
        parser.exit(1, f"Erro ao gerar o relatório: {error}\n")
    print(args.output)
    return report
