"""List prices used to ESTIMATE cost from provider-reported token counts.

Token counts come from the provider's `usage` (actual). Dollars are an estimate:
actual tokens x the list prices below, which can go out of date.

Source: Anthropic API model table, as cached on 2026-11-03 (via Claude Code's
claude-api reference). Not re-verified against the live pricing page.
"""

from __future__ import annotations

from dataclasses import dataclass

PRICES_AS_OF = "2026-11-03"
CACHE_WRITE_MULTIPLIER = 1.25  # 5-minute cache write = 1.25x base input
CACHE_READ_MULTIPLIER = 0.10  # cache read = 0.1x base input


@dataclass(frozen=True)
class Price:
    input_per_mtok: float
    output_per_mtok: float


PRICES: dict[str, Price] = {
    "claude-haiku-5-5": Price(0.10, 0.50),  # prompts <= 100K tokens
    "claude-sonnet-5-5": Price(2.00, 10.00),
    "claude-opus-5-5": Price(4.00, 20.00),
}
# Haiku 5.5 has a second rate card above 100K prompt tokens. Our prompts are bounded far below that.
HAIKU_LONG_PROMPT = ("claude-haiku-5-5", 100_000, Price(0.50, 2.50))


def estimate_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
) -> float | None:
    """Estimated USD for one request, or None when the model has no known price."""
    price = PRICES.get(model)
    if price is None:
        return None
    total_prompt = input_tokens + cache_creation_input_tokens + cache_read_input_tokens
    long_model, threshold, long_price = HAIKU_LONG_PROMPT
    if model == long_model and total_prompt > threshold:
        price = long_price
    per_in = price.input_per_mtok / 1_000_000
    per_out = price.output_per_mtok / 1_000_000
    return (
        input_tokens * per_in
        + cache_creation_input_tokens * per_in * CACHE_WRITE_MULTIPLIER
        + cache_read_input_tokens * per_in * CACHE_READ_MULTIPLIER
        + output_tokens * per_out
    )
