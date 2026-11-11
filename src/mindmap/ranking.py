"""Rank new grow candidates and admit them under the node ceiling. Deterministic.

Value = the model's importance (1-5). Ties: a candidate attached to an existing node
before one hanging off another candidate, then the model's emission order.
A child is admitted only after its parent; if the parent is omitted, so is the child.
"""

from __future__ import annotations

from dataclasses import dataclass

from mindmap.dedup import Omitted, Prepared


@dataclass(frozen=True)
class Admission:
    candidate: Prepared
    parent_kind: str  # "existing" | "candidate"
    parent: str  # existing node id, or the ref of an admitted candidate


def rank(fresh: list[Prepared], existing_ids: set[str]) -> list[Prepared]:
    return sorted(fresh, key=lambda c: (-c.importance, 0 if c.attach_to in existing_ids else 1, c.order))


def admit(
    ranked: list[Prepared],
    *,
    existing_ids: set[str],
    root_id: str,
    capacity: int,
    dup_target: dict[str, str],
    notes: list[str],
) -> tuple[list[Admission], list[Omitted]]:
    fresh_refs = {c.ref for c in ranked}
    status: dict[str, str] = {}
    admitted: list[Admission] = []
    omitted: list[Omitted] = []

    def resolve(c: Prepared) -> tuple[str, str]:
        target = c.attach_to
        for _ in range(len(dup_target) + 1):  # follow duplicate redirects, bounded
            if target is None or target == c.ref:
                break
            if target in existing_ids:
                return "existing", target
            if target in dup_target:
                target = dup_target[target]
                continue
            if target in fresh_refs:
                return "candidate", target
            break
        notes.append(f"candidate {c.ref!r}: attach_to {c.attach_to!r} unusable; attached to root")
        return "existing", root_id

    def omit(c: Prepared, reason: str, detail: str | None = None) -> None:
        status[c.ref] = "omitted"
        omitted.append(Omitted(ref=c.ref, label=c.label, summary=c.summary, importance=c.importance,
                               reason=reason, detail=detail))  # type: ignore[arg-type]

    def place(c: Prepared, kind: str, parent: str) -> None:
        nonlocal capacity
        if capacity <= 0:
            omit(c, "ceiling", "node ceiling reached")
            return
        capacity -= 1
        status[c.ref] = "admitted"
        admitted.append(Admission(c, kind, parent))

    pending = list(ranked)
    while pending:
        waiting: list[Prepared] = []
        progressed = False
        for c in pending:
            kind, parent = resolve(c)
            if kind == "candidate":
                parent_status = status.get(parent)
                if parent_status is None:
                    waiting.append(c)
                    continue
                if parent_status == "omitted":
                    if capacity <= 0:
                        omit(c, "ceiling", "node ceiling reached")
                    else:
                        omit(c, "parent_omitted", f"parent {parent!r} was not added")
                    progressed = True
                    continue
            place(c, kind, parent)
            progressed = True
        if waiting and not progressed:  # attach_to cycle among candidates: break it at the root
            first = waiting.pop(0)
            notes.append(f"candidate {first.ref!r}: attach_to cycle; attached to root")
            place(first, "existing", root_id)
        pending = waiting
    return admitted, omitted
