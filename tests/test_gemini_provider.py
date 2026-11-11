"""GeminiProvider tested with a stub client returning REAL google-genai SDK types. No network, no key."""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx2
import pytest
from google.genai import errors as genai_errors
from google.genai import types

from helpers import candidate, grow_reply, make_map
from mindmap.config import Settings, load_dotenv
from mindmap.errors import (
    ConfigError,
    ModelOutputError,
    ProviderAuthError,
    ProviderRateLimited,
    ProviderRequestRejected,
    ProviderTimeout,
    ProviderUnavailable,
)
from mindmap.grow import grow
from mindmap.llm.base import LLMRequest
from mindmap.llm.gemini_provider import GeminiProvider, gemini_schema
from mindmap.wire import GenerateProposal, GrowProposal, provider_schema


def _response(text: str = '{"candidates": []}', finish=types.FinishReason.STOP, *, thought: str | None = "plan",
              usage=(100, 50, 30, 20)) -> types.GenerateContentResponse:
    parts = ([types.Part(text=thought, thought=True)] if thought else []) + ([types.Part(text=text)] if text else [])
    prompt, cands, thoughts, cached = usage
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=parts), finish_reason=finish)],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=prompt, candidates_token_count=cands,
            thoughts_token_count=thoughts, cached_content_token_count=cached),
        response_id="resp-1", model_version="gemini-3.6-flash",
    )


class StubModels:
    def __init__(self, outcomes, repeat_last=False):
        self.outcomes = list(outcomes)
        self.repeat_last = repeat_last
        self.calls: list[dict] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes[0] if (self.repeat_last and len(self.outcomes) == 1) else self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _provider(*outcomes, repeat_last=False) -> tuple[GeminiProvider, StubModels]:
    models = StubModels(outcomes, repeat_last)
    return GeminiProvider(client=SimpleNamespace(models=models)), models


def _request(messages=None) -> LLMRequest:
    return LLMRequest(purpose="grow", attempt=1, model="gemini-3.6-flash", system="SYS",
                      messages=messages or [{"role": "user", "content": "hi"}],
                      schema=provider_schema(GrowProposal), max_tokens=1000, effort="medium")


def _rate_limit(delay: str | None) -> genai_errors.ClientError:
    details = [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay}] if delay else []
    return genai_errors.ClientError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED",
                                                    "message": "quota exceeded", "details": details}})


# --- Construction & configuration ------------------------------------------------------


def test_missing_key_is_config_error() -> None:
    with pytest.raises(ConfigError, match="GEMINI_API_KEY"):
        GeminiProvider()


