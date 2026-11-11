from __future__ import annotations

import socket

import pytest

from mindmap.errors import CallBudgetExceeded, ProviderRateLimited
from mindmap.llm.base import LLMRequest
from mindmap.llm.budget import BudgetedCaller, CallBudget
from mindmap.llm.fake import FakeProvider
from mindmap.pricing import estimate_cost_usd


def _req(attempt: int = 1) -> LLMRequest:
    return LLMRequest(
        purpose="grow", attempt=attempt, model="claude-sonnet-5-5", system="s",
        messages=[{"role": "user", "content": "u"}], schema={}, max_tokens=10,
    )


def test_budget_refuses_third_request_before_sending() -> None:
    provider = FakeProvider(["a", "b", "c"])
    caller = BudgetedCaller(provider, CallBudget(2))
    caller.call(_req(1))
    caller.call(_req(2))
    with pytest.raises(CallBudgetExceeded):
        caller.call(_req(3))
    assert provider.calls == 2  # the third request was never sent


def test_failed_request_consumes_budget_and_is_recorded() -> None:
    provider = FakeProvider([ProviderRateLimited("429")])
    caller = BudgetedCaller(provider, CallBudget(1))
    with pytest.raises(ProviderRateLimited):
        caller.call(_req())
    assert caller.budget.remaining == 0
    assert caller.records[0].outcome == "provider_error:ProviderRateLimited"
    assert caller.records[0].input_tokens is None  # no fabricated usage on failure


def test_fake_usage_is_zero_not_estimated() -> None:
    caller = BudgetedCaller(FakeProvider(["x" * 1000]), CallBudget(1))
    caller.call(_req())
    rec = caller.records[0]
    assert rec.input_tokens == 0 and rec.output_tokens == 0
    assert rec.prompt_chars == 2


def test_cost_estimate_uses_list_price() -> None:
    # 1M input + 1M output on Sonnet 5.5 = $2 + $10
    assert estimate_cost_usd("claude-sonnet-5-5", 1_000_000, 1_000_000) == pytest.approx(12.0)
    assert estimate_cost_usd("unknown-model", 10, 10) is None


@pytest.mark.parametrize(
    "model, cache_read_per_mtok, cache_write_per_mtok",
    [("claude-sonnet-5-5", 0.10, 2.50), ("claude-opus-5-5", 0.20, 5.00), ("claude-haiku-5-5", 0.01, 0.125)],
)
def test_cache_prices_match_official_table(model, cache_read_per_mtok, cache_write_per_mtok) -> None:
    # 100K tokens: stays inside Haiku's <=100K-token rate card
    assert estimate_cost_usd(model, 0, 0, cache_read_input_tokens=100_000) == pytest.approx(cache_read_per_mtok / 10)
    assert estimate_cost_usd(model, 0, 0, cache_creation_input_tokens=100_000) == pytest.approx(
        cache_write_per_mtok / 10)


def test_haiku_long_prompt_rate_card() -> None:
    assert estimate_cost_usd("claude-haiku-5-5", 100_001, 0) == pytest.approx(100_001 * 0.50 / 1e6)
    assert estimate_cost_usd("claude-haiku-5-5", 100_000, 0) == pytest.approx(100_000 * 0.10 / 1e6)


def test_worst_case_request_bound() -> None:
    from mindmap.pricing import worst_case_request_usd

    # 40K input x $2 + 16K output x $10 per MTok
    assert worst_case_request_usd("claude-sonnet-5-5", 16_000) == pytest.approx(0.24)


def test_network_is_blocked_in_tests() -> None:
    with pytest.raises(RuntimeError):
        socket.create_connection(("example.com", 443))
