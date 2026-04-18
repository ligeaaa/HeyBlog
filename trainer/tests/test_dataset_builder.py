from trainer.dataset.builder import aggregate_rows
from trainer.dataset.builder import build_resolution_records
from trainer.dataset.builder import build_supervised_samples
from trainer.dataset.schema import RawLabelRow
from trainer.labeling.label_mapping import default_mapping


def test_dataset_builder_aggregates_duplicate_urls_before_resolution() -> None:
    rows = [
        RawLabelRow(url="https://blog.example.com/", title="Alpha", label="blog"),
        RawLabelRow(url="https://blog.example.com/", title="", label="others"),
        RawLabelRow(url="https://solo.example.com/", title="Solo", label="blog"),
    ]
    mapping = default_mapping()

    aggregated = aggregate_rows(rows, mapping)
    resolutions = build_resolution_records(aggregated, mapping)
    supervised = build_supervised_samples(resolutions)

    assert len(aggregated) == 2
    assert len(supervised) == 1
    assert supervised[0].url == "https://solo.example.com/"
    assert any(record.resolution_status == "conflict_review" for record in resolutions)
