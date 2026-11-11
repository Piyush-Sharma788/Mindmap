"""Thin CLI. All logic lives in the library; this module does I/O and exit codes."""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

import typer

from mindmap.config import Settings
from mindmap.contract import load_mindmap
from mindmap.errors import (
    CallBudgetExceeded,
    ConfigError,
    InputError,
    InvariantViolation,
    MindmapError,
    ModelOutputError,
    ProviderError,
)
from mindmap.llm.base import LLMProvider
from mindmap.observability import setup_logging

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Mini mindmap engine.")
T = TypeVar("T")

EXIT_CODES: list[tuple[type[MindmapError], int]] = [
    (ConfigError, 2),
    (InputError, 3),
    (ProviderError, 4),
    (ModelOutputError, 5),
    (CallBudgetExceeded, 70),
    (InvariantViolation, 70),
]


def make_provider() -> LLMProvider:
    """Construct the real provider lazily (tests replace this function)."""
    from mindmap.llm.anthropic_provider import AnthropicProvider

    return AnthropicProvider()


def _settings() -> Settings:
    try:
        return Settings.from_env()
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise InputError(f"cannot read {path}: {exc.strerror}") from exc


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _report_path(out: Path) -> Path:
    return out.with_name(out.stem + ".report.json")


def _run(fn: Callable[[], T]) -> T:
    """Map engine errors to exit codes. Bugs (non-MindmapError) propagate with a traceback."""
    try:
        return fn()
    except MindmapError as exc:
        code = next((c for cls, c in EXIT_CODES if isinstance(exc, cls)), 1)
        typer.echo(f"error: {type(exc).__name__}: {exc}", err=True)
        for failure in getattr(exc, "failures", []):
            typer.echo(f"  - {failure}", err=True)
        usage = getattr(exc, "usage", None)
        if usage:
            typer.echo(f"  requests made: {len(usage)} ({', '.join(u.outcome for u in usage)})", err=True)
        raise typer.Exit(code) from None


def _summary(kind: str, result: Any, out: Path) -> None:
    s = result.usage_summary
    cost = f"${s.estimated_cost_usd:.4f} (estimate)" if s.estimated_cost_usd is not None else "n/a"
    typer.echo(f"{kind}: {len(result.mindmap.nodes)} nodes -> {out}", err=True)
    typer.echo(f"  requests={s.requests} input_tokens={s.input_tokens} output_tokens={s.output_tokens} cost={cost}",
               err=True)


@app.callback()
def main(verbose: bool = typer.Option(False, "--verbose", "-v", help="Log each LLM request to stderr.")) -> None:
    setup_logging(logging.INFO if verbose else logging.WARNING)


@app.command("generate")
def generate_cmd(
    in_path: Path = typer.Option(..., "--in", help="Input document (UTF-8 text)."),
    out: Path = typer.Option(..., "--out", help="Output mindmap JSON."),
) -> None:
    """Generate a 5-9 node mindmap from a document."""
    from mindmap.generate import generate

    def work() -> None:
        raw = _read(in_path)
        settings = _settings()
        result = generate(raw, make_provider(), settings)
        _write_atomic(out, result.mindmap.to_json() + "\n")
        _write_atomic(_report_path(out), result.model_dump_json(by_alias=True, indent=2) + "\n")
        _summary("generate", result, out)
        if result.trimmed:
            typer.echo(f"  trimmed {len(result.trimmed)} node(s) over the 9-node limit (see report)", err=True)

    _run(work)


@app.command("grow")
def grow_cmd(
    map_path: Path = typer.Option(..., "--map", help="Existing mindmap JSON."),
    in_path: Path = typer.Option(..., "--in", help="New document (UTF-8 text)."),
    out: Path = typer.Option(..., "--out", help="Output mindmap JSON."),
) -> None:
    """Grow an existing mindmap with a new document (at most 2 LLM requests)."""
    from mindmap.grow import grow

    def work() -> None:
        existing = load_mindmap(_read(map_path))
        raw = _read(in_path)
        settings = _settings()
        result = grow(existing, raw, make_provider(), settings)
        _write_atomic(out, result.mindmap.to_json() + "\n")
        _write_atomic(_report_path(out), result.model_dump_json(by_alias=True, indent=2) + "\n")
        _summary("grow", result, out)
        typer.echo(f"  added={len(result.added)} duplicates={len(result.duplicates)} omitted={len(result.omitted)}",
                   err=True)
        for o in result.omitted:
            typer.echo(f"  omitted [{o.reason}] {o.label}", err=True)

    _run(work)


@app.command("render")
def render_cmd(
    map_path: Path = typer.Option(..., "--map", help="Mindmap JSON."),
    out: Path = typer.Option(..., "--out", help="Output Mermaid file (.mmd)."),
) -> None:
    """Render a mindmap as a Mermaid flowchart (no LLM)."""
    from mindmap.render import render_mermaid

    _run(lambda: _write_atomic(out, render_mermaid(load_mindmap(_read(map_path)))))


@app.command("eval")
def eval_cmd(
    suite: Path = typer.Option(Path("evals"), "--suite", help="Suite directory containing cases.json."),
    mode: str = typer.Option("replay", "--mode", help="replay (offline) | record (live, saves) | live"),
    out: Path | None = typer.Option(None, "--out", help="Results JSON (default: <suite>/results/...)."),
) -> None:
    """Run the eval suite and write a results JSON."""
    from mindmap.evals.runner import run_suite
    from mindmap.llm.cassette import RecordingProvider, ReplayProvider

    def work() -> None:
        if mode not in ("replay", "record", "live"):
            raise InputError("--mode must be replay, record or live")
        if not (suite / "cases.json").is_file():
            raise InputError(f"{suite}/cases.json not found")
        settings = _settings()
        cassettes = suite / "cassettes"
        if mode == "replay":
            provider: LLMProvider = ReplayProvider(cassettes)
        elif mode == "record":
            provider = RecordingProvider(make_provider(), cassettes)
        else:
            provider = make_provider()
        results = run_suite(suite, provider, settings, mode)  # type: ignore[arg-type]
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = out or suite / "results" / f"{stamp}-{mode}-{settings.model_generate}.json"
        _write_atomic(target, json.dumps(results, indent=2) + "\n")
        agg = results["aggregate"]
        typer.echo(f"eval ({mode}): {agg['cases_scored']}/{agg['cases_total']} scored, "
                   f"{agg['cases_not_recorded']} not recorded, {agg['cases_errored']} errored -> {target}", err=True)
        for key, value in agg.items():
            typer.echo(f"  {key}: {value}", err=True)

    _run(work)


if __name__ == "__main__":  # pragma: no cover
    app(sys.argv[1:])
