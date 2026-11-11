"""Regression gate: the deterministic pipeline bench must keep these guarantees."""

from __future__ import annotations

import pytest

from mindmap.evals import pipeline


@pytest.fixture(scope="module")
def bench():
    return pipeline.run_pipeline_bench()


def test_grow_invariants_hold_on_every_fuzzed_run(bench) -> None:
    g = bench["grow_fuzz"]
    for key in ("valid_rate", "preserved_rate", "within_ceiling_rate", "accounted_rate", "reasons_ok_rate",
                "requests_le_2_rate"):
        assert g[key] == 1.0, key


def test_grow_admission_close_to_optimal(bench) -> None:
    assert bench["grow_fuzz"]["admitted_value_vs_optimum_min"] >= 0.95


def test_backstop_precision_and_recall(bench) -> None:
    d = bench["dedup_backstop"]
    assert d["false_merge_rate"] == 0.0
    assert d["variant_catch_rate"] >= 0.8
    assert bench["grow_fuzz"]["variant_duplicate_catch_rate"] >= 0.95


def test_generate_never_returns_an_invalid_map(bench) -> None:
    g = bench["generate_fuzz"]
    assert g["invalid_map_returned"] == 0 and g["runs_over_2_requests"] == 0


def test_selection_keeps_topics_and_avoids_appendix_junk(bench) -> None:
    for name, row in bench["selection"].items():
        assert row["topic_retention"] == 1.0 and row["within_budget"], name
    assert bench["selection"]["report_107k"]["appendix_share_of_excerpt"] < 0.05


def test_injection_and_render_fully_contained(bench) -> None:
    assert bench["injection"]["delimiter_integrity_rate"] == 1.0
    assert bench["render_fuzz"]["all_lines_allowed_rate"] == 1.0
