"""Every tunable number in the engine, in one place.

Each constant says where it comes from:
  spec     - stated in the Visualli assignment PDF
  reasoned - derived from another constraint
  guessed  - chosen by judgement, NOT yet validated by the eval
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# --- Graph size ---------------------------------------------------------------
GENERATE_MIN_NODES = 5  # spec: "5 to 9 nodes on first generation"
GENERATE_MAX_NODES = 9  # spec
GENERATE_TARGET_NODES = 7  # guessed: middle of 5-9, leaves room for trims/drops either side
MAX_NODES = 25  # spec: ceiling for any map

# --- LLM call budgets ------------------------------------------------------------
GROW_MAX_CALLS = 2  # spec: "at most 2 LLM calls for the whole grow operation"
GENERATE_MAX_CALLS = 2  # reasoned: no spec limit; same discipline as grow (1 call + 1 repair)
assert GROW_MAX_CALLS <= 2, "assignment hard limit"

# --- Input bounding -----------------------------------------------------------------
MAX_INPUT_BYTES = 5_000_000  # guessed: bounds CPU/memory of passage selection; larger is rejected
EXCERPT_MAX_CHARS = 24_000  # guessed: ~6K tokens; a ~4,000-word article passes verbatim
SEGMENT_MAX_CHARS = 600  # guessed: hard-split run-on "sentences" (e.g. text with no punctuation)
NOVELTY_WEIGHT = 0.5  # guessed: down-weights sentences already covered by the map, never zeroes them

# --- Model output bounds ---------------------------------------------------------
MAX_CANDIDATES = 15  # guessed: bounds grow output; refills most maps, 5->25 needs 20 (see TD-6)
IMPORTANCE_MIN, IMPORTANCE_MAX = 1, 5  # guessed: coarse ordinal scale, expected more stable than 0-100
MAX_OUTPUT_TOKENS = 16_000  # guessed: room for thinking + JSON; worst-case $ per call is bounded by it

# --- Field rules (contract) -------------------------------------------------------
LABEL_MAX_WORDS = 4  # spec: "1-4 words"
LABEL_MAX_CHARS = 40  # guessed: stops one 'word' being a 300-char string
SUMMARY_MAX_CHARS = 250  # guessed: one readable sentence
RELATION_MAX_WORDS = 4  # guessed: "part of", "leads to", ...
RELATION_MAX_CHARS = 30  # guessed
TITLE_MAX_CHARS = 80  # guessed
NODE_ID_MAX_CHARS = 64  # guessed
SLUG_MAX_CHARS = 40  # guessed: readable ids

# --- Provider reliability ------------------------------------------------------------
REQUEST_TIMEOUT_S = 180.0  # guessed: 16K output tokens at ~100 tok/s fits; slower = treat as failure
RETRY_AFTER_MAX_S = 10.0  # guessed: honour short retry-after once; never block a CLI user for minutes
RETRY_DEFAULT_WAIT_S = 1.0  # guessed: pause before the single retry when the server gives no hint

DEFAULT_MODEL = "claude-sonnet-5-5"  # user decision (Phase 2): Sonnet 5.5 default
DEFAULT_EFFORT = "medium"  # guessed: API default for Sonnet 5.5 is "high"; medium trades thinking for cost
VALID_EFFORTS = ("low", "medium", "high", "xhigh", "max")


@dataclass(frozen=True)
class Settings:
    """Runtime choices that may differ per environment. Read from env vars."""

    model_generate: str = DEFAULT_MODEL
    model_grow: str = DEFAULT_MODEL
    effort: str | None = DEFAULT_EFFORT
    max_output_tokens: int = MAX_OUTPUT_TOKENS
    cache_system_prompt: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        base = os.environ.get("MINDMAP_MODEL", DEFAULT_MODEL)
        effort = os.environ.get("MINDMAP_EFFORT", DEFAULT_EFFORT)
        if effort.lower() in ("", "none", "default"):
            effort_value: str | None = None  # omit -> provider default
        elif effort in VALID_EFFORTS:
            effort_value = effort
        else:
            raise ValueError(f"MINDMAP_EFFORT must be one of {VALID_EFFORTS} or 'default'")
        return cls(
            model_generate=os.environ.get("MINDMAP_MODEL_GENERATE", base),
            model_grow=os.environ.get("MINDMAP_MODEL_GROW", base),
            effort=effort_value,
        )
