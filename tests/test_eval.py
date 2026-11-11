"""Eval machinery: record -> replay round trip and metrics. Uses a fake inner provider
only to exercise the plumbing; these are not quality measurements."""

from __future__ import annotations

import json

import pytest

from helpers import candidate, generate_reply, grow_reply, make_map
from mindmap.config import Settings
from mindmap.evals.metrics import match_concepts_lexically
from mindmap.evals.runner import run_suite
from mindmap.llm.cassette import CassetteMissing, RecordingProvider, ReplayProvider, request_key
from mindmap.llm.base import LLMRequest
from mindmap.llm.fake import FakeProvider


def _suite(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "maps").mkdir()
    (tmp_path / "docs" / "a.txt").write_text("Photosynthesis uses chlorophyll.")
    (tmp_path / "docs" / "b.txt").write_text("Irrigation helps crops.")
    (tmp_path / "maps" / "seed.json").write_text(make_map(5).to_json())
    (tmp_path / "cases.json").write_text(json.dumps({"cases": [
        {"id": "g", "kind": "generate", "doc": "docs/a.txt",
         "expected_concepts": [["concept a"], ["missing thing"]]},
        {"id": "w", "kind": "grow", "doc": "docs/b.txt", "map": "maps/seed.json",
         "expected_new": [["irrigation"]], "expected_covered": [["topic 1"]],
         "forbidden_markers": ["PWNED"]},
    ]}))
    return tmp_path


def _dynamic(request: LLMRequest) -> str:
    if request.purpose == "generate":
        return generate_reply(6)
    return grow_reply(candidate("c1", "Irrigation", importance=4), candidate("c2", "Topic 1", attach_to="n0"))


def test_record_then_replay_gives_identical_metrics(tmp_path) -> None:
    suite = _suite(tmp_path)
    recorder = RecordingProvider(FakeProvider([_dynamic], repeat_last=True), suite / "cassettes")
    recorded = run_suite(suite, recorder, Settings(), "record")
    replayed = run_suite(suite, ReplayProvider(suite / "cassettes"), Settings(), "replay")
    assert recorded["aggregate"] == replayed["aggregate"]
    agg = replayed["aggregate"]
    assert agg["cases_scored"] == 2
    assert agg["generate_concept_recall"] == 0.5
    assert agg["grow_new_concept_recall"] == 1.0
    assert agg["grow_duplicate_leakage"] == 0.0  # "Topic 1" caught as a lexical duplicate
    assert agg["grow_max_requests"] == 1
    assert agg["injection_followed_rate"] == 0.0


def test_changed_settings_miss_the_cassette(tmp_path) -> None:
    suite = _suite(tmp_path)
    run_suite(suite, RecordingProvider(FakeProvider([_dynamic], repeat_last=True), suite / "cassettes"),
              Settings(), "record")
    other = run_suite(suite, ReplayProvider(suite / "cassettes"), Settings(effort="high"), "replay")
    assert {c["status"] for c in other["cases"]} == {"not_recorded"}


def test_cassette_key_depends_on_prompt() -> None:
    base = dict(purpose="grow", attempt=1, model="m", system="s", schema={}, max_tokens=1)
    a = LLMRequest(messages=[{"role": "user", "content": "x"}], **base)
    b = LLMRequest(messages=[{"role": "user", "content": "y"}], **base)
    assert request_key(a) != request_key(b)
    with pytest.raises(CassetteMissing):
        ReplayProvider(__import__("pathlib").Path("/nonexistent")).complete(a)


@pytest.mark.parametrize(
    "aliases, texts, hit",
    [
        (["calvin cycle"], ["The Calvin cycle fixes carbon."], True),
        (["cam"], ["Camera sensors"], False),  # whole-word only
        (["stomata"], ["Stomatum pores"], False),
        (["c4"], ["C4 plants such as maize"], True),
    ],
)
def test_lexical_matcher(aliases, texts, hit) -> None:
    assert match_concepts_lexically([aliases], texts) == [hit]
