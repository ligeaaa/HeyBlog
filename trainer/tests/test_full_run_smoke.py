from pathlib import Path

from trainer.constants import DEFAULT_MODEL_ROOT
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
    assert full_run_dir.is_relative_to(DEFAULT_RUN_ROOT)
    assert (full_run_dir / "summary.json").exists()
    assert (full_run_dir / "report.md").exists()

    expected_models = {"structured", "structured_rf", "structured_svm", "tfidf", "tfidf_svm", "tfidf_nb"}
    seen_models: set[str] = set()
    for entry in result["results"]:
        run_dir = Path(entry["run_dir"])
        model_name = entry["model_name"]
        seen_models.add(model_name)
        assert run_dir.parent == DEFAULT_MODEL_ROOT / model_name
        assert run_dir.name.isdigit()
        assert len(run_dir.name) == 10
        assert (run_dir / "metrics.json").exists()
        assert (run_dir / "model.joblib").exists()
        assert (run_dir / "report.md").exists()

    assert expected_models == seen_models
