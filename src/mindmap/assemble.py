"""Turn model drafts into contract-valid structures, deterministically.

Every change made to model output is recorded as a human-readable repair note.
Nothing here invents content: the only invented element is the "relates to" edge
that attaches an otherwise-orphaned node to the root (TD-10), and it is logged.
"""

from __future__ import annotations

import re
import unicodedata

from pydantic import BaseModel, ValidationError

from mindmap.config import (
    GENERATE_MAX_NODES,
    GENERATE_MIN_NODES,
    IMPORTANCE_MAX,
    IMPORTANCE_MIN,
    LABEL_MAX_CHARS,
    LABEL_MAX_WORDS,
    RELATION_MAX_CHARS,
    RELATION_MAX_WORDS,
    SLUG_MAX_CHARS,
    SUMMARY_MAX_CHARS,
    TITLE_MAX_CHARS,
)
from mindmap.contract import Mindmap, check_generate_size, reachable_from_root, sentence_breaks
from mindmap.llm.structured import OutputRejected
from mindmap.wire import GenerateProposal

DEFAULT_RELATION = "relates to"
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _one_line(text: str | None) -> str:
    return " ".join(_CONTROL.sub(" ", text or "").split())


def _cut(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text.rfind(" ", 0, limit + 1)
    return text[: cut if cut > 0 else limit].rstrip(" ,;:-")


def normalize_label(raw: str | None, notes: list[str], where: str) -> str | None:
    text = _one_line(raw)
    if not text:
        notes.append(f"{where}: empty label")
        return None
    words = text.split()
    if len(words) > LABEL_MAX_WORDS:
        text = " ".join(words[:LABEL_MAX_WORDS])
        notes.append(f"{where}: label cut to {LABEL_MAX_WORDS} words")
    if len(text) > LABEL_MAX_CHARS:
        text = _cut(text, LABEL_MAX_CHARS)
        notes.append(f"{where}: label cut to {LABEL_MAX_CHARS} chars")
    return text or None


def normalize_summary(raw: str | None, notes: list[str], where: str) -> str | None:
    text = _one_line(raw)
    if not text:
        notes.append(f"{where}: empty summary")
        return None
    breaks = sentence_breaks(text)
    if breaks:
        text = text[: breaks[0]].strip()
        notes.append(f"{where}: summary cut to its first sentence")
    if len(text) > SUMMARY_MAX_CHARS:
        text = _cut(text, SUMMARY_MAX_CHARS - 1) + "…"
        notes.append(f"{where}: summary cut to {SUMMARY_MAX_CHARS} chars")
    return text


def normalize_relation(raw: str | None, notes: list[str], where: str) -> str:
    text = _one_line(raw)
    if not text:
        notes.append(f"{where}: missing relation, used '{DEFAULT_RELATION}'")
        return DEFAULT_RELATION
    words = text.split()
    if len(words) > RELATION_MAX_WORDS:
        text = " ".join(words[:RELATION_MAX_WORDS])
        notes.append(f"{where}: relation cut to {RELATION_MAX_WORDS} words")
    if len(text) > RELATION_MAX_CHARS:
        text = _cut(text, RELATION_MAX_CHARS) or DEFAULT_RELATION
        notes.append(f"{where}: relation cut to {RELATION_MAX_CHARS} chars")
    return text


def clamp_importance(value: int, notes: list[str], where: str) -> int:
    if IMPORTANCE_MIN <= value <= IMPORTANCE_MAX:
        return value
    clamped = min(max(value, IMPORTANCE_MIN), IMPORTANCE_MAX)
    notes.append(f"{where}: importance {value} clamped to {clamped}")
    return clamped


_LEADING_ARTICLES = ("the", "a", "an")


def _singular(word: str) -> str:
    """Conservative English singular: -ies -> -y; -(ss|sh|ch|x|z)es -> drop "es"; else -s -> drop
    "s" (not -ss). "-ses" is ambiguous (buses / leases), so only the "s" is dropped: "leases" ->
    "lease" matches, "buses" -> "buse" does not match "bus" (known miss, pipeline bench).
    Irregular plurals ("analyses") are not handled."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith(("sses", "shes", "ches", "xes", "zes")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def label_key(label: str) -> str:
    """Normalised form used for exact-duplicate detection: case, accents, punctuation, a leading
    article ("The Calvin Cycle"), and regular plurals. High precision by design: it never merges
    labels that differ by a content word (measured false-merge rate: pipeline bench)."""
    text = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode().lower()
    words = re.findall(r"[a-z0-9]+", text)
    if len(words) > 1 and words[0] in _LEADING_ARTICLES:
        words = words[1:]
    return " ".join(_singular(w) for w in words)


def slugify(label: str) -> str:
    text = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:SLUG_MAX_CHARS].strip("-")
    return slug or "node"


def unique_id(label: str, taken: set[str]) -> str:
    base = slugify(label)
    candidate, n = base, 2
    while candidate in taken:
        candidate = f"{base}-{n}"
        n += 1
    taken.add(candidate)
    return candidate


class TrimmedNode(BaseModel):
    label: str
    summary: str
    importance: int
    reason: str = "over_generate_max"


def assemble_generate(proposal: GenerateProposal) -> tuple[Mindmap, list[str], list[TrimmedNode]]:
    """Validated GenerateProposal -> contract Mindmap. Raises OutputRejected if unrecoverable."""
    notes: list[str] = []
    kept: dict[str, dict] = {}  # ref -> {"label","summary","importance","order"}
    seen_labels: dict[str, str] = {}
    for order, draft in enumerate(proposal.nodes):
        where = f"node {draft.ref!r}"
        if draft.ref in kept:
            notes.append(f"{where}: duplicate ref dropped")
            continue
        label = normalize_label(draft.label, notes, where)
        summary = normalize_summary(draft.summary, notes, where)
        if label is None or summary is None:
            notes.append(f"{where}: dropped (unusable label or summary)")
            continue
        key = label_key(label)
        if key in seen_labels:
            notes.append(f"{where}: dropped, same label as {seen_labels[key]!r}")
            continue
        seen_labels[key] = draft.ref
        kept[draft.ref] = {
            "label": label,
            "summary": summary,
            "importance": clamp_importance(draft.importance, notes, where),
            "order": order,
        }

    if proposal.root_ref not in kept:
        raise OutputRejected([f"root_ref {proposal.root_ref!r} does not match any usable node ref"])

    trimmed: list[TrimmedNode] = []
    excess = len(kept) - GENERATE_MAX_NODES
    if excess > 0:
        removable = sorted(
            (ref for ref in kept if ref != proposal.root_ref),
            key=lambda r: (kept[r]["importance"], -kept[r]["order"]),
        )
        for ref in removable[:excess]:
            info = kept.pop(ref)
            trimmed.append(TrimmedNode(label=info["label"], summary=info["summary"], importance=info["importance"]))
        notes.append(f"trimmed {excess} lowest-importance node(s) to stay within {GENERATE_MAX_NODES}")

    if len(kept) < GENERATE_MIN_NODES:
        raise OutputRejected(
            [f"only {len(kept)} usable distinct nodes; return {GENERATE_MIN_NODES}-{GENERATE_MAX_NODES}"]
        )

    taken: set[str] = set()
    ids = {ref: unique_id(info["label"], taken) for ref, info in kept.items()}
    root_id = ids[proposal.root_ref]

    edges: list[dict[str, str]] = []
    pairs: set[frozenset[str]] = set()
    for c in proposal.connections:
        where = f"connection {c.source_ref!r}->{c.target_ref!r}"
        if c.source_ref not in ids or c.target_ref not in ids:
            notes.append(f"{where}: dropped (unknown or removed node)")
            continue
        if c.source_ref == c.target_ref:
            notes.append(f"{where}: dropped (self-loop)")
            continue
        pair = frozenset((c.source_ref, c.target_ref))
        if pair in pairs:
            notes.append(f"{where}: dropped (duplicate)")
            continue
        pairs.add(pair)
        edges.append({"from": ids[c.source_ref], "to": ids[c.target_ref],
                      "label": normalize_relation(c.label, notes, where)})

    title = _cut(_one_line(proposal.title), TITLE_MAX_CHARS) or kept[proposal.root_ref]["label"]
    payload = {
        "title": title,
        "rootId": root_id,
        "nodes": [{"id": ids[r], "label": i["label"], "summary": i["summary"]} for r, i in kept.items()],
        "connections": edges,
    }
    mindmap = _validate(payload)
    reachable = reachable_from_root(mindmap)
    orphans = [n.id for n in mindmap.nodes if n.id not in reachable]
    if orphans:
        for orphan in orphans:
            edges.append({"from": root_id, "to": orphan, "label": DEFAULT_RELATION})
        notes.append(f"attached {len(orphans)} unconnected node(s) to the root with '{DEFAULT_RELATION}'")
        mindmap = _validate(payload)
    check_generate_size(mindmap)
    return mindmap, notes, trimmed


def _validate(payload: dict) -> Mindmap:
    try:
        return Mindmap.model_validate(payload)
    except ValidationError as exc:  # should be unreachable after normalisation: surface it, don't hide it
        raise OutputRejected([f"assembled map failed the contract: {e['msg']}" for e in exc.errors()[:5]]) from exc
