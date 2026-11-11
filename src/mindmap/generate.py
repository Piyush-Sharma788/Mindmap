"""generate: text -> Mindmap (5-9 nodes). At most GENERATE_MAX_CALLS provider requests."""

from __future__ import annotations

import time
from collections.abc import Callable

from pydantic import BaseModel

from mindmap.assemble import TrimmedNode, assemble_generate
from mindmap.config import GENERATE_MAX_CALLS, Settings
from mindmap.contract import Mindmap
from mindmap.errors import MindmapError
from mindmap.llm.base import LLMProvider
from mindmap.llm.budget import BudgetedCaller, CallBudget
from mindmap.llm.structured import parse_json_model, run_with_repair
from mindmap.observability import UsageRecord, UsageSummary, summarize_usage
from mindmap.prompts import neutralise, GENERATE_SYSTEM, PROMPT_VERSION, generate_user_message
from mindmap.textprep import ExcerptStats, load_document, select_passages
from mindmap.wire import GenerateProposal, provider_schema


class GenerateResult(BaseModel):
    mindmap: Mindmap
    repairs: list[str]
    trimmed: list[TrimmedNode]
    excerpt: ExcerptStats
    usage: list[UsageRecord]
    usage_summary: UsageSummary
    prompt_version: str = PROMPT_VERSION


def generate(
    document: str | bytes,
    provider: LLMProvider,
    settings: Settings | None = None,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> GenerateResult:
    settings = settings or Settings()
    # Neutralise delimiter tags BEFORE selection so the excerpt budget is measured on the exact
    # text that is sent (neutralising lengthens each tag by 3 chars).
    text = neutralise(load_document(document if isinstance(document, bytes) else document.encode("utf-8")))
    excerpt = select_passages(text)
    caller = BudgetedCaller(provider, CallBudget(GENERATE_MAX_CALLS))

    def parse(raw: str):
        return assemble_generate(parse_json_model(raw, GenerateProposal))

    try:
        mindmap, repairs, trimmed = run_with_repair(
            caller,
            purpose="generate",
            model=settings.model_generate,
            system=GENERATE_SYSTEM,
            user_message=generate_user_message(excerpt.text, excerpted=not excerpt.stats.passthrough),
            schema=provider_schema(GenerateProposal),
            settings=settings,
            parse=parse,
            sleep=sleep,
        )
    except MindmapError as exc:
        exc.usage = list(caller.records)  # type: ignore[attr-defined]  # so the CLI can report the requests made
        raise
    return GenerateResult(
        mindmap=mindmap,
        repairs=repairs,
        trimmed=trimmed,
        excerpt=excerpt.stats,
        usage=caller.records,
        usage_summary=summarize_usage(caller.records),
    )
