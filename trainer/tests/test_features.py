from trainer.features.title_features import extract_title_features
from trainer.features.url_features import extract_url_features


def test_feature_extractors_handle_missing_title_and_url_keywords() -> None:
    url_features = extract_url_features("https://blog.example.com/archive/2024/post")
    title_features = extract_title_features("")

    assert url_features["url:path_depth"] == 3.0
    assert url_features["url:kw:blog"] == 1.0
    assert url_features["url:kw:archive"] == 1.0
    assert title_features["title:missing"] == 1.0
    assert title_features["title:token_count"] == 0.0
