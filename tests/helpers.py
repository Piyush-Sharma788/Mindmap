"""Shared builders for tests."""

from __future__ import annotations

import json
from typing import Any

from mindmap.contract import Mindmap


def node(i: int | str, label: str | None = None, summary: str | None = None) -> dict[str, str]:
    return {
        "id": f"n{i}",
        "label": label or f"Topic {i}",
        "summary": summary or f"Topic {i} is a concept used in tests.",
    }


def make_map(n_nodes: int, *, title: str = "Test Map") -> Mindmap:
    """A valid star-shaped map: n0 is root, n1..n{k} attach to it."""
    nodes = [node(i) for i in range(n_nodes)]
    edges = [{"from": "n0", "to": f"n{i}", "label": "includes"} for i in range(1, n_nodes)]
    return Mindmap.model_validate({"title": title, "rootId": "n0", "nodes": nodes, "connections": edges})


def generate_reply(n_nodes: int = 7, **overrides: Any) -> str:
    """A well-formed GenerateProposal JSON string."""
    nodes = [
        {"ref": f"r{i}", "label": f"Concept {chr(65 + i)}", "summary": f"Concept {chr(65 + i)} matters.",
         "importance": 5 if i == 0 else 3}
        for i in range(n_nodes)
    ]
    connections = [
        {"source_ref": "r0", "target_ref": f"r{i}", "label": "includes"} for i in range(1, n_nodes)
    ]
    payload: dict[str, Any] = {"title": "Generated", "root_ref": "r0", "nodes": nodes, "connections": connections}
    payload.update(overrides)
    return json.dumps(payload)


def candidate(
    ref: str,
    label: str,
    *,
    importance: int = 3,
    duplicate_of: str | None = None,
    attach_to: str | None = "n0",
    relation: str | None = "relates to",
    summary: str | None = None,
) -> dict[str, Any]:
    return {
        "ref": ref,
        "label": label,
        "summary": summary or f"{label} is discussed in the new document.",
        "importance": importance,
        "duplicate_of": duplicate_of,
        "attach_to": attach_to if duplicate_of is None else attach_to,
        "relation": relation,
    }


def grow_reply(*candidates: dict[str, Any]) -> str:
    return json.dumps({"candidates": list(candidates)})
