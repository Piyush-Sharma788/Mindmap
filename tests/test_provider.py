"""AnthropicProvider tested with a stub client: no network, no key."""

from __future__ import annotations

import pathlib
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from mindmap.errors import (
    ConfigError,
    ProviderAuthError,
    ProviderRateLimited,
    ProviderRequestRejected,
    ProviderTimeout,
    ProviderUnavailable,
)
from mindmap.llm.anthropic_provider import AnthropicProvider
from mindmap.llm.base import LLMRequest
from mindmap.wire import GrowProposal, provider_schema

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "mindmap"


def _request() -> LLMRequest:
    return LLMRequest(
        purpose="grow", attempt=1, model="claude-sonnet-5-5", system="SYS",
        messages=[{"role": "user", "content": "hi"}], schema=provider_schema(GrowProposal),
        max_tokens=100, effort="medium",
    )


class StubMessages:
    def __init__(self, outcome):
        self.outcome = outcome
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def _client(outcome):
    return SimpleNamespace(messages=StubMessages(outcome))


def _status_error(cls, status: int, headers: dict | None = None):
    response = httpx2.Response(status, headers=headers or {},
                               request=httpx2.Request("POST", "https://api.example.invalid/v1/messages"))
    return cls("error", response=response, body=None)


def test_sdk_retries_disabled_and_timeout_set(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-not-a-real-key")
    provider = AnthropicProvider()
    assert provider.client.max_retries == 0
    assert provider.client.timeout == 180.0


def test_missing_credentials_is_config_error(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(pathlib.Path, "home", lambda: tmp_path)
    with pytest.raises(ConfigError):
        AnthropicProvider()


def test_request_shape_uses_derived_schema_and_no_sampling_params() -> None:
    reply = SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text='{"candidates": []}')],
        stop_reason="end_turn", model="claude-sonnet-5-5",
        usage=SimpleNamespace(input_tokens=10, output_tokens=5, cache_creation_input_tokens=None,
                              cache_read_input_tokens=3),
    )
    stub = _client(reply)
    response = AnthropicProvider(client=stub).complete(_request())
    kwargs = stub.messages.kwargs
    assert kwargs["output_config"]["format"]["schema"] == provider_schema(GrowProposal)
    assert kwargs["output_config"]["effort"] == "medium"
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert not {"temperature", "top_p", "top_k"} & kwargs.keys()
    assert response.text == '{"candidates": []}'  # thinking block skipped, text read by type
    assert response.usage.input_tokens == 10 and response.usage.cache_read_input_tokens == 3


@pytest.mark.parametrize(
    "exc, expected",
    [
        (_status_error(anthropic.RateLimitError, 429, {"retry-after": "3"}), ProviderRateLimited),
        (_status_error(anthropic.AuthenticationError, 401), ProviderAuthError),
        (_status_error(anthropic.BadRequestError, 400), ProviderRequestRejected),
        (_status_error(anthropic.InternalServerError, 500), ProviderUnavailable),
        (_status_error(anthropic.APIStatusError, 529), ProviderUnavailable),
        (anthropic.APITimeoutError(request=httpx2.Request("POST", "https://x.invalid")), ProviderTimeout),
        (anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x.invalid")), ProviderUnavailable),
    ],
)
def test_sdk_errors_mapped_to_typed_errors(exc, expected) -> None:
    with pytest.raises(expected) as info:
        AnthropicProvider(client=_client(exc)).complete(_request())
    if expected is ProviderRateLimited:
        assert info.value.retry_after_s == 3.0


def test_sdk_is_imported_in_exactly_one_module() -> None:
    importers = [p.relative_to(SRC).as_posix() for p in SRC.rglob("*.py")
                 if "import anthropic" in p.read_text() or "from anthropic" in p.read_text()]
    assert importers == ["llm/anthropic_provider.py"]


def test_no_embedding_or_token_count_calls() -> None:
    code = (SRC / "llm" / "anthropic_provider.py").read_text()
    assert "count_tokens" not in code and "embed" not in code
    assert code.count("messages.create(") == 1
