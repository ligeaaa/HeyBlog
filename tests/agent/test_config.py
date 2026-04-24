from __future__ import annotations

import os

import pytest

from agent.config import AgentSettings


def test_agent_settings_load_multiple_provider_configs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_DEFAULT_PROVIDER", "openai")
    monkeypatch.setenv("AGENT_PROVIDER_OPENAI_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("AGENT_PROVIDER_OPENAI_API_KEY", "key-openai")
    monkeypatch.setenv("AGENT_PROVIDER_OPENROUTER_MODEL", "openai/gpt-4o-mini")
    monkeypatch.setenv("AGENT_PROVIDER_OPENROUTER_API_KEY", "key-openrouter")
    monkeypatch.setenv("AGENT_PROVIDER_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

    settings = AgentSettings.from_env()

    assert settings.default_provider == "openai"
    assert settings.provider_configs["openai"].model == "gpt-4o-mini"
    assert settings.provider_configs["openrouter"].base_url == "https://openrouter.ai/api/v1"


def test_agent_settings_fail_fast_on_incomplete_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_DEFAULT_PROVIDER", raising=False)
    monkeypatch.setenv("AGENT_PROVIDER_OPENAI_MODEL", "gpt-4o-mini")
    monkeypatch.delenv("AGENT_PROVIDER_OPENAI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="must define both"):
        AgentSettings.from_env()


@pytest.fixture(autouse=True)
def clear_agent_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("AGENT_"):
            monkeypatch.delenv(key, raising=False)
