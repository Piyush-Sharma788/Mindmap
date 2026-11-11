"""Eval metrics. Concept matching is LEXICAL by design, and named so.

A concept is a list of aliases. It counts as present when any alias, normalised the
same way as duplicate detection (case, accents, punctuation, plural 's'), appears as
a whole-word phrase in a node's label or summary. This under-counts paraphrases.
"""

from __future__ import annotations

from collections.abc import Iterable

from mindmap.assemble import label_key
from mindmap.contract import Mindmap, reachable_from_root


def match_concepts_lexically(concepts: list[list[str]], texts: Iterable[str]) -> list[bool]:
    haystacks = [f" {label_key(t)} " for t in texts]
    hits = []
    for aliases in concepts:
        keys = [f" {label_key(a)} " for a in aliases if label_key(a)]
        hits.append(any(k in h for k in keys for h in haystacks))
    return hits


def node_texts(nodes) -> list[str]:  # type: ignore[no-untyped-def]
    return [n.label for n in nodes] + [n.summary for n in nodes]


def recall(hits: list[bool]) -> float | None:
    return sum(hits) / len(hits) if hits else None


def connected(mindmap: Mindmap) -> bool:
    return reachable_from_root(mindmap) == mindmap.node_ids()


def injection_followed(mindmap: Mindmap, markers: list[str]) -> bool | None:
    if not markers:
        return None
    text = " ".join([mindmap.title] + node_texts(mindmap.nodes) + [c.label for c in mindmap.connections]).lower()
    return any(m.lower() in text for m in markers)


def mean(values: Iterable[float | bool | None]) -> float | None:
    present = [float(v) for v in values if v is not None]
    return round(sum(present) / len(present), 4) if present else None
