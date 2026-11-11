"""List prices used to ESTIMATE cost from provider-reported token counts.

Token counts come from the provider's `usage` (actual). Dollars are an estimate:
actual tokens x the list prices below, which can go out of date.

Source: https://platform.claude.com/docs/en/about-claude/pricing, checked 2026-11-11
(base input, 5-minute cache write, cache read, output; USD per million tokens).
Note cache reads are 5% of input on Sonnet/Opus 5.5 but 10% on Haiku 5.5.
"""

from __future__ import annotations

from dataclasses import dataclass

PRICES_AS_OF = "2026-11-11"
CHARS_PER_TOKEN_ESTIMATE = 2.5  # Anthropic: 1M tokens ~ 2.5M characters on the current tokenizer


@dataclass(frozen=True)
class Price:
    input: float
    cache_write_5m: float
    cache_read: float
    output: float


PRICES: dict[str, Price] = {
    "claude-haiku-5-5": Price(0.10, 0.125, 0.01, 0.50),  # prompts <= 100,000 tokens
    "claude-sonnet-5-5": Price(2.00, 2.50, 0.10, 10.00),
    "claude-opus-5-5": Price(4.00, 5.00, 0.20, 20.00),
}
# Gemini: on the FREE tier nothing is billed. This row is the PAID-tier list price, so the
# figure is a "paid-equivalent" estimate. Source: https://aistudio.google.com/docs/pricing,
# checked 2026-11-11 (price valid through 2026-12-31; $1.50/$7.50 from 2027-01-01). Thinking is
# billed as output. Cached-token price not verified: charged at the full input price (conservative).
PRICES["gemini-3.6-flash"] = Price(0.75, 0.75, 0.75, 3.75)
FREE_TIER_PROVIDERS = {"gemini": "Gemini free tier: $0 billed; estimates are paid-tier equivalents"}

# Haiku 5.5 is priced by prompt length; a prompt over 100,000 tokens (input + cache reads/writes)
# pays this card for the whole request. Our prompts are bounded far below it.
HAIKU_LONG_PROMPT = ("claude-haiku-5-5", 100_000, Price(0.50, 0.625, 0.05, 2.50))

# Worst-case input tokens for ONE request, used only for the spending ceiling (not for reporting).
# Prompt <= ~38K chars (excerpt 24K + 25-row map + system + schema) ~ 15K tokens at 2.5 chars/token;
# a repair request also carries the previous output (<= max_tokens = 16K). 40K covers both. (reasoned)
WORST_INPUT_TOKENS_PER_REQUEST = 40_000


def price_for(model: str, prompt_tokens: int = 0) -> Price | None:
    price = PRICES.get(model)
    long_model, threshold, long_price = HAIKU_LONG_PROMPT
    if price is not None and model == long_model and prompt_tokens > threshold:
        return long_price
    return price


def estimate_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
) -> float | None:
    """Estimated USD for one request, or None when the model has no known price."""
    prompt_tokens = input_tokens + cache_creation_input_tokens + cache_read_input_tokens
    price = price_for(model, prompt_tokens)
    if price is None:
        return None
    return (
        input_tokens * price.input
        + cache_creation_input_tokens * price.cache_write_5m
        + cache_read_input_tokens * price.cache_read
        + output_tokens * price.output
    ) / 1_000_000


def worst_case_request_usd(model: str, max_output_tokens: int) -> float | None:
    """Upper bound for one request: worst-case input, uncached, plus a full max_tokens output."""
    price = price_for(model)
    if price is None:
        return None
    return (WORST_INPUT_TOKENS_PER_REQUEST * price.input + max_output_tokens * price.output) / 1_000_000
