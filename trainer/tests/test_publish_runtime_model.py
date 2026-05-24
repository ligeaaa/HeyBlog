import json
from pathlib import Path

from trainer.pipelines.publish_runtime_model import publish_runtime_model


def test_publish_runtime_model_copies_artifacts_and_writes_manifest(tmp_path: Path) -> None:
    run_dir = tmp_path / "data" / "model" / "tfidf_svm" / "2605231457"
    run_dir.mkdir(parents=True)
    (run_dir / "model.joblib").write_bytes(b"model")
    (run_dir / "config.json").write_text(
        json.dumps(
            {
                "model_name": "tfidf_svm",
                "dataset_dir": "data/trainer/datasets/example",
                "selected_threshold": {"threshold": 0.63, "val_f1": 0.85, "val_samples": 100},
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "metrics.json").write_text(json.dumps({"f1": 0.87}), encoding="utf-8")
    runtime_root = tmp_path / "runtime_resources" / "models" / "url_decision" / "current"

    manifest = publish_runtime_model(run_dir=run_dir, runtime_root=runtime_root)

    destination = runtime_root / "tfidf_svm" / "2605231457"
    assert manifest["destination"] == str(destination)
    assert manifest["selected_threshold"]["threshold"] == 0.63
    assert (destination / "model.joblib").read_bytes() == b"model"
    assert (destination / "runtime_manifest.json").exists()
    assert (runtime_root / "latest_manifest.json").exists()
