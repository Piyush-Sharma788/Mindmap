"""Mermaid flowchart rendering. No model involved.

All user-controlled text (labels, relations, title) is escaped with Mermaid entity
codes and placed inside double quotes. Node ids are replaced by generated aliases
(n0, n1, ...), so a hostile id can never become Mermaid syntax.
A flowchart (not Mermaid's `mindmap` diagram) is used because maps may contain
cross-links, which a strict tree diagram cannot show.
"""

from __future__ import annotations

import re

from mindmap.contract import Mindmap

LABEL_RENDER_MAX = 60
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_ENTITIES = {
    "#": "#35;",
    "&": "#38;",
    '"': "#quot;",
    "<": "#lt;",
    ">": "#gt;",
    "`": "#96;",
    "|": "#124;",
}


def escape(text: str, limit: int = LABEL_RENDER_MAX) -> str:
    text = " ".join(_CONTROL.sub(" ", text).split())
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return "".join(_ENTITIES.get(ch, ch) for ch in text)


def render_mermaid(mindmap: Mindmap) -> str:
    alias = {node.id: f"n{i}" for i, node in enumerate(mindmap.nodes)}
    lines = [f"%% {escape(mindmap.title, 120)}", "flowchart LR"]
    for node in mindmap.nodes:
        label = escape(node.label)
        if node.id == mindmap.rootId:
            lines.append(f'    {alias[node.id]}(("{label}"))')
        else:
            lines.append(f'    {alias[node.id]}["{label}"]')
    for edge in mindmap.connections:
        lines.append(f'    {alias[edge.from_]} -->|"{escape(edge.label, 40)}"| {alias[edge.to]}')
    lines.append(f"    classDef root stroke-width:3px")
    lines.append(f"    class {alias[mindmap.rootId]} root")
    return "\n".join(lines) + "\n"
