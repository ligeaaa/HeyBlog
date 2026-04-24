"""Environment-backed settings for the lightweight blog classification agent."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from agent.schema import ProviderSelection
from shared.config import DEFAULT_MAX_FETCHED_PAGE_BYTES
from shared.config import DEFAULT_REQUEST_TIMEOUT_SECONDS
from shared.config import DEFAULT_USER_AGENT

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "agent" / "evals"
_ENV_LOADED = False


def _strip_wrapping_quotes(value: str) -> str:
    """Remove matching single or double quotes around a value."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _load_dotenv(path: Path | None = None) -> None:
    """Load ``.env`` key-value pairs once without overriding shell values."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return

    env_path = path or (PROJECT_ROOT / ".env")
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key:
                continue
            os.environ.setdefault(key, _strip_wrapping_quotes(value.strip()))
    _ENV_LOADED = True


@dataclass(slots=True)
class ProviderConfig:
    """Store the model and credentials for one LLM provider.

    Args:
        name: Normalized provider name used in CLI selection and reports.
        model: Default model identifier for this provider.
        api_key: Credential used for calls to this provider.
        base_url: Optional custom base URL for OpenAI-compatible providers.
    """

    name: str
    model: str
    api_key: str
    base_url: str | None = None


@dataclass(slots=True)
class AgentSettings:
    """Store runtime settings for fetch, classification, and outputs.

    Args:
        default_provider: Provider chosen when the CLI does not override it.
        default_model: Fallback model when the CLI and provider config omit it.
        provider_configs: Mapping of normalized provider names to credentials.
        fetch_timeout_seconds: Per-request timeout for page fetching.
        fetch_max_concurrency: Maximum concurrent page fetches.
        classification_max_concurrency: Maximum concurrent LLM requests.
        classification_requests_per_minute: Global request budget for LLM calls.
        max_page_bytes: Maximum accepted page size for fetched HTML.
        user_agent: User-Agent sent during page fetches.
        output_root: Default directory for eval artifacts.
    """

    default_provider: str
    default_model: str
    provider_configs: dict[str, ProviderConfig]
    fetch_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS
    fetch_max_concurrency: int = 4
    classification_max_concurrency: int = 2
    classification_requests_per_minute: int = 60
    max_page_bytes: int = DEFAULT_MAX_FETCHED_PAGE_BYTES
    user_agent: str = DEFAULT_USER_AGENT
    output_root: Path = DEFAULT_OUTPUT_ROOT

    @classmethod
    def from_env(cls) -> "AgentSettings":
        """Build agent settings from environment variables.

        Returns:
            One validated settings object with provider credentials, fetch
            limits, classification limits, and artifact output paths.
        """
        _load_dotenv()
        provider_configs = _load_provider_configs()
        default_provider = os.getenv("AGENT_DEFAULT_PROVIDER", "").strip().lower()
        if not default_provider:
            if len(provider_configs) == 1:
                default_provider = next(iter(provider_configs))
            else:
                raise ValueError("AGENT_DEFAULT_PROVIDER is required when multiple providers are configured")
        if default_provider not in provider_configs:
            raise ValueError(f"default provider '{default_provider}' is not configured")
        default_model = os.getenv("AGENT_DEFAULT_MODEL", "").strip() or provider_configs[default_provider].model
        return cls(
            default_provider=default_provider,
            default_model=default_model,
            provider_configs=provider_configs,
            fetch_timeout_seconds=max(
                0.001,
                float(os.getenv("AGENT_FETCH_TIMEOUT_SECONDS", str(DEFAULT_REQUEST_TIMEOUT_SECONDS))),
            ),
            fetch_max_concurrency=max(1, int(os.getenv("AGENT_FETCH_MAX_CONCURRENCY", "4"))),
            classification_max_concurrency=max(
                1,
                int(os.getenv("AGENT_CLASSIFICATION_MAX_CONCURRENCY", "2")),
            ),
            classification_requests_per_minute=max(
                1,
                int(os.getenv("AGENT_CLASSIFICATION_REQUESTS_PER_MINUTE", "60")),
            ),
            max_page_bytes=max(
                1,
                int(os.getenv("AGENT_MAX_PAGE_BYTES", str(DEFAULT_MAX_FETCHED_PAGE_BYTES))),
            ),
            user_agent=os.getenv("AGENT_USER_AGENT", DEFAULT_USER_AGENT),
            output_root=Path(os.getenv("AGENT_OUTPUT_ROOT", str(DEFAULT_OUTPUT_ROOT))),
        )

    def resolve_provider(self, *, provider: str | None = None, model: str | None = None) -> ProviderSelection:
        """Resolve one concrete provider config for a run.

        Args:
            provider: Optional CLI/provider override.
            model: Optional model override for the selected provider.

        Returns:
            One provider config with the chosen provider name and model.
        """
        resolved_provider = (provider or self.default_provider).strip().lower()
        if resolved_provider not in self.provider_configs:
            raise ValueError(f"provider '{resolved_provider}' is not configured")
        config = self.provider_configs[resolved_provider]
        return ProviderSelection(
            provider=config.name,
            model=(model or config.model or self.default_model).strip(),
            api_key=config.api_key,
            base_url=config.base_url,
        )


def _load_provider_configs() -> dict[str, ProviderConfig]:
    """Parse provider credentials from environment variables.

    Returns:
        A mapping keyed by normalized provider name.

    Raises:
        ValueError: If a provider block is partially configured or no providers
            are configured at all.
    """
    discovered: dict[str, dict[str, str]] = {}
    known_suffixes = ("BASE_URL", "API_KEY", "MODEL")
    for key, value in os.environ.items():
        if not key.startswith("AGENT_PROVIDER_"):
            continue
        suffix = key[len("AGENT_PROVIDER_") :]
        matched_suffix = next((candidate for candidate in known_suffixes if suffix.endswith(f"_{candidate}")), None)
        if matched_suffix is None:
            continue
        provider_name = suffix[: -(len(matched_suffix) + 1)].strip().lower()
        if not provider_name:
            continue
        provider_fields = discovered.setdefault(provider_name, {})
        provider_fields[matched_suffix.lower()] = value.strip()

    configs: dict[str, ProviderConfig] = {}
    for provider_name, fields in discovered.items():
        model = fields.get("model", "").strip()
        api_key = fields.get("api_key", "").strip()
        base_url = fields.get("base_url", "").strip() or None
        if not model or not api_key:
            raise ValueError(
                f"provider '{provider_name}' must define both AGENT_PROVIDER_{provider_name.upper()}_MODEL "
                f"and AGENT_PROVIDER_{provider_name.upper()}_API_KEY"
            )
        configs[provider_name] = ProviderConfig(
            name=provider_name,
            model=model,
            api_key=api_key,
            base_url=base_url,
        )

    if not configs:
        raise ValueError("at least one AGENT_PROVIDER_<NAME>_MODEL/API_KEY pair must be configured")
    return configs
