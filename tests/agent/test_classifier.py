from __future__ import annotations

from agent.classifier import BlogClassifier
from agent.config import AgentSettings
from agent.config import ProviderConfig
from agent.schema import BlogJudgeInput
from agent.schema import ProviderSelection


def _settings() -> AgentSettings:
    return AgentSettings(
        default_provider="openai",
        default_model="gpt-4o-mini",
        provider_configs={
            "openai": ProviderConfig(name="openai", model="gpt-4o-mini", api_key="key")
        },
    )


def test_classifier_parses_structured_json_response() -> None:
    def fake_completion(**kwargs):
        return {
            "choices": [
                {
                    "message": {
                        "content": '{"pred_label":"blog","reason":"personal writing homepage"}'
                    }
                }
            ]
        }

    classifier = BlogClassifier(
        _settings(),
        ProviderSelection(provider="openai", model="gpt-4o-mini", api_key="key"),
        completion_fn=fake_completion,
    )

    result = classifier.classify_one(
        BlogJudgeInput(url="https://example.com", title="My blog", page_text="Hello world")
    )

    assert result.pred_label == "blog"
    assert result.llm_status == "success"
    assert "personal writing" in result.reason


def test_classifier_surfaces_failure_as_null_prediction() -> None:
    def exploding_completion(**kwargs):
        raise RuntimeError("network failed")

    classifier = BlogClassifier(
        _settings(),
        ProviderSelection(provider="openai", model="gpt-4o-mini", api_key="key"),
        completion_fn=exploding_completion,
    )

    result = classifier.classify_one(
        BlogJudgeInput(url="https://example.com", title="My blog", page_text=None)
    )

    assert result.pred_label is None
    assert result.llm_status == "failed"
    assert "classification_failed" in result.reason
