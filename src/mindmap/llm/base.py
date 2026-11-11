"""Provider-neutral request/response types and the provider protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class LLMRequest:
    purpose: str  # "generate" | "grow"
    attempt: int  # 1-based
    model: str
    system: str
    messages: list[dict[str, Any]]  # [{"role": "user"|"assistant", "content": str}]
    schema: dict[str, Any]  # JSON schema derived from wire models (see wire.py)
    max_tokens: int
    effort: str | None = None
    cache_system_prompt: bool = True

    def prompt_chars(self) -> int:
        """Characters actually sent as prompt text (system + messages). Measured, not estimated."""
        return len(self.system) + sum(len(str(m["content"])) for m in self.messages)


@dataclass(frozen=True)
class Usage:
    """Token counts AS REPORTED BY THE PROVIDER. Never filled with estimates."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass(frozen=True)
class LLMResponse:
    text: str
    stop_reason: str | None
    model: str
    usage: Usage
    provider: str
    request_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class LLMProvider(Protocol):
    name: str

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Send exactly ONE request. Must not retry internally."""
        ...
