"""Measure the exact prompt each eval case would send, offline (no model, no network).

Reproduces the "measured prompt sizes" quoted in APPROACH.md §7:
    python -m mindmap.evals.prompt_sizes [--suite evals]

A capturing provider records the first request and then refuses it with a non-retryable
error, so the pipeline stops after building the request. Nothing is sent anywhere.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from mindmap.config import Settings
from mindmap.contract import load_mindmap
from mindmap.errors import MindmapError, ProviderRequestRejected
from mindmap.evals.runner import load_suite
from mindmap.generate import generate
from mindmap.grow import grow
from mindmap.llm.base import LLMRequest, LLMResponse


class _CaptureFirstRequest:
    name = "capture"

    def __init__(self) -> None:
        self.request: LLMRequest | None = None

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.request = request
        raise ProviderRequestRejected("captured for measurement; not sent")


def measure(suite_dir: Path, settings: Settings | None = None) -> list[dict[str, Any]]:
    settings = settings or Settings()
    rows = []
    for case in load_suite(suite_dir).cases:
        doc = (suite_dir / case.doc).read_text(encoding="utf-8") * case.doc_repeat
        capture = _CaptureFirstRequest()
        try:
            if case.kind == "generate":
                generate(doc, capture, settings)
            else:
                assert case.map is not None
                grow(load_mindmap((suite_dir / case.map).read_bytes()), doc, capture, settings)
        except MindmapError:
            pass  # expected: the capture provider refuses after recording the request
        if capture.request is None:
            rows.append({"case": case.id, "prompt_chars": None, "note": "no request (input rejected first)"})
            continue
        rows.append({
            "case": case.id,
            "prompt_chars": capture.request.prompt_chars(),
            "schema_chars": len(json.dumps(capture.request.schema)),
            "document_chars": len(doc),
        })
    return rows


def main() -> None:  # pragma: no cover - thin CLI
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=Path("evals"))
    for row in measure(parser.parse_args().suite):
        print(json.dumps(row))


if __name__ == "__main__":  # pragma: no cover
    main()
