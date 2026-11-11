"""Grow candidate preparation and duplicate detection. Deterministic code, no model.

The MODEL judges semantic coverage (`duplicate_of`). This module applies that
judgement, then a high-precision backstop: exact match on a normalised label
(case, accents, punctuation, trailing plural 's') against existing nodes and
earlier candidates. Paraphrases the model misses are NOT caught here (by design:
fuzzy thresholds wrongly merge e.g. "Machine Learning" / "Machine Learning Ethics").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from mindmap.assemble import clamp_importance, label_key, normalize_label, normalize_relation, normalize_summary
from mindmap.config import MAX_CANDIDATES
from mindmap.contract import Mindmap
from mindmap.wire import GrowProposal

OmitReason = Literal["ceiling", "invalid", "over_candidate_limit"]


class Duplicate(BaseModel):
    ref: str
    label: str
    duplicate_of: str  # existing node id, or the ref of an earlier candidate
    source: Literal["model", "lexical"]


class Omitted(BaseModel):
    ref: str
    label: str
    summary: str
    importance: int | None
    reason: OmitReason
    detail: str | None = None


@dataclass
class Prepared:
    ref: str
    label: str
    summary: str
    importance: int
    duplicate_of: str | None
    attach_to: str | None
    relation: str
    order: int


def prepare_candidates(proposal: GrowProposal, notes: list[str]) -> tuple[list[Prepared], list[Omitted]]:
    prepared: list[Prepared] = []
    omitted: list[Omitted] = []
    seen_refs: set[str] = set()
    for order, cand in enumerate(proposal.candidates):
        where = f"candidate {cand.ref!r}"
        if order >= MAX_CANDIDATES:
            omitted.append(Omitted(ref=cand.ref, label=cand.label, summary=cand.summary, importance=cand.importance,
                                   reason="over_candidate_limit", detail=f"only the first {MAX_CANDIDATES} are considered"))
            continue
        if cand.ref in seen_refs:
            omitted.append(Omitted(ref=cand.ref, label=cand.label, summary=cand.summary, importance=cand.importance,
                                   reason="invalid", detail="duplicate ref"))
            continue
        seen_refs.add(cand.ref)
        label = normalize_label(cand.label, notes, where)
        summary = normalize_summary(cand.summary, notes, where)
        if label is None or summary is None:
            omitted.append(Omitted(ref=cand.ref, label=cand.label, summary=cand.summary, importance=cand.importance,
                                   reason="invalid", detail="empty label or summary"))
            continue
        relation = normalize_relation(cand.relation, notes, where) if cand.duplicate_of is None else ""
        prepared.append(Prepared(
            ref=cand.ref, label=label, summary=summary,
            importance=clamp_importance(cand.importance, notes, where),
            duplicate_of=cand.duplicate_of, attach_to=cand.attach_to, relation=relation, order=order,
        ))
    return prepared, omitted


def split_duplicates(
    prepared: list[Prepared], existing: Mindmap, notes: list[str]
) -> tuple[list[Prepared], list[Duplicate], dict[str, str]]:
    """Return (fresh candidates, duplicates, ref -> what it duplicates)."""
    existing_ids = existing.node_ids()
    existing_keys = {label_key(n.label): n.id for n in existing.nodes}
    fresh: list[Prepared] = []
    duplicates: list[Duplicate] = []
    dup_target: dict[str, str] = {}
    fresh_keys: dict[str, str] = {}
    for cand in prepared:
        if cand.duplicate_of is not None:
            if cand.duplicate_of in existing_ids:
                duplicates.append(Duplicate(ref=cand.ref, label=cand.label, duplicate_of=cand.duplicate_of, source="model"))
                dup_target[cand.ref] = cand.duplicate_of
                continue
            notes.append(f"candidate {cand.ref!r}: duplicate_of {cand.duplicate_of!r} is not an existing id; ignored")
            if not cand.relation:
                cand.relation = normalize_relation(None, notes, f"candidate {cand.ref!r}")
        key = label_key(cand.label)
        if key in existing_keys:
            duplicates.append(Duplicate(ref=cand.ref, label=cand.label, duplicate_of=existing_keys[key], source="lexical"))
            dup_target[cand.ref] = existing_keys[key]
            continue
        if key in fresh_keys:
            duplicates.append(Duplicate(ref=cand.ref, label=cand.label, duplicate_of=fresh_keys[key], source="lexical"))
            dup_target[cand.ref] = fresh_keys[key]
            continue
        fresh_keys[key] = cand.ref
        fresh.append(cand)
    return fresh, duplicates, dup_target
