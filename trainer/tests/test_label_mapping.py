from trainer.labeling.label_mapping import default_mapping
from trainer.labeling.resolution import resolve_labels


def test_label_mapping_defaults_resolve_blog_non_blog_and_excluded() -> None:
    mapping = default_mapping()

    blog = resolve_labels(["blog"], mapping)
    non_blog = resolve_labels(["others"], mapping)
    excluded = resolve_labels(["company"], mapping)
    conflict = resolve_labels(["blog", "others"], mapping)

    assert blog.binary_label == "blog"
    assert blog.resolution_status == "mapped"
    assert non_blog.binary_label == "non_blog"
    assert non_blog.resolution_status == "mapped"
    assert excluded.binary_label is None
    assert excluded.resolution_status == "excluded"
    assert conflict.binary_label is None
    assert conflict.resolution_status == "conflict_review"


def test_label_mapping_treats_mapped_plus_excluded_as_conflict_review() -> None:
    resolved = resolve_labels(["blog", "company"], default_mapping())

    assert resolved.binary_label is None
    assert resolved.resolution_status == "conflict_review"
