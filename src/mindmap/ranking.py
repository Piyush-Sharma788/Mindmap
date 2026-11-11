"""Admit new grow candidates under the node ceiling. Deterministic, no model.

Value = the model's importance (1-5). A candidate can hang off another NEW candidate, so
admitting it may require admitting its parent chain first.

Greedy by chain: repeatedly pick the most important remaining candidate whose chain
(itself + not-yet-admitted new ancestors) fits in the remaining capacity, and admit the
chain parents-first. Ties: shorter chain, then attached directly to an existing node,
then the model's emission order.

Why not "rank, then admit in passes" (the Phase 2 version)? A high-importance child of a
low-importance new parent waited a pass while mid-importance siblings used the capacity,
so the most valuable concept was dropped (regression test:
test_important_child_is_not_starved_by_mid_importance_siblings). Greedy is not always
optimal (it is a small knapsack); the pipeline bench measures it against an exact optimum.
"""

from __future__ import annotations

from dataclasses import dataclass

from mindmap.dedup import Omitted, Prepared


@dataclass(frozen=True)
class Admission:
    candidate: Prepared
    parent_kind: str  # "existing" | "candidate"
    parent: str  # existing node id, or the ref of an admitted candidate


def resolve_parents(
    fresh: list[Prepared], *, existing_ids: set[str], root_id: str, dup_target: dict[str, str], notes: list[str]
) -> dict[str, tuple[str, str]]:
    """ref -> ("existing", node id) | ("candidate", ref). Duplicates redirect to what they
    duplicate; unusable targets and attach cycles fall back to the root (logged)."""
    fresh_refs = {c.ref for c in fresh}
    parents: dict[str, tuple[str, str]] = {}
    for c in fresh:
        target = c.attach_to
        resolved: tuple[str, str] | None = None
        for _ in range(len(dup_target) + 1):  # follow duplicate redirects, bounded
            if target is None or target == c.ref:
                break
            if target in existing_ids:
                resolved = ("existing", target)
                break
            if target in dup_target:
                target = dup_target[target]
                continue
            if target in fresh_refs:
                resolved = ("candidate", target)
            break
        if resolved is None:
            notes.append(f"candidate {c.ref!r}: attach_to {c.attach_to!r} unusable; attached to root")
            resolved = ("existing", root_id)
        parents[c.ref] = resolved

    order = {c.ref: c.order for c in fresh}
    for c in fresh:  # break attach cycles among candidates
        path: list[str] = []
        ref = c.ref
        while parents[ref][0] == "candidate" and ref not in path:
            path.append(ref)
            ref = parents[ref][1]
        if ref in path:  # cycle: re-attach its earliest-emitted member to the root
            cycle = path[path.index(ref):]
            breaker = min(cycle, key=lambda r: order[r])
            parents[breaker] = ("existing", root_id)
            notes.append(f"candidate {breaker!r}: attach_to cycle; attached to root")
    return parents


def admit(
    fresh: list[Prepared],
    *,
    existing_ids: set[str],
    root_id: str,
    capacity: int,
    dup_target: dict[str, str],
    notes: list[str],
) -> tuple[list[Admission], list[Omitted]]:
    by_ref = {c.ref: c for c in fresh}
    parents = resolve_parents(fresh, existing_ids=existing_ids, root_id=root_id,
                              dup_target=dup_target, notes=notes)
    admitted_refs: set[str] = set()
    admitted: list[Admission] = []

    def chain(ref: str) -> list[str]:
        """Unadmitted candidates needed to admit `ref`, ancestor-first."""
        needed: list[str] = []
        while ref not in admitted_refs:
            needed.append(ref)
            kind, parent = parents[ref]
            if kind == "existing":
                break
            ref = parent
        return list(reversed(needed))

    remaining = [c.ref for c in fresh]
    while capacity > 0:
        best: tuple[tuple[int, int, int, int], list[str]] | None = None
        for ref in remaining:
            needed = chain(ref)
            if len(needed) > capacity:
                continue
            c = by_ref[ref]
            key = (-c.importance, len(needed), 0 if parents[ref][0] == "existing" else 1, c.order)
            if best is None or key < best[0]:
                best = (key, needed)
        if best is None:
            break
        for ref in best[1]:
            kind, parent = parents[ref]
            admitted.append(Admission(by_ref[ref], kind, parent))
            admitted_refs.add(ref)
            remaining.remove(ref)
            capacity -= 1

    # The loop only stops early when capacity is 0: while capacity > 0, the top-most unadmitted
    # ancestor of any remaining candidate has a chain of length 1 and always fits.
    omitted = [
        Omitted(ref=c.ref, label=c.label, summary=c.summary, importance=c.importance,
                reason="ceiling", detail="node ceiling reached")
        for c in sorted((by_ref[r] for r in remaining), key=lambda c: (-c.importance, c.order))
    ]
    return admitted, omitted
