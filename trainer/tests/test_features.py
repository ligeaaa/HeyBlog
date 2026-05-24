from trainer.dataset.schema import SupervisedSample
from trainer.features.assemble import build_tfidf_documents
from trainer.features.page_features import extract_page_features
from trainer.features.page_features import page_signal_tokens
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
            text="RSS 归档 标签 友链 2024",
        )
    ]

    _, title_docs = build_tfidf_documents(
        samples,
        url_char_ngram_range=(3, 3),
        title_word_ngram_range=(1, 2),
        title_token_chunk_size=2,
    )

    assert "ab 12" in title_docs[0]
    assert "page_blog_signal:feed" in title_docs[0]
    assert "page_blog_signal:friend_links" in title_docs[0]


def test_page_features_capture_blog_and_company_signals() -> None:
    html = """
    <html><head><link rel="alternate" href="/feed.xml"></head>
    <body><article class="h-entry">2024-01-02 归档 标签 友链 评论</article></body></html>
    """

    features = extract_page_features(html)
    tokens = page_signal_tokens(html)

    assert features["page:html_present"] == 1.0
    assert features["page:feed_link_count"] == 1.0
    assert features["page:blog_signal:archive"] >= 1.0
    assert features["page:blog_signal:taxonomy"] >= 1.0
    assert "page_blog_signal:archive" in tokens


def test_page_features_capture_non_blog_signals() -> None:
    features = extract_page_features("Company pricing products careers privacy policy")

    assert features["page:non_blog_signal:company"] >= 1.0
    assert features["page:non_blog_signal:commerce"] >= 1.0
    assert features["page:non_blog_signal:career"] >= 1.0
