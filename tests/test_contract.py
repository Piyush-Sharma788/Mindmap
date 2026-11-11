from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from helpers import make_map, node
from mindmap import contract, wire
from mindmap.contract import Mindmap, check_generate_size, is_one_sentence


def _payload(**overrides):
    base = {
        "title": "T",
        "rootId": "n0",
        "nodes": [node(0), node(1)],
        "connections": [{"from": "n0", "to": "n1", "label": "part of"}],
    }
    base.update(overrides)
    return base


def test_valid_map_round_trips_with_from_alias() -> None:
    m = Mindmap.model_validate(_payload())
    dumped = json.loads(m.to_json())
    assert dumped["connections"][0]["from"] == "n0"
    assert Mindmap.model_validate(dumped) == m


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"nodes": [node(0), node(0)], "connections": []}, "duplicate node ids"),
        ({"rootId": "missing"}, "does not match any node id"),
        ({"connections": [{"from": "n0", "to": "ghost", "label": "x"}]}, "dangling"),
        ({"connections": [{"from": "n1", "to": "n1", "label": "x"}]}, "self-loop"),
        ({"nodes": [node(0, label="one two three four five"), node(1)]}, "1-4 words"),
        ({"nodes": [node(0, summary="First sentence. Second sentence."), node(1)]}, "one sentence"),
        ({"nodes": [node(0, label="bad\nlabel"), node(1)]}, "control characters"),
        ({"nodes": [{**node(0), "label": "  "}, node(1)]}, "must not be empty"),
        ({"extra_field": 1}, "Extra inputs"),
    ],
)
def test_contract_rejects(overrides, message) -> None:
    with pytest.raises(ValidationError, match=message):
        Mindmap.model_validate(_payload(**overrides))


def test_ceiling_is_enforced_by_contract() -> None:
    make_map(25)
    with pytest.raises(ValidationError, match="ceiling is 25"):
        make_map(26)


def test_generate_size_rule() -> None:
    check_generate_size(make_map(5))
    check_generate_size(make_map(9))
    for n in (4, 10):
        with pytest.raises(ValueError):
            check_generate_size(make_map(n))


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Plants convert light into chemical energy.", True),
        ("Uses inputs, e.g. water and light, to make sugar.", True),
        ("Costs rose 3.5 percent in 2024.", True),
        ("It grows. It dies.", False),
        ('He said "stop." Then left.', False),
    ],
)
def test_sentence_heuristic(text, expected) -> None:
    assert is_one_sentence(text) is expected


def test_hyphenated_term_counts_as_one_word() -> None:
    Mindmap.model_validate(_payload(nodes=[node(0, label="long-term memory consolidation process"), node(1)]))


# --- Single source of truth / drift ---------------------------------------------------


def _walk(schema):
    if isinstance(schema, dict):
        yield schema
        for value in schema.values():
            yield from _walk(value)
    elif isinstance(schema, list):
        for item in schema:
            yield from _walk(item)


@pytest.mark.parametrize("model", [wire.GenerateProposal, wire.GrowProposal])
def test_provider_schema_is_derived_and_supported(model) -> None:
    schema = wire.provider_schema(model)
    for sub in _walk(schema):
        if sub.get("type") == "object":
            assert sub.get("additionalProperties") is False
        assert not set(sub) & {"minLength", "maxLength", "minimum", "maximum", "minItems", "maxItems"}
    # Every field of the Pydantic model appears, all required.
    assert set(schema["properties"]) == set(model.model_fields)
    assert set(schema["required"]) == set(model.model_fields)


def test_wire_fields_share_contract_descriptions() -> None:
    gen = wire.provider_schema(wire.GenerateProposal)
    draft = gen["$defs"]["DraftNode"]["properties"]
    assert draft["label"]["description"] == contract.LABEL_DESCRIPTION
    assert draft["summary"]["description"] == contract.SUMMARY_DESCRIPTION
    assert gen["properties"]["title"]["description"] == contract.TITLE_DESCRIPTION
    assert gen["$defs"]["DraftConnection"]["properties"]["label"]["description"] == contract.RELATION_DESCRIPTION
    grow = wire.provider_schema(wire.GrowProposal)
    cand = grow["$defs"]["Candidate"]["properties"]
    assert cand["label"]["description"] == contract.LABEL_DESCRIPTION
    assert cand["summary"]["description"] == contract.SUMMARY_DESCRIPTION

    public = Mindmap.model_json_schema(by_alias=True)["$defs"]["MindmapNode"]["properties"]
    assert public["label"]["description"] == contract.LABEL_DESCRIPTION
    assert public["summary"]["description"] == contract.SUMMARY_DESCRIPTION


def test_committed_schema_file_matches_contract() -> None:
    assert contract.SCHEMA_PATH.read_text() == contract.export_schema(), (
        "schema/mindmap.schema.json drifted: regenerate with "
        "`python -m mindmap.contract > schema/mindmap.schema.json`"
    )


@pytest.mark.parametrize(
    "a, b, same",
    [
        ("Calvin Cycle", "The Calvin Cycle", True), ("Bus Lane", "Bus Lanes", True), ("Bus", "Buses", False), ("Office Lease", "Office Leases", True),
        ("Immune Response", "Immune Responses", True),
        ("Battery", "Batteries", True), ("Process", "Processes", True), ("Café", "Cafe", True),
        ("Machine Learning", "Machine Learning Ethics", False), ("C3 Plants", "C4 Plants", False),
        ("Glass", "Gas", False), ("The", "The", True), ("A", "An", False),
    ],
)
def test_label_key_precision(a, b, same) -> None:
    from mindmap.assemble import label_key

    assert (label_key(a) == label_key(b)) is same
