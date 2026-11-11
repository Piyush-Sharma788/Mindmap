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


def test_network_is_blocked_in_tests() -> None:
    with pytest.raises(RuntimeError):
        socket.create_connection(("example.com", 443))
