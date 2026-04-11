from trainer.dataset.schema import SupervisedSample
from trainer.splits.group_split import assign_group_splits


def _sample(domain: str, label: str, suffix: str) -> SupervisedSample:
    return SupervisedSample(
        sample_id=f"https://{domain}/{suffix}",
        url=f"https://{domain}/{suffix}",
        normalized_url=f"https://{domain}/{suffix}",
        domain=domain,
        title=f"title-{suffix}",
        raw_labels=["blog" if label == "blog" else "others"],
        binary_label=label,
        resolution_status="mapped",
        resolution_reason="test",
        title_missing=False,
    )


def test_group_split_keeps_domains_in_one_split() -> None:
    samples = [
        _sample("a.example", "blog", "1"),
        _sample("a.example", "blog", "2"),
        _sample("b.example", "non_blog", "1"),
        _sample("c.example", "blog", "1"),
        _sample("d.example", "non_blog", "1"),
        _sample("e.example", "blog", "1"),
    ]

    assigned = assign_group_splits(samples, seed=7, ratios={"train": 0.7, "val": 0.15, "test": 0.15})
    domain_to_split = {}
    for sample in assigned:
        domain_to_split.setdefault(sample.domain, sample.split)
        assert domain_to_split[sample.domain] == sample.split
    assert {sample.split for sample in assigned} == {"train", "val", "test"}
