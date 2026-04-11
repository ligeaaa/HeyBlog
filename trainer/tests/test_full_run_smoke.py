from pathlib import Path

from trainer.config import DatasetConfig
from trainer.constants import DEFAULT_RUN_ROOT
from trainer.pipelines.full_run import run_full_pipeline
from trainer.pipelines.prepare_dataset import default_dataset_version


def test_full_run_smoke(tmp_path: Path) -> None:
    source = tmp_path / "labels.csv"
    source.write_text(
        "\n".join(
            [
                "url,title,label",
                "https://blog.alpha.example/,Alpha Blog,blog",
                "https://alpha.example/company,Alpha Inc,others",
                "https://notes.beta.example/,Beta Notes,blog",
                "https://beta.example/about,About Beta,others",
                "https://journal.gamma.example/,Gamma Journal,blog",
                "https://gamma.example/team,Gamma Team,others",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_full_pipeline(
        source_csv=source,
        dataset_version=default_dataset_version(source),
    )

    dataset_dir = Path(result["dataset_dir"])
    full_run_dir = Path(result["full_run_dir"])

    assert (dataset_dir / "label_resolution.jsonl").exists()
    assert (dataset_dir / "split_manifest.json").exists()
    assert (full_run_dir / "structured" / "metrics.json").exists()
    assert (full_run_dir / "structured" / "model.joblib").exists()
    assert (full_run_dir / "tfidf" / "report.md").exists()