def test_sdk_retries_disabled_and_timeout_in_ms(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-not-a-real-key")
    http = GeminiProvider().client._api_client._http_options
    assert http.retry_options.attempts == 1
    assert http.timeout == 180_000


def test_settings_select_gemini_and_its_default_model(monkeypatch) -> None:
    monkeypatch.setenv("MINDMAP_PROVIDER", "gemini")
    s = Settings.from_env()
    assert (s.provider, s.model_generate, s.model_grow) == ("gemini", "gemini-3.6-flash", "gemini-3.6-flash")
    monkeypatch.setenv("MINDMAP_PROVIDER", "openai")
    with pytest.raises(ValueError):
        Settings.from_env()


def test_dotenv_loads_names_without_overriding(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("MINDMAP_NO_DOTENV")
    env = tmp_path / ".env"
    env.write_text('# comment\nGEMINI_API_KEY="secret-value"\nexport MINDMAP_PROVIDER=gemini\nEMPTY=\n')
    monkeypatch.setenv("MINDMAP_PROVIDER", "anthropic")  # already set: must win
    loaded = load_dotenv(env)
    assert loaded == ["GEMINI_API_KEY"]  # names only; never values
    import os
    assert os.environ["GEMINI_API_KEY"] == "secret-value" and os.environ["MINDMAP_PROVIDER"] == "anthropic"
    monkeypatch.delenv("GEMINI_API_KEY")


def test_dotenv_disabled_in_tests(tmp_path) -> None:
    (tmp_path / ".env").write_text("GEMINI_API_KEY=x\n")
    assert load_dotenv(tmp_path / ".env") == []


# --- Request shape & schema ------------------------------------------------------------


def test_request_uses_derived_schema_system_and_role_mapping() -> None:
    provider, models = _provider(_response())
    provider.complete(_request([{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"},
                                {"role": "user", "content": "fix"}]))
    kwargs = models.calls[0]
    config: types.GenerateContentConfig = kwargs["config"]
    assert kwargs["model"] == "gemini-3.6-flash"
    assert [c.role for c in kwargs["contents"]] == ["user", "model", "user"]
    assert config.system_instruction == "SYS"
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == gemini_schema(provider_schema(GrowProposal))
    assert config.max_output_tokens == 1000 and config.candidate_count == 1
    assert config.temperature is None and config.thinking_config is None


@pytest.mark.parametrize("model", [GenerateProposal, GrowProposal])
def test_gemini_schema_only_rewrites_nullable_anyof(model) -> None:
    original = provider_schema(model)
    rewritten = gemini_schema(original)
    text = json.dumps(rewritten)
    assert '"anyOf"' not in text
    if model is GrowProposal:
        cand = rewritten["$defs"]["Candidate"]["properties"]
        assert cand["duplicate_of"]["type"] == ["string", "null"]
        assert cand["duplicate_of"]["description"] == original["$defs"]["Candidate"]["properties"]["duplicate_of"]["description"]
    else:
        assert rewritten == original  # no nullable fields: unchanged


# --- Response handling ------------------------------------------------------------------


def test_usage_text_and_metadata_mapping() -> None:
    provider, _ = _provider(_response('{"candidates": []}'))
    r = provider.complete(_request())
    assert r.text == '{"candidates": []}'  # thought part excluded
    assert r.stop_reason == "end_turn" and r.request_id == "resp-1" and r.provider == "gemini"
    assert (r.usage.input_tokens, r.usage.cache_read_input_tokens, r.usage.output_tokens) == (80, 20, 80)
    assert r.extra["thoughts_token_count"] == 30


@pytest.mark.parametrize(
    "response, stop",
    [
        (_response('{"cand', types.FinishReason.MAX_TOKENS), "max_tokens"),
        (_response("", types.FinishReason.SAFETY, thought=None), "refusal"),
        (_response("", types.FinishReason.PROHIBITED_CONTENT, thought=None), "refusal"),
        (types.GenerateContentResponse(candidates=[], prompt_feedback=types.GenerateContentResponsePromptFeedback(
            block_reason=types.BlockedReason.JAILBREAK)), "refusal"),
        (types.GenerateContentResponse(candidates=[]), "empty"),
        (_response("{}", types.FinishReason.MALFORMED_RESPONSE), "malformed_response"),
    ],
)
def test_finish_reasons_mapped_without_inventing_text(response, stop) -> None:
    provider, _ = _provider(response)
    r = provider.complete(_request())
    assert r.stop_reason == stop


@pytest.mark.parametrize(
    "exc, expected",
    [
        (_rate_limit("7s"), ProviderRateLimited),
        (genai_errors.ClientError(401, {"error": {"code": 401, "status": "UNAUTHENTICATED", "message": "bad key"}}),
         ProviderAuthError),
        (genai_errors.ClientError(403, {"error": {"code": 403, "status": "PERMISSION_DENIED", "message": "no"}}),
         ProviderAuthError),
        (genai_errors.ClientError(400, {"error": {"code": 400, "status": "INVALID_ARGUMENT", "message": "schema"}}),
         ProviderRequestRejected),
        (genai_errors.ServerError(503, {"error": {"code": 503, "status": "UNAVAILABLE", "message": "busy"}}),
         ProviderUnavailable),
        (httpx2.ReadTimeout("slow"), ProviderTimeout),
        (httpx2.ConnectError("down"), ProviderUnavailable),
    ],
)
def test_errors_mapped_to_typed_provider_errors(exc, expected) -> None:
    provider, _ = _provider(exc)
    with pytest.raises(expected) as info:
        provider.complete(_request())
    if expected is ProviderRateLimited:
        assert info.value.retry_after_s == 7.0
    assert "dummy" not in str(info.value)


# --- Engine constraints hold with the Gemini provider --------------------------------------


def test_grow_with_gemini_happy_path_one_request() -> None:
    reply = grow_reply(candidate("c1", "Irrigation", importance=5))
    provider, models = _provider(_response(reply))
    result = grow(make_map(5), "New text about irrigation.", provider, Settings(provider="gemini"), sleep=lambda s: None)
    assert len(models.calls) == 1 and [a.label for a in result.added] == ["Irrigation"]
    assert result.usage[0].input_tokens == 80 and result.usage[0].model == "gemini-3.6-flash"


@pytest.mark.parametrize(
    "outcome, expected_error, expected_calls",
    [
        (_rate_limit("2s"), ProviderRateLimited, 2),  # short retry delay: one retry, then stop
        (_rate_limit("60s"), ProviderRateLimited, 1),  # delay beyond our cap: retrying would waste quota
        (_rate_limit(None), ProviderRateLimited, 2),
        (genai_errors.ServerError(500, {"error": {"code": 500, "status": "INTERNAL", "message": "x"}}),
         ProviderUnavailable, 2),
        (_response("not json"), ModelOutputError, 2),
        (_response("", types.FinishReason.SAFETY, thought=None), ModelOutputError, 2),
    ],
)
def test_grow_with_gemini_never_exceeds_two_requests(outcome, expected_error, expected_calls) -> None:
    provider, models = _provider(outcome, repeat_last=True)
    waits: list[float] = []
    with pytest.raises(expected_error):
        grow(make_map(5), "Some text.", provider, Settings(provider="gemini"), sleep=waits.append)
    assert len(models.calls) == expected_calls <= 2
    assert all(w <= 10.0 for w in waits)
