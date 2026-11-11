"""Hard cap on LLM requests per operation, plus usage recording.

Every provider request goes through `BudgetedCaller.call`, which takes a budget
slot BEFORE the request is sent. Failed requests (timeouts, 429s, refusals)
therefore count, and a third request in grow raises instead of being sent.
"""

from __future__ import annotations

import logging
import time

from mindmap.errors import CallBudgetExceeded, ProviderError
from mindmap.llm.base import LLMProvider, LLMRequest, LLMResponse
from mindmap.observability import UsageRecord
from mindmap.pricing import estimate_cost_usd

logger = logging.getLogger("mindmap.llm")


class CallBudget:
    def __init__(self, max_calls: int) -> None:
        if max_calls < 1:
            raise ValueError("max_calls must be >= 1")
        self.max_calls = max_calls
        self.used = 0

    @property
    def remaining(self) -> int:
        return self.max_calls - self.used

    def acquire(self) -> int:
        """Reserve one request. Returns its 1-based index. Raises if exhausted."""
        if self.used >= self.max_calls:
            raise CallBudgetExceeded(f"LLM request budget of {self.max_calls} exhausted")
        self.used += 1
        return self.used


class BudgetedCaller:
    def __init__(self, provider: LLMProvider, budget: CallBudget) -> None:
        self.provider = provider
        self.budget = budget
        self.records: list[UsageRecord] = []

    def call(self, request: LLMRequest) -> LLMResponse:
        self.budget.acquire()
        started = time.perf_counter()
        try:
            response = self.provider.complete(request)
        except ProviderError as exc:
            self._record(request, started, outcome=f"provider_error:{type(exc).__name__}")
            raise
        self._record(request, started, outcome="ok", response=response)
        return response

    def mark_last(self, outcome: str) -> None:
        """Downgrade the outcome of the last record (e.g. ok -> invalid_output) after parsing."""
        if self.records:
            self.records[-1] = self.records[-1].model_copy(update={"outcome": outcome})

    def _record(
        self, request: LLMRequest, started: float, *, outcome: str, response: LLMResponse | None = None
    ) -> None:
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        record = UsageRecord(
            purpose=request.purpose,
            attempt=request.attempt,
            provider=self.provider.name,
            model=response.model if response else request.model,
            outcome=outcome,
            latency_ms=latency_ms,
            prompt_chars=request.prompt_chars(),
        )
        if response is not None:
            u = response.usage
            record = record.model_copy(
                update={
                    "input_tokens": u.input_tokens,
                    "output_tokens": u.output_tokens,
                    "cache_creation_input_tokens": u.cache_creation_input_tokens,
                    "cache_read_input_tokens": u.cache_read_input_tokens,
                    "stop_reason": response.stop_reason,
                    "request_id": response.request_id,
                    "estimated_cost_usd": estimate_cost_usd(
                        request.model,
                        u.input_tokens,
                        u.output_tokens,
                        u.cache_creation_input_tokens,
                        u.cache_read_input_tokens,
                    ),
                }
            )
        self.records.append(record)
        logger.info(
            "llm_request purpose=%s attempt=%d model=%s outcome=%s latency_ms=%.0f prompt_chars=%d "
            "in_tok=%s out_tok=%s",
            record.purpose,
            record.attempt,
            record.model,
            record.outcome,
            record.latency_ms,
            record.prompt_chars,
            record.input_tokens,
            record.output_tokens,
        )
