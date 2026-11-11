# Mini Mindmap Engine

A library and thin CLI that turns a document into a small concept mindmap (`generate`) and grows an existing map with a second document (`grow`). Grow uses **at most 2 LLM requests**, whatever the document length, and the map holds **at most 25 nodes**.

Design: [ARCHITECTURE.md](ARCHITECTURE.md). Decisions and trade-offs: [TECHNICAL_DECISIONS.md](TECHNICAL_DECISIONS.md). Requirement status: [REQUIREMENTS_CHECKLIST.md](REQUIREMENTS_CHECKLIST.md). Write-up: [APPROACH.md](APPROACH.md). Live evaluation: [LIVE_EVALUATION_REPORT.md](LIVE_EVALUATION_REPORT.md) (**not run yet**: no API key so far). Code map: [CODE_WALKTHROUGH.md](CODE_WALKTHROUGH.md). Interview notes: [INTERVIEW_PREPARATION.md](INTERVIEW_PREPARATION.md).

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

## Providers and models

Pick the provider with `MINDMAP_PROVIDER` (`anthropic` by default, or `gemini`). The engine is identical for both; only `src/mindmap/llm/<provider>_provider.py` differs.

| | Anthropic | Gemini |
|---|---|---|
| SDK | `anthropic` (2.x) | `google-genai` (3.1) |
| Key | `ANTHROPIC_API_KEY` | `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) |
| Default model | `claude-sonnet-5-5` | `gemini-3.6-flash` (stable; free tier) |
| Structured output | `output_config.format` (json_schema) | `response_mime_type=application/json` + `response_json_schema` |
| Schema | `wire.provider_schema()` | the same schema, with nullable `anyOf` rewritten to `type: [X, "null"]` (Gemini's documented form) |
| SDK retries | `max_retries=0` | `HttpRetryOptions(attempts=1)` |
| Other parameters | `effort=medium`, `max_tokens=16000`, timeout 180 s, system prompt marked cacheable | `max_output_tokens=16000`, timeout 180 000 ms, default thinking, `candidate_count=1` |
| Sampling (`temperature`) | not sent: current Claude models reject it | not sent (provider default) |

**Verification.** All IDs and prices were checked against official docs on 2026-11-11: platform.claude.com for the models and pricing pages; aistudio.google.com for the models, pricing, rate limits and structured output pages. **No live request has been made with either provider yet.**

**Gemini free tier.**
- **Cost:** `gemini-3.6-flash` input and output are free of charge on the free tier. The cost figures the engine reports are *paid-tier equivalents* ($0.75 in / $3.75 out per MTok until 2026-12-31). Requests are free only if your Google AI Studio project is on the Free tier, with no billing attached. Check this on the AI Studio Projects page.
- **Rate limits:** Google applies limits per project. The public docs don't list the free-tier numbers for this model, so check yours on the AI Studio rate-limit page.
- **Data use:** Google may use free-tier content to improve its products, so don't send confidential documents.

## Configuration

Copy `.env.example` to `.env` (it is gitignored) and fill in a key. The CLI loads `.env` from the current directory without overriding variables that are already set, and it never prints values. The test suite disables `.env` loading.

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
.venv/bin/mindmap eval --suite evals/ --mode record --max-cost-usd 2   # LIVE: runs and records responses
.venv/bin/mindmap eval --suite evals/ --mode live --max-cost-usd 2     # LIVE, records nothing
# options: --cases id1,id2 (subset)   --pause-s 10 (wait between cases, for low per-minute quotas)
```

`--max-cost-usd` is required for live and record runs. A case runs only if the money spent so far (provider-reported tokens × list price) plus the case's worst-case cost stays within the ceiling. On the Gemini free tier, the ceiling is applied to paid-equivalent prices.

- **The suite** (`evals/cases.json`) has 10 cases: 4 generate and 6 grow. The grow cases cover overlap, an identical document, a binding ceiling, a 63K-character report whose new material sits in the **last** sections, prompt injection, and an empty document.
- **Status:** no live run has been made yet, so replay currently reports 9 cases as `not_recorded`. The empty-document case checks for an `InputError` and needs no recording. **There are no model-quality numbers yet.**
- **Fixtures:** the documents, seed maps and expected concepts were written with AI assistance and reviewed by hand.

### Pipeline bench (offline, deterministic)

```bash
.venv/bin/mindmap eval --mode pipeline     # ~1 s, no key, no network
```

This measures the code around the model, with scripted model output and seeded fuzzing. It does **not** measure model quality. It covers:
- passage selection on a synthetic long report;
- the duplicate backstop on labelled label pairs;
- grow fuzz (400 runs): validity, preservation, ceiling, accounting, duplicate catch rate, and admitted value compared with an exact optimum;
- generate fuzz (300 runs);
- prompt delimiter integrity;
- Mermaid escaping.

`evals/results/pipeline-bench-{before,after}-phase4.json` holds the same bench run on the Phase 3 code and on the current code:

| Metric | Phase 3 | Phase 4 |
|---|---|---|
| Appendix junk in the excerpt (63K / 107K report) | 49.9% / 49.8% | 4.4% / 0.5% |
| Duplicate-variant catch rate, grow fuzz | 75.6% | 100% (0 false merges on labelled pairs) |
| Grow admission, worst case vs optimum | 62.5% | 100% on these seeds (greedy is not guaranteed optimal) |
| Delimiter integrity on hostile documents | 80% | 100% |
| Validity / preservation / ceiling / accounting / ≤ 2 requests | 100% | 100% |

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
  evals/           runner + metrics; pipeline.py (offline bench) + synthetic.py (generated docs)
  cli.py           Typer CLI
schema/mindmap.schema.json   generated from contract.py (a drift test fails if stale)
evals/            suite: cases.json, docs/, maps/, cassettes/ (after a live run), results/
tests/            offline pytest suite
```

## AI assistance

This code and the planning documents were written with Claude Code (Claude Opus 5.5), working in phases that the author reviewed and approved. Details and the time note will go in `APPROACH.md`.
