from __future__ import annotations

import re

from helpers import make_map
from mindmap.contract import Mindmap
from mindmap.render import render_mermaid

ALLOWED = [
    re.compile(r'^%% [^\n]*$'),
    re.compile(r"^flowchart LR$"),
    re.compile(r'^    n\d+\(\("[^"\n]*"\)\)$'),
    re.compile(r'^    n\d+\["[^"\n]*"\]$'),
    re.compile(r'^    n\d+ -->\|"[^"|\n]*"\| n\d+$'),
    re.compile(r"^    classDef root stroke-width:3px$"),
    re.compile(r"^    class n\d+ root$"),
]


def test_basic_render() -> None:
    out = render_mermaid(make_map(3))
    assert out.splitlines()[1] == "flowchart LR"
    assert '    n0(("Topic 0"))' in out
    assert '    n0 -->|"includes"| n1' in out


def test_hostile_text_cannot_break_out_of_quotes() -> None:
    hostile = Mindmap.model_validate({
        "title": 'Title %%{init: {"theme":"dark"}}%%',
        "rootId": 'root"]-->x',
        "nodes": [
            {"id": 'root"]-->x', "label": 'Evil"] --> X[pwn', "summary": "A hostile node."},
            {"id": "b", "label": "click n0 call", "summary": "Tries a click directive."},
            {"id": "c", "label": "<b>bold</b> `md` #1", "summary": "Markup and entities."},
            {"id": "d", "label": "pipe | breaker", "summary": "Breaks edge labels."},
        ],
        "connections": [
            {"from": 'root"]-->x', "to": "b", "label": 'x"|y'},
            {"from": 'root"]-->x', "to": "c", "label": "a | b"},
            {"from": "c", "to": "d", "label": "<script>"},
        ],
    })
    out = render_mermaid(hostile)
    for line in out.splitlines():
        assert any(p.match(line) for p in ALLOWED), f"unexpected Mermaid line: {line!r}"
    assert 'root"' not in out  # raw ids never reach the output
    assert "<b>" not in out and "<script>" not in out and "`" not in out
    assert "#quot;" in out and "#124;" in out
