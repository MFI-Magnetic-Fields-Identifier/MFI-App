import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("arguments", "exit_code", "stream", "expected"),
    [
        ((), 0, "stdout", "MFI CV: ambiente Python pronto."),
        (("--help",), 0, "stdout", "usage:"),
        (("--invalido",), 2, "stderr", "--invalido"),
    ],
)
def test_module_command(
    tmp_path: Path,
    arguments: tuple[str, ...],
    exit_code: int,
    stream: str,
    expected: str,
) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "mfi_cv", *arguments],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == exit_code
    output = result.stdout if stream == "stdout" else result.stderr
    assert expected in output
