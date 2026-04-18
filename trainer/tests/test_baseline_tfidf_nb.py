from trainer.config import tfidf_nb_model_config
from trainer.dataset.schema import SupervisedSample
from trainer.models.baseline_tfidf_nb import train_tfidf_nb_baseline


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


def test_tfidf_nb_baseline_can_fit_and_predict_probabilities() -> None:
    samples = [
        _sample("https://blog.alpha.example/", "Alpha Blog", "blog"),
        _sample("https://alpha.example/company", "Alpha Inc", "non_blog"),
        _sample("https://notes.beta.example/", "Beta Notes", "blog"),
        _sample("https://corp.beta.example/about", "About Beta", "non_blog"),
        _sample("https://journal.gamma.example/", "Gamma Journal", "blog"),
        _sample("https://gamma.example/team", "Gamma Team", "non_blog"),
    ]
    model = train_tfidf_nb_baseline(samples, tfidf_nb_model_config())

    probabilities = model.predict_proba(samples)

    assert len(probabilities) == 6
    assert all(0.0 <= probability <= 1.0 for probability in probabilities)
    assert "positive_weights" in model.feature_summary()
