from __future__ import annotations

import json

import pytest

from helpers import generate_reply
from mindmap.config import Settings
from mindmap.contract import check_generate_size, reachable_from_root
from mindmap.errors import InputError, ModelOutputError, ProviderAuthError, ProviderUnavailable
from mindmap.generate import generate
from mindmap.llm.fake import FakeProvider, FakeReply

DOC = "Photosynthesis converts light into chemical energy. Chlorophyll absorbs light in the leaf."
NO_SLEEP = lambda _s: None  # noqa: E731


def run(provider: FakeProvider, doc: str = DOC):
    return generate(doc, provider, Settings(), sleep=NO_SLEEP)


def test_happy_path_one_request() -> None:
    provider = FakeProvider([generate_reply(7)])
    result = run(provider)
    assert provider.calls == 1
    assert len(result.mindmap.nodes) == 7
    assert result.mindmap.rootId == "concept-a"
    check_generate_size(result.mindmap)
    assert result.usage_summary.requests == 1


def test_request_carries_derived_schema_and_delimited_document() -> None:
    provider = FakeProvider([generate_reply(6)])
    run(provider)
    req = provider.requests[0]
    assert req.schema["properties"].keys() == {"title", "root_ref", "nodes", "connections"}
    assert "<document>\n" + DOC in req.messages[0]["content"]


def test_more_than_nine_nodes_are_trimmed_and_reported() -> None:
    result = run(FakeProvider([generate_reply(12)]))
    assert len(result.mindmap.nodes) == 9
    assert len(result.trimmed) == 3
    assert any("trimmed 3" in note for note in result.repairs)


def test_too_few_nodes_triggers_one_repair_then_succeeds() -> None:
    provider = FakeProvider([generate_reply(3), generate_reply(6)])
    result = run(provider)
    assert provider.calls == 2
    assert "only 3 usable" in provider.requests[1].messages[-1]["content"]
    assert len(result.mindmap.nodes) == 6


def test_too_few_nodes_twice_fails_without_fabricating() -> None:
    provider = FakeProvider([generate_reply(3), generate_reply(4)])
    with pytest.raises(ModelOutputError) as info:
        run(provider)
    assert provider.calls == 2
    assert len(info.value.failures) == 2


@pytest.mark.parametrize("bad", ["not json at all", "{\"title\": 1}", ""])
def test_malformed_then_valid(bad: str) -> None:
    provider = FakeProvider([bad, generate_reply(5)])
    assert len(run(provider).mindmap.nodes) == 5
    assert provider.calls == 2


def test_refusal_and_truncation_consume_budget() -> None:
    provider = FakeProvider([FakeReply("", "refusal"), FakeReply("{\"tit", "max_tokens")])
    with pytest.raises(ModelOutputError):
        run(provider)
    assert provider.calls == 2


def test_transient_error_retried_once() -> None:
    provider = FakeProvider([ProviderUnavailable("503"), generate_reply(5)])
    assert len(run(provider).mindmap.nodes) == 5


def test_non_retryable_error_is_not_retried() -> None:
    provider = FakeProvider([ProviderAuthError("401"), generate_reply(5)])
    with pytest.raises(ProviderAuthError) as info:
        run(provider)
    assert provider.calls == 1
    assert info.value.usage[0].outcome == "provider_error:ProviderAuthError"


def test_graph_defects_repaired_and_logged() -> None:
    reply = json.loads(generate_reply(6))
    reply["connections"] = [
        {"source_ref": "r0", "target_ref": "r1", "label": "includes"},
        {"source_ref": "r1", "target_ref": "r1", "label": "self"},
        {"source_ref": "r0", "target_ref": "ghost", "label": "dangling"},
        {"source_ref": "r1", "target_ref": "r0", "label": "duplicate pair"},
    ]
    reply["nodes"][2]["label"] = "a label that is far too long"
    reply["nodes"][3]["summary"] = "First sentence here. Second sentence here."
    result = run(FakeProvider([json.dumps(reply)]))
    m = result.mindmap
    assert reachable_from_root(m) == m.node_ids()  # orphans attached to root
    notes = " | ".join(result.repairs)
    for expected in ("self-loop", "unknown", "duplicate", "cut to 4 words", "first sentence", "unconnected"):
        assert expected in notes
    assert all(c.from_ != c.to for c in m.connections)


def test_root_ref_invalid_triggers_repair() -> None:
    provider = FakeProvider([generate_reply(6, root_ref="nope"), generate_reply(6)])
    run(provider)
    assert "root_ref" in provider.requests[1].messages[-1]["content"]


def test_empty_document_makes_no_request() -> None:
    provider = FakeProvider([])
    with pytest.raises(InputError):
        run(provider, doc="   ")
    assert provider.calls == 0


def test_duplicate_labels_collapse_before_count_check() -> None:
    reply = json.loads(generate_reply(6))
    reply["nodes"][5]["label"] = "concept b"  # same as node 1 after normalisation
    result = run(FakeProvider([json.dumps(reply)]))
    assert len(result.mindmap.nodes) == 5
