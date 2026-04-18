import json
from pathlib import Path

from trainer.config import DatasetConfig
from trainer.pipelines.prepare_dataset import default_dataset_version
from trainer.pipelines.prepare_dataset import run_prepare_dataset


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_run_prepare_dataset_writes_expected_artifacts(tmp_path: Path) -> None:
    source = tmp_path / "labels.csv"
    source.write_text(
        "\n".join(
            [
                "url,title,label",
                "https://blog.alpha.example/,Alpha Blog,blog",
                "https://blog.alpha.example/,,blog",
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
    config = DatasetConfig(source_csv=source, dataset_root=tmp_path / "datasets")

    result = run_prepare_dataset(source_csv=source, config=config)

    dataset_dir = Path(result["dataset_dir"])
    dataset_version = default_dataset_version(source)
    resolution_rows = _read_jsonl(dataset_dir / "label_resolution.jsonl")
    supervised_rows = _read_jsonl(dataset_dir / "full_supervised.jsonl")
    split_rows = {
        split: _read_jsonl(dataset_dir / f"{split}.jsonl")
        for split in ("train", "val", "test")
    }

    assert result["dataset_version"] == dataset_version
    assert dataset_dir == config.dataset_root / dataset_version
    assert (dataset_dir / "raw_export.csv").read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
    assert len(resolution_rows) == 6
    assert len(supervised_rows) == 6
    assert sum(len(rows) for rows in split_rows.values()) == len(supervised_rows)
    assert {row["sample_id"] for row in supervised_rows} == {
        row["sample_id"]
        for rows in split_rows.values()
        for row in rows
    }
    assert all(rows for rows in split_rows.values())
    assert _read_json(dataset_dir / "dataset_config.json")["dataset_version"] == dataset_version
    assert _read_json(dataset_dir / "dataset_stats.json") == result["dataset_stats"]
    assert _read_json(dataset_dir / "split_manifest.json") == result["split_manifest"]
