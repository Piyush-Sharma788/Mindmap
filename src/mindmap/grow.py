"""grow: existing Mindmap + new document -> larger Mindmap.

Hard limits (spec): at most GROW_MAX_CALLS (=2) provider requests in total, including
failures and the repair; at most MAX_NODES (=25) nodes; existing nodes, connections,
title and rootId are never modified (append-only merge, checked after the fact).
Every candidate the model proposes is reported as added, duplicate or omitted.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from pydantic import BaseModel

from mindmap.assemble import unique_id
from mindmap.config import GROW_MAX_CALLS, MAX_CANDIDATES, MAX_NODES, Settings
from mindmap.contract import Mindmap
from mindmap.dedup import Duplicate, Omitted, prepare_candidates, split_duplicates
from mindmap.errors import InvariantViolation, MindmapError
from mindmap.llm.base import LLMProvider
from mindmap.llm.budget import BudgetedCaller, CallBudget
from mindmap.llm.structured import parse_json_model, run_with_repair
from mindmap.observability import UsageRecord, UsageSummary, summarize
from mindmap.prompts import neutralise, GROW_SYSTEM, PROMPT_VERSION, grow_user_message
from mindmap.ranking import Admission, admit
from mindmap.textprep import ExcerptStats, load_document, select_passages
from mindmap.wire import GrowProposal, provider_schema


class Added(BaseModel):
    id: str
    ref: str
    label: str
    importance: int
    attached_to: str
    relation: str


class GrowResult(BaseModel):
    mindmap: Mindmap
    capacity_before: int
    candidates_total: int
    added: list[Added]
    duplicates: list[Duplicate]
    omitted: list[Omitted]
    repairs: list[str]
    excerpt: ExcerptStats
    usage: list[UsageRecord]
    usage_summary: UsageSummary
    prompt_version: str = PROMPT_VERSION


def grow(
    existing: Mindmap,
    document: str | bytes,
    provider: LLMProvider,
    settings: Settings | None = None,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> GrowResult:
    settings = settings or Settings()
    existing = Mindmap.model_validate(existing.model_dump(by_alias=True))  # re-validate untrusted input
    # Neutralise delimiter tags BEFORE selection so the excerpt budget is measured on the exact
    # text that is sent (neutralising lengthens each tag by 3 chars).
    text = neutralise(load_document(document if isinstance(document, bytes) else document.encode("utf-8")))
    capacity = MAX_NODES - len(existing.nodes)
    excerpt = select_passages(
        text, novelty_against=[n.label for n in existing.nodes] + [n.summary for n in existing.nodes]
    )
    caller = BudgetedCaller(provider, CallBudget(GROW_MAX_CALLS))
    try:
        proposal = run_with_repair(
            caller,
            purpose="grow",
            model=settings.model_grow,
            system=GROW_SYSTEM,
            user_message=grow_user_message(
                existing, excerpt.text, excerpted=not excerpt.stats.passthrough,
                capacity=capacity, max_candidates=MAX_CANDIDATES,
            ),
            schema=provider_schema(GrowProposal),
            settings=settings,
            parse=lambda raw: parse_json_model(raw, GrowProposal),
            sleep=sleep,
        )
    except MindmapError as exc:
        exc.usage = list(caller.records)  # type: ignore[attr-defined]
        raise

    notes: list[str] = []
    prepared, omitted = prepare_candidates(proposal, notes)
    fresh, duplicates, dup_target = split_duplicates(prepared, existing, notes)
    existing_ids = existing.node_ids()
    admissions, omitted_rank = admit(
        fresh, existing_ids=existing_ids, root_id=existing.rootId,
        capacity=capacity, dup_target=dup_target, notes=notes,
    )
    omitted += omitted_rank
    merged, added = _merge(existing, admissions)

    _check_preserved(existing, merged)
    accounted = len(added) + len(duplicates) + len(omitted)
    if accounted != len(proposal.candidates):
        raise InvariantViolation(f"{len(proposal.candidates)} candidates but {accounted} accounted for")

    return GrowResult(
        mindmap=merged,
        capacity_before=capacity,
        candidates_total=len(proposal.candidates),
        added=added,
        duplicates=duplicates,
        omitted=omitted,
        repairs=notes,
        excerpt=excerpt.stats,
        usage=caller.records,
        usage_summary=summarize(caller.records),
    )


def _merge(existing: Mindmap, admissions: list[Admission]) -> tuple[Mindmap, list[Added]]:
    taken = set(existing.node_ids())
    ref_to_id: dict[str, str] = {}
    nodes = [n.model_dump(by_alias=True) for n in existing.nodes]
    edges = [c.model_dump(by_alias=True) for c in existing.connections]
    added: list[Added] = []
    for adm in admissions:  # admission order guarantees parents come before children
        c = adm.candidate
        node_id = unique_id(c.label, taken)
        ref_to_id[c.ref] = node_id
        parent_id = adm.parent if adm.parent_kind == "existing" else ref_to_id[adm.parent]
        nodes.append({"id": node_id, "label": c.label, "summary": c.summary})
        edges.append({"from": parent_id, "to": node_id, "label": c.relation})
        added.append(Added(id=node_id, ref=c.ref, label=c.label, importance=c.importance,
                           attached_to=parent_id, relation=c.relation))
    merged = Mindmap.model_validate(
        {"title": existing.title, "rootId": existing.rootId, "nodes": nodes, "connections": edges}
    )
    return merged, added


def _check_preserved(before: Mindmap, after: Mindmap) -> None:
    k, e = len(before.nodes), len(before.connections)
    if (
        after.nodes[:k] != before.nodes
        or after.connections[:e] != before.connections
        or after.title != before.title
        or after.rootId != before.rootId
    ):
        raise InvariantViolation("grow modified the existing map")
    if len(after.nodes) > MAX_NODES:
        raise InvariantViolation(f"grow exceeded {MAX_NODES} nodes")
