from trainer.dataset.schema import SupervisedSample
from trainer.features.assemble import build_tfidf_documents
from trainer.features.title_features import extract_title_features
from trainer.features.title_features import tokenize_title_char_chunks
from trainer.features.url_features import extract_url_features


def test_feature_extractors_handle_missing_title_and_url_keywords() -> None:
    url_features = extract_url_features("https://blog.example.com/archive/2024/post")
    title_features = extract_title_features("")

    assert url_features["url:path_depth"] == 3.0
    assert url_features["url:kw:blog"] == 1.0
    assert url_features["url:kw:archive"] == 1.0
    assert title_features["title:missing"] == 1.0
    assert title_features["title:token_count"] == 0.0


def test_title_char_chunk_tokenizer_keeps_only_alnum_and_cjk() -> None:
    assert tokenize_title_char_chunks("AB-12_中文!", chunk_size=2) == ["ab", "12", "中文"]


def test_build_tfidf_documents_uses_title_char_chunks_for_new_models() -> None:
    samples = [
        SupervisedSample(
            sample_id="sample-1",
            url="https://example.com/post",
            normalized_url="https://example.com/post",
            domain="example.com",
            title="AB-12_中文!",
            raw_labels=["blog"],
            binary_label="blog",
            resolution_status="mapped",
            resolution_reason="test",
            title_missing=False,
            split="train",
        )
    ]

    _, title_docs = build_tfidf_documents(
        samples,
        url_char_ngram_range=(3, 3),
        title_word_ngram_range=(1, 2),
        title_token_chunk_size=2,
    )

    assert title_docs == [["ab", "12", "中文", "ab 12", "12 中文"]]
