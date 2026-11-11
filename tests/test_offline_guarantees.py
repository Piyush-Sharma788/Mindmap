"""Offline modes must never construct a real provider (and so can never make a paid request).

Any real-provider construction in `replay` or `pipeline` mode fails these tests; the suite-wide
conftest also blocks every socket connection.
"""

from __future__ import annotations

import json
import pathlib
import shutil

import pytest
from typer.testing import CliRunner

from mindmap import cli

SUITE = pathlib.Path(__file__).resolve().parents[1] / "evals"
runner = CliRunner()


@pytest.fixture
def no_real_provider(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("a real provider was constructed in an offline mode")

    monkeypatch.setattr(cli, "make_provider", forbidden)


def test_replay_scores_recorded_gemini_case_without_any_provider(tmp_path, monkeypatch, no_real_provider) -> None:
    if not any((SUITE / "cassettes").glob("*.json")):
        pytest.skip("no recorded cassette in this checkout")
    suite = tmp_path / "evals"
    shutil.copytree(SUITE, suite, ignore=shutil.ignore_patterns("results"))
    monkeypatch.setenv("MINDMAP_PROVIDER", "gemini")  # must match the recording; no key needed
    out = tmp_path / "replay.json"
    result = runner.invoke(cli.app, ["eval", "--suite", str(suite), "--mode", "replay", "--out", str(out)])
    assert result.exit_code == 0, result.output
    rows = {c["id"]: c for c in json.loads(out.read_text())["cases"]}
    assert rows["gen-photosynthesis"]["status"] == "ok"
    assert rows["gen-photosynthesis"]["requests"] == 1  # replayed, not re-requested


def test_replay_with_mismatched_provider_reports_misses_not_live_calls(tmp_path, no_real_provider) -> None:
    suite = tmp_path / "evals"
    shutil.copytree(SUITE, suite, ignore=shutil.ignore_patterns("results"))
    out = tmp_path / "replay.json"
    result = runner.invoke(cli.app, ["eval", "--suite", str(suite), "--mode", "replay", "--out", str(out)])
    assert result.exit_code == 0, result.output
    statuses = {c["status"] for c in json.loads(out.read_text())["cases"]}
    assert statuses <= {"not_recorded", "error"}  # default provider differs from the recording


def test_pipeline_bench_constructs_no_provider(tmp_path, no_real_provider) -> None:
    result = runner.invoke(cli.app, ["eval", "--mode", "pipeline", "--out", str(tmp_path / "b.json")])
    assert result.exit_code == 0, result.output
