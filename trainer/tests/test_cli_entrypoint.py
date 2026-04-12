import json
import subprocess
import sys
from pathlib import Path

from trainer import cli

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_SCRIPT = REPO_ROOT / "trainer" / "cli.py"


def test_main_defaults_to_prepare_dataset(monkeypatch, capsys) -> None:
    calls: list[tuple[Path | None, str | None]] = []

    def fake_run_full_pipeline(*, source_csv: Path | None = None, dataset_version: str | None = None) -> dict[str, str]:
        calls.append((source_csv, dataset_version))
        return {"dataset_dir": "tmp/dataset", "full_run_dir": "tmp/run"}

    monkeypatch.setattr(cli, "run_full_pipeline", fake_run_full_pipeline)

    exit_code = cli.main([])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert calls == [(None, None)]
    assert json.loads(captured.out) == {
        "dataset_dir": "tmp/dataset",
        "full_run_dir": "tmp/run",
    }


def test_direct_script_launch_supports_help() -> None:
    result = subprocess.run(
        [sys.executable, str(CLI_SCRIPT), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "prepare-dataset" in result.stdout
    assert "full-run" in result.stdout
