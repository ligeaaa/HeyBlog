from trainer.config import structured_lr_model_config
from trainer.config import tfidf_lr_model_config
from trainer.dataset.schema import SupervisedSample
from trainer.models.registry import train_model


def _sample(url: str, title: str, label: str) -> SupervisedSample:
    domain = url.split("/")[2]
    return SupervisedSample(
        sample_id=url,
        url=url,
        normalized_url=url,
        domain=domain,
        title=title,
        raw_labels=["blog" if label == "blog" else "others"],
        binary_label=label,
        resolution_status="mapped",
        resolution_reason="test",
        title_missing=not bool(title),
        split="train",
    )


def test_structured_lr_alias_preserves_explicit_model_name() -> None:
    samples = [
        _sample("https://blog.alpha.example/", "Alpha Blog", "blog"),
        _sample("https://alpha.example/company", "Alpha Inc", "non_blog"),
        _sample("https://notes.beta.example/", "Beta Notes", "blog"),
        _sample("https://corp.beta.example/about", "About Beta", "non_blog"),
    ]

    model = train_model("structured_lr", samples, structured_lr_model_config())

    assert model.model_name == "structured_lr"
    assert len(model.predict_proba(samples)) == 4


def test_tfidf_lr_alias_preserves_explicit_model_name() -> None:
    samples = [
        _sample("https://blog.alpha.example/", "Alpha Blog", "blog"),
        _sample("https://alpha.example/company", "Alpha Inc", "non_blog"),
        _sample("https://notes.beta.example/", "Beta Notes", "blog"),
        _sample("https://corp.beta.example/about", "About Beta", "non_blog"),
    ]

    model = train_model("tfidf_lr", samples, tfidf_lr_model_config())

    assert model.model_name == "tfidf_lr"
    assert len(model.predict_proba(samples)) == 4
