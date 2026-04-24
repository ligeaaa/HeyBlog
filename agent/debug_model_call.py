"""Simple CLI for testing one direct LiteLLM model call."""

from __future__ import annotations

import argparse
import json
from typing import Any

from agent.config import AgentSettings


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the direct model-call debug script."""
    parser = argparse.ArgumentParser(description="Run one direct LiteLLM model call for debugging.")
    parser.add_argument(
        "--provider",
        type=str,
        default=None,
        help="Optional provider override. Defaults to AGENT_DEFAULT_PROVIDER from env.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Optional model override. Defaults to AGENT_DEFAULT_MODEL or the provider default from env.",
    )
    parser.add_argument(
        "--message",
        type=str,
        default="Reply with exactly: ok",
        help="User message sent to the model.",
    )
    parser.add_argument(
        "--system",
        type=str,
        default="You are a concise assistant. Follow the user's instruction exactly.",
        help="Optional system prompt.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=128,
        help="Maximum completion tokens for the debug request.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Sampling temperature for the debug request.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable LiteLLM internal debug logging.",
    )
    return parser


def run_debug_model_call(
    *,
    provider: str | None = None,
    model: str | None = None,
    message: str,
    system: str,
    max_tokens: int,
    temperature: float,
    debug: bool = False,
) -> dict[str, Any]:
    """Run one direct model call and return a structured debug payload.

    Args:
        provider: Optional provider override.
        model: Optional model override.
        message: User prompt sent to the model.
        system: System prompt sent before the user message.
        max_tokens: Maximum completion tokens for the request.
        temperature: Sampling temperature for the request.
        debug: Whether to enable LiteLLM debug logging.

    Returns:
        A JSON-serializable payload including the resolved config, raw assistant
        content, and the raw LiteLLM response when possible.
    """
    settings = AgentSettings.from_env()
    selection = settings.resolve_provider(provider=provider, model=model)

    try:
        import litellm
        from litellm import completion
    except ImportError as exc:  # pragma: no cover - only triggered when optional deps are missing.
        raise RuntimeError("litellm is not installed; run `pip install -e '.[agent]'` first") from exc

    if debug:
        litellm._turn_on_debug()

    response = completion(
        model=selection.model,
        custom_llm_provider=selection.provider,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": message},
        ],
        api_key=selection.api_key,
        api_base=selection.base_url,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    assistant_content = _extract_content(response)
    return {
        "resolved_provider": selection.provider,
        "resolved_model": selection.model,
        "resolved_api_base": selection.base_url,
        "assistant_content": assistant_content,
        "raw_response": _to_jsonable(response),
    }


def _extract_content(response: Any) -> str | None:
    """Extract assistant text from a LiteLLM-like response object."""
    if isinstance(response, dict):
        choices = response.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content")
        return None
    choices = getattr(response, "choices", None)
    if not choices:
        return None
    message = getattr(choices[0], "message", None)
    return getattr(message, "content", None)


def _to_jsonable(response: Any) -> Any:
    """Convert a LiteLLM response into a JSON-serializable object."""
    if isinstance(response, dict):
        return response
    model_dump = getattr(response, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    dict_method = getattr(response, "dict", None)
    if callable(dict_method):
        return dict_method()
    return repr(response)


def main() -> None:
    """Run the CLI entrypoint for direct model-call debugging."""
    args = _build_arg_parser().parse_args()
    result = run_debug_model_call(
        provider=args.provider,
        model=args.model,
        message=args.message,
        system=args.system,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        debug=args.debug,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
