from __future__ import annotations

import json
import pathlib
import shutil

import pytest
from typer.testing import CliRunner

from helpers import candidate, generate_reply, grow_reply, make_map
from mindmap import cli
from mindmap.contract import Mindmap
from mindmap.llm.fake import FakeProvider

runner = CliRunner()
SUITE = pathlib.Path(__file__).resolve().parents[1] / "evals"


@pytest.fixture
def fake(monkeypatch):
    holder: dict[str, FakeProvider] = {}

    def install(script, **kw):
        holder["p"] = FakeProvider(script, **kw)
        monkeypatch.setattr(cli, "make_provider", lambda *_args, **_kwargs: holder["p"])
        return holder["p"]

    return install


def test_generate_writes_contract_map_and_separate_report(tmp_path, fake) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("Some document about photosynthesis.")
    fake([generate_reply(6)])
    out = tmp_path / "map.json"
    result = runner.invoke(cli.app, ["generate", "--in", str(doc), "--out", str(out)])
    assert result.exit_code == 0, result.output
    Mindmap.model_validate_json(out.read_text())  # pure contract, no report fields
    assert set(json.loads(out.read_text())) == {"title", "rootId", "nodes", "connections"}
    report = json.loads((tmp_path / "map.report.json").read_text())
    assert report["usage_summary"]["requests"] == 1


def test_grow_then_render(tmp_path, fake) -> None:
    map_file = tmp_path / "map.json"
    map_file.write_text(make_map(24).to_json())
    doc = tmp_path / "doc2.txt"
    doc.write_text("New material about irrigation and soil.")
    fake([grow_reply(candidate("c1", "Irrigation", importance=5), candidate("c2", "Soil", importance=2))])
    out = tmp_path / "map2.json"
    result = runner.invoke(cli.app, ["grow", "--map", str(map_file), "--in", str(doc), "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert "omitted [ceiling] Soil" in result.output
    assert len(Mindmap.model_validate_json(out.read_text()).nodes) == 25

    mmd = tmp_path / "map2.mmd"
    result = runner.invoke(cli.app, ["render", "--map", str(out), "--out", str(mmd)])
    assert result.exit_code == 0 and mmd.read_text().startswith("%% ")


def test_model_failure_exits_nonzero_and_writes_nothing(tmp_path, fake) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("text")
    provider = fake(["garbage", "garbage again"])
    out = tmp_path / "map.json"
    result = runner.invoke(cli.app, ["generate", "--in", str(doc), "--out", str(out)])
    assert result.exit_code == 5
    assert not out.exists() and not (tmp_path / "map.report.json").exists()
    assert provider.calls == 2 and "requests made: 2" in result.output


def test_missing_credentials_exit_2_without_writing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pathlib.Path, "home", lambda: tmp_path)
    doc = tmp_path / "doc.txt"
    doc.write_text("text")
    out = tmp_path / "map.json"
    result = runner.invoke(cli.app, ["generate", "--in", str(doc), "--out", str(out)])
    assert result.exit_code == 2 and "ConfigError" in result.output
    assert not out.exists()


def test_bad_inputs_exit_3_before_any_request(tmp_path, fake) -> None:
    provider = fake([])
    empty = tmp_path / "empty.txt"
    empty.write_text("   ")
    bad_map = tmp_path / "bad.json"
    bad_map.write_text('{"title": "x", "rootId": "missing", "nodes": [], "connections": []}')
    for args in (
        ["generate", "--in", str(empty), "--out", str(tmp_path / "o.json")],
        ["generate", "--in", str(tmp_path / "nope.txt"), "--out", str(tmp_path / "o.json")],
        ["grow", "--map", str(bad_map), "--in", str(empty), "--out", str(tmp_path / "o.json")],
        ["render", "--map", str(bad_map), "--out", str(tmp_path / "o.mmd")],
    ):
        result = runner.invoke(cli.app, args)
        assert result.exit_code == 3, (args, result.output)
    assert provider.calls == 0


def test_eval_replay_on_shipped_suite_runs_offline(tmp_path) -> None:
    suite = tmp_path / "evals"
    shutil.copytree(SUITE, suite, ignore=shutil.ignore_patterns("cassettes", "results"))
    out = tmp_path / "results.json"
    result = runner.invoke(cli.app, ["eval", "--suite", str(suite), "--mode", "replay", "--out", str(out)])
    assert result.exit_code == 0, result.output
    data = json.loads(out.read_text())
    statuses = {c["id"]: c["status"] for c in data["cases"]}
    assert statuses["grow-empty-document"] == "error"  # expected InputError, no request needed
    assert all(s == "not_recorded" for k, s in statuses.items() if k != "grow-empty-document")
    assert data["aggregate"]["expected_errors_matched"] == 1.0


@pytest.mark.parametrize("mode", ["live", "record"])
def test_live_eval_refuses_to_run_without_a_spending_ceiling(tmp_path, fake, mode) -> None:
    provider = fake([])
    result = runner.invoke(cli.app, ["eval", "--suite", str(SUITE), "--mode", mode, "--out", str(tmp_path / "r.json")])
    assert result.exit_code == 2 and "--max-cost-usd" in result.output
    assert provider.calls == 0


def test_gemini_selected_without_key_exits_2_and_needs_no_anthropic_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MINDMAP_PROVIDER", "gemini")
    doc = tmp_path / "doc.txt"
    doc.write_text("text")
    result = runner.invoke(cli.app, ["generate", "--in", str(doc), "--out", str(tmp_path / "m.json")])
    assert result.exit_code == 2 and "GEMINI_API_KEY" in result.output and "ANTHROPIC" not in result.output
