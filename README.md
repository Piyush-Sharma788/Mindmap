# Mini Mindmap Engine

A library and thin CLI that turns a document into a small concept mindmap (`generate`) and grows an existing map with a second document (`grow`). Grow uses **at most 2 LLM requests**, whatever the document length, and the map holds **at most 25 nodes**.

Design: [ARCHITECTURE.md](ARCHITECTURE.md). Decisions and trade-offs: [TECHNICAL_DECISIONS.md](TECHNICAL_DECISIONS.md). Requirement status: [REQUIREMENTS_CHECKLIST.md](REQUIREMENTS_CHECKLIST.md). Final write-up: `APPROACH.md` (to be written).

## Setup (one command)

```bash
make setup          # creates .venv with Python 3.11 and installs the package + pytest
```

Requires `python3.11` on PATH. For another version (3.11 or newer), run `make setup PYTHON=python3.12`.

## Tests (one command, no API key, no network)

```bash
make test
```

The test suite removes Anthropic credentials from the environment and blocks all socket connections. Every LLM interaction in the tests goes through a scripted `FakeProvider`.

## Provider and models

| | |
|---|---|
| Provider | Anthropic Claude API, via the official `anthropic` Python SDK (2.x) |
| Default model | `claude-sonnet-5-5`, for both generate and grow |
| Comparison candidates | `claude-haiku-5-5` (cheaper), `claude-opus-5-5` (quality benchmark) |
| Parameters | `output_config.format` = a JSON schema derived from the contract; `output_config.effort = medium`; `max_tokens = 16000`; SDK `max_retries = 0`; timeout 180 s. **No** `temperature` or `top_p`: current Claude models reject sampling parameters |

The model IDs and list prices (Haiku 5.5 $0.10/$0.50, Sonnet 5.5 $2/$10, Opus 5.5 $4/$20 per 1M input/output tokens) come from Anthropic's API reference, as cached on 2026-11-03. **No live request has been made yet**, so the IDs and request shape are not yet confirmed against the live API.

## Usage

```bash
export ANTHROPIC_API_KEY=...            # never commit it; .env is gitignored
.venv/bin/mindmap generate --in doc.txt --out map.json
.venv/bin/mindmap grow --map map.json --in doc2.txt --out map2.json
.venv/bin/mindmap render --map map2.json --out map2.mmd
.venv/bin/mindmap eval --suite evals/ --mode replay      # offline; see below
```

- `--out` receives **only** the contract `Mindmap` JSON. A sidecar `<out>.report.json` holds:
  - the repairs made to model output;
  - for grow: what was added, what was dropped as a duplicate, and what was omitted, with a reason;
  - excerpt statistics;
  - per-request usage, with provider-reported tokens and a cost **estimated** from list prices.
- `-v` logs one line per LLM request to stderr. Document text is never logged.
- Model and effort can be overridden with `MINDMAP_MODEL`, `MINDMAP_MODEL_GENERATE`, `MINDMAP_MODEL_GROW` and `MINDMAP_EFFORT`.
- Exit codes: 2 config or credentials, 3 bad input, 4 provider failure, 5 unusable model output, 70 internal invariant (a bug). No output file is written when the command fails.

## Evaluation

```bash
.venv/bin/mindmap eval --suite evals/ --mode replay   # offline, free: replays recorded responses
.venv/bin/mindmap eval --suite evals/ --mode record   # LIVE (costs money): runs and records responses
.venv/bin/mindmap eval --suite evals/ --mode live     # LIVE, records nothing
```

- **The suite** (`evals/cases.json`) has 10 cases: 4 generate and 6 grow. The grow cases cover overlap, an identical document, a binding ceiling, a ~0.9 MB document, prompt injection, and an empty document.
- **Status:** no live run has been made yet, so replay currently reports 9 cases as `not_recorded`. The empty-document case checks for an `InputError` and needs no recording. There are no quality numbers yet.
- **Fixtures:** the documents, seed maps and expected concepts were written with AI assistance and reviewed by hand.

## Layout

```
src/mindmap/
  contract.py      single source of truth: Mindmap types + validators; schema export
  wire.py          LLM response shapes built from contract field types; provider_schema()
  config.py        every tunable number, with its provenance (spec / reasoned / guessed)
  textprep.py      document validation + deterministic select_passages (no model)
  prompts.py       static system prompts; untrusted text delimited and neutralised
  assemble.py      model draft -> contract map, with every repair logged
  dedup.py         grow: candidate prep + duplicate detection
  ranking.py       grow: importance ranking + admission under the ceiling
  generate.py / grow.py   pipelines
  render.py        Mermaid output with escaping
  llm/             provider protocol, CallBudget, Anthropic provider, fake, cassettes
  evals/           runner + metrics
  cli.py           Typer CLI
schema/mindmap.schema.json   generated from contract.py (a drift test fails if stale)
evals/            suite: cases.json, docs/, maps/, cassettes/ (after a live run), results/
tests/            offline pytest suite
```

## AI assistance

This code and the planning documents were written with Claude Code (Claude Opus 5.5), working in phases that the author reviewed and approved. Details and the time note will go in `APPROACH.md`.
