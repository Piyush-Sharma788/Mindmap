"""THE data contract. Single source of truth.

Everything else derives from this module:
  - wire.py builds the LLM response schemas from the field types/descriptions here,
  - the provider JSON schema is generated from those wire models (wire.provider_schema),
  - schema/mindmap.schema.json is generated from `Mindmap` (see `export_schema`) and a
    test fails if the committed copy drifts.

Code enforces the contract because the model will not: unique ids, a real rootId,
no dangling edges, no self-loops, label/summary rules, and the 25-node ceiling.
The 5-9 rule applies only to first generation, so it lives in `check_generate_size`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from mindmap.config import (
    GENERATE_MAX_NODES,
    GENERATE_MIN_NODES,
    LABEL_MAX_CHARS,
    LABEL_MAX_WORDS,
    MAX_NODES,
    NODE_ID_MAX_CHARS,
    RELATION_MAX_CHARS,
    RELATION_MAX_WORDS,
    SUMMARY_MAX_CHARS,
    TITLE_MAX_CHARS,
)

# --- Field descriptions (shared with the wire schema handed to the provider) ---------
NODE_ID_DESCRIPTION = "Stable node id, unique within the mindmap."
LABEL_DESCRIPTION = f"Short node label: 1-{LABEL_MAX_WORDS} words, at most {LABEL_MAX_CHARS} characters."
SUMMARY_DESCRIPTION = f"Exactly one sentence, at most {SUMMARY_MAX_CHARS} characters, explaining the node."
RELATION_DESCRIPTION = (
    f"Relationship from source to target, 1-{RELATION_MAX_WORDS} words, e.g. 'causes', 'part of'."
)
TITLE_DESCRIPTION = f"Title of the whole mindmap, at most {TITLE_MAX_CHARS} characters."

# --- Text rules -------------------------------------------------------------------
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
# A sentence break: terminal punctuation, optional closing quote/bracket, whitespace, more text.
_SENTENCE_BREAK = re.compile(r"[.!?]+[\"')\]]*\s+(?=\S)")
# Common abbreviations that end in '.' but do not end a sentence. Heuristic (known limitation).
_ABBREVIATIONS = {
    "e.g.", "i.e.", "etc.", "vs.", "approx.", "dr.", "mr.", "mrs.", "ms.", "st.", "no.",
    "fig.", "inc.", "ltd.", "co.", "jr.", "sr.", "u.s.", "u.k.", "a.m.", "p.m.",
}


def word_count(text: str) -> int:
    """Whitespace-separated tokens. A hyphenated term ('long-term') counts as one word."""
    return len(text.split())


def sentence_breaks(text: str) -> list[int]:
    """Character offsets where a new sentence starts (abbreviations excluded)."""
    starts = []
    for match in _SENTENCE_BREAK.finditer(text):
        preceding = text[: match.start() + 1].split()
        last_token = preceding[-1].lower() if preceding else ""
        if last_token in _ABBREVIATIONS:
            continue
        starts.append(match.end())
    return starts


def is_one_sentence(text: str) -> bool:
    return not sentence_breaks(text)


def _check_single_line(value: str, field: str) -> str:
    if not value:
        raise ValueError(f"{field} must not be empty")
    if _CONTROL_CHARS.search(value):
        raise ValueError(f"{field} must not contain control characters or newlines")
    return value


def _check_label(value: str) -> str:
    _check_single_line(value, "label")
    if not 1 <= word_count(value) <= LABEL_MAX_WORDS:
        raise ValueError(f"label must be 1-{LABEL_MAX_WORDS} words, got {word_count(value)}")
    if len(value) > LABEL_MAX_CHARS:
        raise ValueError(f"label must be at most {LABEL_MAX_CHARS} characters")
    return value


def _check_summary(value: str) -> str:
    _check_single_line(value, "summary")
    if len(value) > SUMMARY_MAX_CHARS:
        raise ValueError(f"summary must be at most {SUMMARY_MAX_CHARS} characters")
    if not is_one_sentence(value):
        raise ValueError("summary must be one sentence")
    return value


def _check_relation(value: str) -> str:
    _check_single_line(value, "relation label")
    if not 1 <= word_count(value) <= RELATION_MAX_WORDS:
        raise ValueError(f"relation label must be 1-{RELATION_MAX_WORDS} words")
    if len(value) > RELATION_MAX_CHARS:
        raise ValueError(f"relation label must be at most {RELATION_MAX_CHARS} characters")
    return value


def _check_title(value: str) -> str:
    _check_single_line(value, "title")
    if len(value) > TITLE_MAX_CHARS:
        raise ValueError(f"title must be at most {TITLE_MAX_CHARS} characters")
    return value


def _check_node_id(value: str) -> str:
    _check_single_line(value, "id")
    if len(value) > NODE_ID_MAX_CHARS or any(ch.isspace() for ch in value):
        raise ValueError(f"id must be at most {NODE_ID_MAX_CHARS} characters with no whitespace")
    return value


# Strict types: used by the contract.
NodeId = Annotated[str, Field(description=NODE_ID_DESCRIPTION), AfterValidator(_check_node_id)]
Label = Annotated[str, Field(description=LABEL_DESCRIPTION), AfterValidator(_check_label)]
Summary = Annotated[str, Field(description=SUMMARY_DESCRIPTION), AfterValidator(_check_summary)]
RelationLabel = Annotated[str, Field(description=RELATION_DESCRIPTION), AfterValidator(_check_relation)]
Title = Annotated[str, Field(description=TITLE_DESCRIPTION), AfterValidator(_check_title)]

# Draft types: same descriptions, validation deferred. Used by wire.py for model output, which
# is normalised (and every change logged) by assemble.py before the strict contract is applied.
LabelDraft = Annotated[str, Field(description=LABEL_DESCRIPTION)]
SummaryDraft = Annotated[str, Field(description=SUMMARY_DESCRIPTION)]
RelationDraft = Annotated[str, Field(description=RELATION_DESCRIPTION)]
TitleDraft = Annotated[str, Field(description=TITLE_DESCRIPTION)]

_STRICT = ConfigDict(extra="forbid", str_strip_whitespace=True, populate_by_name=True)


class MindmapNode(BaseModel):
    model_config = _STRICT
    id: NodeId
    label: Label
    summary: Summary


class MindmapConnection(BaseModel):
    model_config = _STRICT
    from_: NodeId = Field(alias="from", description="Source node id.")
    to: NodeId = Field(description="Target node id.")
    label: RelationLabel


class Mindmap(BaseModel):
    model_config = _STRICT
    title: Title
    rootId: NodeId
    nodes: list[MindmapNode]
    connections: list[MindmapConnection]

    @model_validator(mode="after")
    def _graph_rules(self) -> "Mindmap":
        ids = [n.id for n in self.nodes]
        if not ids:
            raise ValueError("mindmap must have at least one node")
        if len(ids) > MAX_NODES:
            raise ValueError(f"mindmap has {len(ids)} nodes; the ceiling is {MAX_NODES}")
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"duplicate node ids: {duplicates}")
        known = set(ids)
        if self.rootId not in known:
            raise ValueError(f"rootId {self.rootId!r} does not match any node id")
        for c in self.connections:
            if c.from_ not in known or c.to not in known:
                raise ValueError(f"dangling connection {c.from_!r} -> {c.to!r}")
            if c.from_ == c.to:
                raise ValueError(f"self-loop on node {c.from_!r}")
        return self

    def to_json(self) -> str:
        return self.model_dump_json(by_alias=True, indent=2)

    def node_ids(self) -> set[str]:
        return {n.id for n in self.nodes}


def check_generate_size(mindmap: Mindmap) -> None:
    """Spec rule for first generation only."""
    n = len(mindmap.nodes)
    if not GENERATE_MIN_NODES <= n <= GENERATE_MAX_NODES:
        raise ValueError(f"first generation must have {GENERATE_MIN_NODES}-{GENERATE_MAX_NODES} nodes, got {n}")


def reachable_from_root(mindmap: Mindmap) -> set[str]:
    """Node ids connected to the root, ignoring edge direction (our addition, TD-11)."""
    adjacency: dict[str, set[str]] = {n.id: set() for n in mindmap.nodes}
    for c in mindmap.connections:
        adjacency[c.from_].add(c.to)
        adjacency[c.to].add(c.from_)
    seen = {mindmap.rootId}
    stack = [mindmap.rootId]
    while stack:
        for nxt in adjacency[stack.pop()]:
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


def load_mindmap(raw: bytes) -> Mindmap:
    """Parse and validate an untrusted map file. Raises InputError (never a partial map)."""
    from pydantic import ValidationError

    from mindmap.config import MAX_INPUT_BYTES
    from mindmap.errors import InputError

    if len(raw) > MAX_INPUT_BYTES:
        raise InputError(f"map file is {len(raw):,} bytes; the limit is {MAX_INPUT_BYTES:,}")
    try:
        return Mindmap.model_validate_json(raw)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or '<root>'}: {e['msg']}" for e in exc.errors()[:5])
        raise InputError(f"map file is not a valid mindmap: {problems}") from exc


SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "mindmap.schema.json"


def export_schema() -> str:
    """JSON Schema of the public contract. Generated artifact: never edit the file by hand."""
    return json.dumps(Mindmap.model_json_schema(by_alias=True), indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":  # python -m mindmap.contract > schema/mindmap.schema.json
    print(export_schema(), end="")
