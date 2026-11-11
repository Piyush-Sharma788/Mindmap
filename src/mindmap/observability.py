"""Per-request usage records and logging setup.

Logs never contain document text or credentials: only sizes, counts and outcomes.
"""

from __future__ import annotations

import logging
import sys

from pydantic import BaseModel

from mindmap.pricing import PRICES_AS_OF

logger = logging.getLogger("mindmap")


class UsageRecord(BaseModel):
    purpose: str
    attempt: int
    provider: str
    model: str
    outcome: str  # ok | refused | truncated | invalid_output | provider_error:<Type>
    latency_ms: float
    prompt_chars: int  # measured locally
    # Provider-reported token counts. None when the request failed before a response.
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    cache_read_input_tokens: int | None = None
    stop_reason: str | None = None
    request_id: str | None = None
    # Estimate: provider-reported tokens x list price (pricing.py). None if unknown model/failure.
    estimated_cost_usd: float | None = None


class UsageSummary(BaseModel):
    requests: int
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int
    estimated_cost_usd: float | None
    price_table_date: str = PRICES_AS_OF
    note: str = "tokens are provider-reported; cost is an estimate from list prices"


def summarize_usage(records: list[UsageRecord]) -> UsageSummary:
    """Add up per-request token usage and estimated cost. Pure arithmetic: no model involved."""
    costs = [r.estimated_cost_usd for r in records if r.estimated_cost_usd is not None]
    priced_all = all(r.estimated_cost_usd is not None for r in records if r.input_tokens is not None)
    return UsageSummary(
        requests=len(records),
        input_tokens=sum(r.input_tokens or 0 for r in records),
        output_tokens=sum(r.output_tokens or 0 for r in records),
        cache_creation_input_tokens=sum(r.cache_creation_input_tokens or 0 for r in records),
        cache_read_input_tokens=sum(r.cache_read_input_tokens or 0 for r in records),
        estimated_cost_usd=round(sum(costs), 6) if priced_all else None,
    )


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger("mindmap")
    root.handlers[:] = [handler]
    root.setLevel(level)
