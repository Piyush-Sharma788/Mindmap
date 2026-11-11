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
    # Latency is wall-clock time of the recording run; replay cannot reproduce it (cassettes do not
    # store latency). Comparing it made this test fail whenever the record run took >= 0.5 ms.
    timing = {"mean_latency_ms_per_case", "max_latency_ms_per_case"}
    strip = lambda agg: {k: v for k, v in agg.items() if k not in timing}  # noqa: E731
    assert strip(recorded["aggregate"]) == strip(replayed["aggregate"])
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


class _PricedFake(FakeProvider):
    """Reports fixed usage per request so the spending ceiling can be exercised offline."""

    def complete(self, request):
        from dataclasses import replace

        from mindmap.llm.base import Usage

        response = super().complete(request)
        return replace(response, usage=Usage(input_tokens=20_000, output_tokens=10_000))


def test_spending_ceiling_skips_cases_whose_worst_case_would_exceed_it(tmp_path) -> None:
    suite = _suite(tmp_path)
    cases = json.loads((suite / "cases.json").read_text())
    cases["cases"].append(dict(cases["cases"][0], id="g2"))
    (suite / "cases.json").write_text(json.dumps(cases))
    # Each request costs 20K*$2 + 10K*$10 per MTok = $0.14; worst case per case = 2 x $0.24 = $0.48.
    result = run_suite(suite, _PricedFake([_dynamic], repeat_last=True), Settings(), "live", max_cost_usd=0.70)
    statuses = [c["status"] for c in result["cases"]]
    assert statuses == ["ok", "ok", "skipped_budget"]  # 0.28 spent + 0.48 worst > 0.70
    assert result["aggregate"]["estimated_cost_usd_total"] == pytest.approx(0.28)
    assert result["aggregate"]["estimated_cost_usd_total"] <= 0.70


def test_case_filter_and_unknown_ids(tmp_path) -> None:
    from mindmap.errors import ConfigError

    suite = _suite(tmp_path)
    result = run_suite(suite, FakeProvider([_dynamic], repeat_last=True), Settings(), "live", case_ids=["w"])
    assert [c["id"] for c in result["cases"]] == ["w"]
    with pytest.raises(ConfigError):
        run_suite(suite, FakeProvider([]), Settings(), "live", case_ids=["nope"])


def test_pause_between_live_cases(tmp_path) -> None:
    suite = _suite(tmp_path)
    waits: list[float] = []
    run_suite(suite, FakeProvider([_dynamic], repeat_last=True), Settings(), "live", pause_s=5, sleep=waits.append)
    assert waits == [5]  # two cases -> one pause between them


def test_prompt_size_reproducer_matches_documented_and_live_values() -> None:
    """APPROACH §7 prompt sizes must be reproducible from the repo (not from a scratch script)."""
    import pathlib

    from mindmap.config import EXCERPT_MAX_CHARS
    from mindmap.evals.prompt_sizes import measure

    rows = {r["case"]: r for r in measure(pathlib.Path(__file__).resolve().parents[1] / "evals")}
    assert rows["gen-photosynthesis"]["prompt_chars"] == 2506  # == prompt_chars logged in the live Gemini run
    gen = [r["prompt_chars"] for k, r in rows.items() if k.startswith("gen-")]
    assert 2_000 <= min(gen) and max(gen) <= 2_600  # APPROACH: 2.1-2.5K
    assert rows["grow-long-document"]["prompt_chars"] <= EXCERPT_MAX_CHARS + 4_000  # bounded despite a 63K doc
    assert rows["grow-empty-document"]["prompt_chars"] is None
