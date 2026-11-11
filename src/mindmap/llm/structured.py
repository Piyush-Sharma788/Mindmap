"""Bounded "request -> validate -> (at most one) repair" loop shared by generate and grow.

This is the only retry logic in the engine. It is bounded by the CallBudget: the
loop stops when the budget is spent, and BudgetedCaller raises before a request
over budget could be sent.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from mindmap.config import RETRY_AFTER_MAX_S, RETRY_DEFAULT_WAIT_S, Settings
from mindmap.errors import ModelOutputError, ProviderError
from mindmap.llm.base import LLMRequest
from mindmap.llm.budget import BudgetedCaller
from mindmap.prompts import repair_message

logger = logging.getLogger("mindmap.llm")
T = TypeVar("T")
M = TypeVar("M", bound=BaseModel)


class OutputRejected(Exception):
    """Model output parsed or validated badly. `problems` are fed back in a repair request."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def parse_json_model(text: str, model: type[M]) -> M:
    """Parse model output into a wire model. Error messages never echo input values."""
    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OutputRejected([f"response is not valid JSON ({exc.msg} at char {exc.pos})"]) from exc
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        problems = [
            f"{'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['msg']}" for err in exc.errors()[:10]
        ]
        raise OutputRejected(problems) from exc


def run_with_repair(
    caller: BudgetedCaller,
    *,
    purpose: str,
    model: str,
    system: str,
    user_message: str,
    schema: dict[str, Any],
    settings: Settings,
    parse: Callable[[str], T],
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    base_messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]
    messages = base_messages
    failures: list[str] = []
    attempt = 0
    while caller.budget.remaining > 0:
        attempt += 1
        request = LLMRequest(
            purpose=purpose,
            attempt=attempt,
            model=model,
            system=system,
            messages=messages,
            schema=schema,
            max_tokens=settings.max_output_tokens,
            effort=settings.effort,
            cache_system_prompt=settings.cache_system_prompt,
        )
        try:
            response = caller.call(request)
        except ProviderError as exc:
            failures.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")
            if not exc.retryable or caller.budget.remaining == 0:
                raise
            wait = exc.retry_after_s if exc.retry_after_s is not None else RETRY_DEFAULT_WAIT_S
            sleep(min(max(wait, 0.0), RETRY_AFTER_MAX_S))
            continue  # resend the same request

        if response.stop_reason == "refusal":
            caller.mark_last("refused")
            failures.append(f"attempt {attempt}: model refused")
            continue  # resend unchanged: a different answer is possible but not likely
        if response.stop_reason == "max_tokens":
            caller.mark_last("truncated")
            failures.append(f"attempt {attempt}: output truncated at max_tokens")
            messages = [{"role": "user", "content": user_message + "\n\n" + repair_message(
                ["your previous response was cut off; keep summaries short and return fewer items"])}]
            continue

        try:
            return parse(response.text)
        except OutputRejected as exc:
            caller.mark_last("invalid_output")
            failures.append(f"attempt {attempt}: {exc}")
            logger.info("output_rejected purpose=%s attempt=%d problems=%d", purpose, attempt, len(exc.problems))
            if response.text.strip():
                messages = base_messages + [
                    {"role": "assistant", "content": response.text},
                    {"role": "user", "content": repair_message(exc.problems)},
                ]
            else:
                messages = [{"role": "user", "content": user_message + "\n\n" + repair_message(exc.problems)}]

    raise ModelOutputError(f"{purpose}: no usable model output after {attempt} request(s)", failures)
