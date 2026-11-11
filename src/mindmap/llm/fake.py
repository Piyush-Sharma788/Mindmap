"""Scripted provider for offline tests. Never used by the CLI.

Each scripted step is one of:
  - str                      -> a response with that text and stop_reason "end_turn"
  - FakeReply                -> full control over text / stop_reason
  - an Exception instance    -> raised (e.g. ProviderRateLimited)
  - a callable(request)      -> returns one of the above (for dynamic responses)
Token usage is reported as zero: a fake must not pretend to have real usage.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Union

from mindmap.llm.base import LLMRequest, LLMResponse, Usage


@dataclass(frozen=True)
class FakeReply:
    text: str
    stop_reason: str = "end_turn"


Step = Union[str, FakeReply, Exception, Callable[[LLMRequest], "Step"]]


class FakeProvider:
    name = "fake"

    def __init__(self, script: list[Step] | None = None, *, repeat_last: bool = False) -> None:
        self.script = list(script or [])
        self.repeat_last = repeat_last
        self.requests: list[LLMRequest] = []

    @property
    def calls(self) -> int:
        return len(self.requests)

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if self.script:
            step = self.script[0] if (self.repeat_last and len(self.script) == 1) else self.script.pop(0)
        else:
            raise AssertionError("FakeProvider script exhausted: more requests than the test expected")
        while callable(step) and not isinstance(step, (str, FakeReply, Exception)):
            step = step(request)
        if isinstance(step, Exception):
            raise step
        reply = step if isinstance(step, FakeReply) else FakeReply(text=step)
        return LLMResponse(
            text=reply.text,
            stop_reason=reply.stop_reason,
            model=request.model,
            usage=Usage(),
            provider=self.name,
        )
