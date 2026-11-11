"""Eval runner: suite of cases -> per-case metrics -> aggregate JSON.

Modes:
  replay - offline, from recorded cassettes; no key, no cost (cases without a
           recording are reported as `not_recorded`, never scored from fakes)
  record - live requests (costs money), each response saved as a cassette
  live   - live requests, nothing saved
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from mindmap.config import GROW_MAX_CALLS, MAX_NODES, Settings
from mindmap.contract import check_generate_size, load_mindmap
from mindmap.errors import MindmapError
from mindmap.evals import metrics as M
from mindmap.generate import generate
from mindmap.grow import grow
from mindmap.llm.base import LLMProvider
from mindmap.llm.cassette import CassetteMissing
from mindmap.prompts import PROMPT_VERSION

Mode = Literal["replay", "record", "live"]


class Case(BaseModel):
    id: str
    kind: Literal["generate", "grow"]
    doc: str  # path relative to the suite directory
    map: str | None = None  # seed map for grow cases
    doc_repeat: int = 1  # repeat the document N times (long-document cases without huge files)
    expected_concepts: list[list[str]] = Field(default_factory=list)  # generate: should appear
    expected_new: list[list[str]] = Field(default_factory=list)  # grow: should be added
    expected_covered: list[list[str]] = Field(default_factory=list)  # grow: must NOT be re-added
    forbidden_markers: list[str] = Field(default_factory=list)  # injection payload markers
    expect_error: str | None = None  # e.g. "InputError"
    notes: str = ""


class Suite(BaseModel):
    description: str = ""
    cases: list[Case]


def load_suite(directory: Path) -> Suite:
    return Suite.model_validate_json((directory / "cases.json").read_text(encoding="utf-8"))


def run_case(case: Case, suite_dir: Path, provider: LLMProvider, settings: Settings) -> dict[str, Any]:
    row: dict[str, Any] = {"id": case.id, "kind": case.kind}
    doc = (suite_dir / case.doc).read_text(encoding="utf-8") * case.doc_repeat
    started = time.perf_counter()
    try:
        if case.kind == "generate":
            result = generate(doc, provider, settings)
        else:
            if case.map is None:
                raise ValueError(f"grow case {case.id} needs a seed map")
            existing = load_mindmap((suite_dir / case.map).read_bytes())
            result = grow(existing, doc, provider, settings)
    except CassetteMissing:
        row["status"] = "not_recorded"
        return row
    except MindmapError as exc:
        usage = getattr(exc, "usage", [])
        row.update(status="error", error=type(exc).__name__, requests=len(usage),
                   expected_error_matched=(case.expect_error == type(exc).__name__))
        return row
    row["wall_ms"] = round((time.perf_counter() - started) * 1000)
    if case.expect_error:
        row.update(status="unexpected_success", expected_error_matched=False)
    else:
        row["status"] = "ok"

    m = result.mindmap
    usage = result.usage_summary
    row.update(
        requests=usage.requests,
        first_pass_ok=len(result.usage) == 1 and result.usage[0].outcome == "ok",
        repairs=len(result.repairs),
        nodes=len(m.nodes),
        connected=M.connected(m),
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_input_tokens=usage.cache_read_input_tokens,
        estimated_cost_usd=usage.estimated_cost_usd,
        excerpt_sent_ratio=round(result.excerpt.sent_ratio, 4),
        injection_followed=M.injection_followed(m, case.forbidden_markers),
    )
    if case.kind == "generate":
        try:
            check_generate_size(m)
            row["size_ok"] = True
        except ValueError:
            row["size_ok"] = False
        hits = M.match_concepts_lexically(case.expected_concepts, M.node_texts(m.nodes))
        row["concept_recall"] = M.recall(hits)
        row["missed_concepts"] = [c[0] for c, hit in zip(case.expected_concepts, hits) if not hit]
    else:
        added_nodes = [n for n in m.nodes if n.id in {a.id for a in result.added}]
        row.update(
            size_ok=len(m.nodes) <= MAX_NODES,
            within_call_budget=usage.requests <= GROW_MAX_CALLS,
            accounting_ok=len(result.added) + len(result.duplicates) + len(result.omitted) == result.candidates_total,
            added=len(result.added),
            duplicates=len(result.duplicates),
            omitted=len(result.omitted),
            omitted_reasons=sorted({o.reason for o in result.omitted}),
        )
        new_hits = M.match_concepts_lexically(case.expected_new, M.node_texts(added_nodes))
        row["new_concept_recall"] = M.recall(new_hits)
        leaked = M.match_concepts_lexically(case.expected_covered, M.node_texts(added_nodes))
        row["duplicate_leakage"] = M.recall(leaked)
        row["leaked_concepts"] = [c[0] for c, hit in zip(case.expected_covered, leaked) if hit]
    return row


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [r for r in rows if r.get("status") in ("ok", "unexpected_success")]
    gen = [r for r in scored if r["kind"] == "generate"]
    grw = [r for r in scored if r["kind"] == "grow"]
    expected_errors = [r for r in rows if "expected_error_matched" in r]
    costs = [r.get("estimated_cost_usd") for r in scored]
    return {
        "cases_total": len(rows),
        "cases_scored": len(scored),
        "cases_not_recorded": sum(r.get("status") == "not_recorded" for r in rows),
        "cases_errored": sum(r.get("status") == "error" for r in rows),
        "expected_errors_matched": M.mean(r["expected_error_matched"] for r in expected_errors),
        "size_ok_rate": M.mean(r["size_ok"] for r in scored),
        "connected_rate": M.mean(r["connected"] for r in scored),
        "first_pass_ok_rate": M.mean(r["first_pass_ok"] for r in scored),
        "mean_repairs": M.mean(r["repairs"] for r in scored),
        "generate_concept_recall": M.mean(r.get("concept_recall") for r in gen),
        "grow_new_concept_recall": M.mean(r.get("new_concept_recall") for r in grw),
        "grow_duplicate_leakage": M.mean(r.get("duplicate_leakage") for r in grw),
        "grow_max_requests": max((r["requests"] for r in grw), default=None),
        "grow_accounting_ok_rate": M.mean(r["accounting_ok"] for r in grw),
        "injection_followed_rate": M.mean(r.get("injection_followed") for r in scored),
        "estimated_cost_usd_total": round(sum(c for c in costs if c is not None), 6) if scored else None,
        "estimated_cost_usd_mean_generate": M.mean(r.get("estimated_cost_usd") for r in gen),
        "estimated_cost_usd_mean_grow": M.mean(r.get("estimated_cost_usd") for r in grw),
    }


def run_suite(suite_dir: Path, provider: LLMProvider, settings: Settings, mode: Mode) -> dict[str, Any]:
    suite = load_suite(suite_dir)
    rows = [run_case(case, suite_dir, provider, settings) for case in suite.cases]
    return {
        "suite": str(suite_dir),
        "mode": mode,
        "provider": provider.name,
        "models": {"generate": settings.model_generate, "grow": settings.model_grow},
        "effort": settings.effort,
        "prompt_version": PROMPT_VERSION,
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": "tokens are provider-reported (replay: as recorded); cost is an estimate from list prices",
        "aggregate": aggregate(rows),
        "cases": rows,
    }
