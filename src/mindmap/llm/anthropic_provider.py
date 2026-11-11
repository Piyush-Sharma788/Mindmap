"""The ONLY module that imports the Anthropic SDK.

- SDK automatic retries are disabled (max_retries=0): retries are decided by the
  engine's CallBudget, so every request that leaves this process is counted.
- Structured output: `output_config.format` with the schema from wire.provider_schema.
- No temperature/top_p: current Claude models reject sampling parameters.
- SDK exceptions are mapped to typed ProviderErrors; nothing is swallowed.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import anthropic

from mindmap.config import REQUEST_TIMEOUT_S
from mindmap.errors import (
    ConfigError,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimited,
    ProviderRequestRejected,
    ProviderTimeout,
    ProviderUnavailable,
)
from mindmap.llm.base import LLMRequest, LLMResponse, Usage

_CREDENTIAL_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE", "ANTHROPIC_FEDERATION_RULE_ID")


def credentials_available() -> bool:
    """True if the SDK has something to authenticate with (env var or an `ant auth login` profile)."""
    if any(os.environ.get(var) for var in _CREDENTIAL_ENV):
        return True
    return (Path.home() / ".config" / "anthropic").is_dir()


def _retry_after(exc: anthropic.APIStatusError) -> float | None:
    value = exc.response.headers.get("retry-after") if exc.response is not None else None
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, client: Any | None = None, *, timeout_s: float = REQUEST_TIMEOUT_S) -> None:
        if client is None:
            if not credentials_available():
                raise ConfigError(
                    "No Anthropic credentials found. Set ANTHROPIC_API_KEY (or run `ant auth login`)."
                )
            client = anthropic.Anthropic(max_retries=0, timeout=timeout_s)
        self.client = client

    def build_kwargs(self, request: LLMRequest) -> dict[str, Any]:
        system_block: dict[str, Any] = {"type": "text", "text": request.system}
        if request.cache_system_prompt:
            # Static system prompt is a reusable prefix across users. Below the model's minimum
            # cacheable size it is silently not cached (no error, no extra cost).
            system_block["cache_control"] = {"type": "ephemeral"}
        output_config: dict[str, Any] = {"format": {"type": "json_schema", "schema": request.schema}}
        if request.effort:
            output_config["effort"] = request.effort
        return {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "system": [system_block],
            "messages": request.messages,
            "output_config": output_config,
        }

    def complete(self, request: LLMRequest) -> LLMResponse:
        try:
            response = self.client.messages.create(**self.build_kwargs(request))
        except anthropic.APITimeoutError as exc:  # subclass of APIConnectionError: must come first
            raise ProviderTimeout(f"request timed out: {exc}") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderUnavailable(f"connection failed: {exc}") from exc
        except anthropic.RateLimitError as exc:
            raise ProviderRateLimited(f"rate limited (429): {exc}", retry_after_s=_retry_after(exc)) from exc
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
            raise ProviderAuthError(f"authentication/permission failed ({exc.status_code})") from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500 or exc.status_code in (408, 409):
                raise ProviderUnavailable(f"provider error {exc.status_code}: {exc}",
                                          retry_after_s=_retry_after(exc)) from exc
            raise ProviderRequestRejected(f"request rejected {exc.status_code}: {exc}") from exc
        except anthropic.AnthropicError as exc:
            raise ProviderError(f"provider failure: {type(exc).__name__}: {exc}") from exc
        except TypeError as exc:
            # The SDK raises a bare TypeError, before any network I/O, when it finds no usable
            # credential (e.g. an empty ~/.config/anthropic). Only that case is translated.
            if "authentication method" in str(exc):
                raise ConfigError("No usable Anthropic credentials. Set ANTHROPIC_API_KEY.") from exc
            raise

        text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
        u = response.usage
        return LLMResponse(
            text=text,
            stop_reason=response.stop_reason,
            model=response.model,
            usage=Usage(
                input_tokens=u.input_tokens or 0,
                output_tokens=u.output_tokens or 0,
                cache_creation_input_tokens=getattr(u, "cache_creation_input_tokens", None) or 0,
                cache_read_input_tokens=getattr(u, "cache_read_input_tokens", None) or 0,
            ),
            provider=self.name,
            request_id=getattr(response, "_request_id", None),
        )
