"""Shapes the LLM must return, built from the contract's field types.

Why not ask for a `Mindmap` directly? The model must not choose ids (collisions,
drift across grow), and grow needs per-candidate judgements (duplicate_of,
importance, attach_to) that are not part of the public contract. These are
different SHAPES, but every shared field reuses the contract's type and description,
and `provider_schema` generates the JSON schema sent to the provider. There are no
hand-written copies of the schema anywhere.
"""

from __future__ import annotations

import copy
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mindmap.config import IMPORTANCE_MAX, IMPORTANCE_MIN
from mindmap.contract import (
    RELATION_DESCRIPTION,
    LabelDraft,
    RelationDraft,
    SummaryDraft,
    TitleDraft,
)

_WIRE = ConfigDict(extra="forbid")

IMPORTANCE_DESCRIPTION = (
    f"How central this concept is to the document, {IMPORTANCE_MIN} (minor detail) "
    f"to {IMPORTANCE_MAX} (core idea)."
)


class DraftNode(BaseModel):
    model_config = _WIRE
    ref: str = Field(description="Temporary reference for this node, e.g. 'n1'. Unique in this response.")
    label: LabelDraft
    summary: SummaryDraft
    importance: int = Field(description=IMPORTANCE_DESCRIPTION)


class DraftConnection(BaseModel):
    model_config = _WIRE
    source_ref: str = Field(description="ref of the source node.")
    target_ref: str = Field(description="ref of the target node.")
    label: RelationDraft


class GenerateProposal(BaseModel):
    model_config = _WIRE
    title: TitleDraft
    root_ref: str = Field(description="ref of the node that is the central topic of the document.")
    nodes: list[DraftNode]
    connections: list[DraftConnection]


class Candidate(BaseModel):
    model_config = _WIRE
    ref: str = Field(description="Temporary reference for this candidate, e.g. 'c1'. Unique in this response.")
    label: LabelDraft
    summary: SummaryDraft
    importance: int = Field(description=IMPORTANCE_DESCRIPTION)
    duplicate_of: str | None = Field(
        description="id of the EXISTING node that already covers this concept, or null if it is new."
    )
    attach_to: str | None = Field(
        description=(
            "id of the existing node, or ref of another new candidate, that this concept belongs under. "
            "null only when duplicate_of is set."
        )
    )
    relation: str | None = Field(description=RELATION_DESCRIPTION + " null only when duplicate_of is set.")


class GrowProposal(BaseModel):
    model_config = _WIRE
    candidates: list[Candidate]


# Keywords the provider's structured-output engine does not support. Their constraints
# are enforced in code (assemble.py / contract.py) instead.
_UNSUPPORTED_KEYWORDS = {
    "minLength", "maxLength", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "multipleOf", "minItems", "maxItems", "pattern", "title", "default",
}


def _clean(node: Any) -> Any:
    if isinstance(node, list):
        return [_clean(item) for item in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in ("properties", "$defs"):
            # Keys here are field/definition NAMES, not keywords: keep them all.
            out[key] = {name: _clean(sub) for name, sub in value.items()}
        elif key in _UNSUPPORTED_KEYWORDS:
            continue
        else:
            out[key] = _clean(value)
    if out.get("type") == "object" or "properties" in out:
        out["additionalProperties"] = False
    return out


def provider_schema(model: type[BaseModel]) -> dict[str, Any]:
    """The exact JSON schema sent to the provider for `model`."""
    return _clean(copy.deepcopy(model.model_json_schema()))
