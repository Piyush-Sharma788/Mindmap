"""Google Gemini provider (official `google-genai` SDK). The ONLY module importing it.

- One request per `complete()`: the SDK is configured with HttpRetryOptions(attempts=1).
  (The SDK's default is already a single attempt; setting it explicitly also turns off the
  async-only implicit connection retry, and makes the setting testable.) Retries are decided
  by the engine's CallBudget, as for every provider.
- Structured output: response_mime_type=application/json + response_json_schema, using the
  SAME schema as every provider (wire.provider_schema), with one mechanical rewrite that the
  Gemini docs specify: nullable `anyOf: [{type: X}, {type: null}]` -> `type: [X, "null"]`.
- Safety blocks and token-limit stops are reported as stop reasons ("refusal" /
  "max_tokens"), never turned into output. API errors map to typed ProviderErrors.
- Thinking uses the model's default (not configured). `effort` is an Anthropic parameter and
  is ignored here.
"""

from __future__ import annotations

import copy
import os
import re
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

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

_TIMEOUT_EXC: tuple[type[BaseException], ...] = ()
_TRANSPORT_EXC: tuple[type[BaseException], ...] = ()
for _mod_name in ("httpx", "httpx2"):
    try:
        _mod = __import__(_mod_name)
        _TIMEOUT_EXC += (_mod.TimeoutException,)
        _TRANSPORT_EXC += (_mod.TransportError,)
    except ImportError:  # pragma: no cover - depends on installed extras
        pass

# Finish reasons that mean "the model declined / was blocked": treated like an Anthropic refusal.
_BLOCK_REASONS = {"SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "RECITATION", "IMAGE_SAFETY"}
_RETRY_DELAY = re.compile(r"^(\d+(?:\.\d+)?)s$")


def gemini_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Rewrite nullable anyOf into Gemini's documented `type: [X, "null"]` form. Nothing else."""

    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(item) for item in node]
        if not isinstance(node, dict):
            return node
        out = {key: walk(value) for key, value in node.items()}
        options = out.get("anyOf")
        if isinstance(options, list) and len(options) == 2:
            types_ = [o.get("type") for o in options if isinstance(o, dict) and set(o) == {"type"}]
            if len(types_) == 2 and "null" in types_ and all(isinstance(t, str) for t in types_):
                other = next(t for t in types_ if t != "null")
                del out["anyOf"]
                out["type"] = [other, "null"]
        return out

    return walk(copy.deepcopy(schema))


def _retry_after(exc: genai_errors.APIError) -> float | None:
    """Parse google.rpc.RetryInfo ('retryDelay': '17s') from the error body, if present."""
    details = exc.details.get("error", {}).get("details", []) if isinstance(exc.details, dict) else []
    for item in details if isinstance(details, list) else []:
        if isinstance(item, dict) and str(item.get("@type", "")).endswith("RetryInfo"):
            match = _RETRY_DELAY.match(str(item.get("retryDelay", "")))
            if match:
                return float(match.group(1))
    return None


def api_key_from_env() -> str | None:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or None


class GeminiProvider:
    name = "gemini"

    def __init__(self, client: Any | None = None, *, timeout_s: float = REQUEST_TIMEOUT_S) -> None:
        if client is None:
            api_key = api_key_from_env()
            if not api_key:
                raise ConfigError("No Gemini credentials found. Set GEMINI_API_KEY (in the environment or .env).")
            client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(
                    timeout=int(timeout_s * 1000),  # SDK unit: milliseconds
                    retry_options=types.HttpRetryOptions(attempts=1),  # no SDK retries
                ),
            )
        self.client = client

    def build_kwargs(self, request: LLMRequest) -> dict[str, Any]:
        contents = [
            types.Content(role="model" if m["role"] == "assistant" else "user",
                          parts=[types.Part(text=str(m["content"]))])
            for m in request.messages
        ]
        config = types.GenerateContentConfig(
            system_instruction=request.system,
            response_mime_type="application/json",
            response_json_schema=gemini_schema(request.schema),
            max_output_tokens=request.max_tokens,
            candidate_count=1,
        )
        return {"model": request.model, "contents": contents, "config": config}

    def complete(self, request: LLMRequest) -> LLMResponse:
        try:
            response = self.client.models.generate_content(**self.build_kwargs(request))
        except genai_errors.APIError as exc:
            raise _map_api_error(exc) from exc
        except _TIMEOUT_EXC as exc:
            raise ProviderTimeout(f"request timed out: {type(exc).__name__}") from exc
        except _TRANSPORT_EXC as exc:
            raise ProviderUnavailable(f"connection failed: {type(exc).__name__}") from exc

        text, stop_reason = _extract(response)
        u = response.usage_metadata
        prompt = (getattr(u, "prompt_token_count", None) or 0) if u else 0
        cached = (getattr(u, "cached_content_token_count", None) or 0) if u else 0
        candidates = (getattr(u, "candidates_token_count", None) or 0) if u else 0
        thoughts = (getattr(u, "thoughts_token_count", None) or 0) if u else 0
        return LLMResponse(
            text=text,
            stop_reason=stop_reason,
            model=getattr(response, "model_version", None) or request.model,
            usage=Usage(
                input_tokens=max(prompt - cached, 0),  # prompt_token_count includes cached tokens
                output_tokens=candidates + thoughts,  # thinking is billed as output
                cache_read_input_tokens=cached,
            ),
            provider=self.name,
            request_id=getattr(response, "response_id", None),
            extra={"thoughts_token_count": thoughts},
        )


def _extract(response: Any) -> tuple[str, str]:
    """Return (text, normalised stop_reason) without ever inventing text."""
    candidates = getattr(response, "candidates", None) or []
    feedback = getattr(response, "prompt_feedback", None)
    if not candidates:
        if feedback is not None and getattr(feedback, "block_reason", None):
            return "", "refusal"
        return "", "empty"
    candidate = candidates[0]
    parts = getattr(getattr(candidate, "content", None), "parts", None) or []
    text = "".join(p.text for p in parts if getattr(p, "text", None) and not getattr(p, "thought", False))
    finish = getattr(candidate, "finish_reason", None)
    name = getattr(finish, "name", str(finish) if finish is not None else "")
    if name == "STOP":
        return text, "end_turn"
    if name == "MAX_TOKENS":
        return text, "max_tokens"
    if name in _BLOCK_REASONS:
        return text, "refusal"
    return text, (name or "unknown").lower()


def _map_api_error(exc: genai_errors.APIError) -> ProviderError:
    code = exc.code or 0
    label = f"{code} {exc.status or ''}".strip()
    message = (exc.message or "")[:300]
    if code == 429:
        return ProviderRateLimited(f"rate limited ({label}): {message}", retry_after_s=_retry_after(exc))
    if code in (401, 403):
        return ProviderAuthError(f"authentication/permission failed ({label})")
    if code >= 500 or code in (408, 409):
        return ProviderUnavailable(f"provider error ({label}): {message}", retry_after_s=_retry_after(exc))
    if 400 <= code < 500:
        return ProviderRequestRejected(f"request rejected ({label}): {message}")
    return ProviderError(f"provider failure ({label}): {message}")
