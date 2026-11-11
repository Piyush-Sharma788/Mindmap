# Submission Checklist

## Repository metadata (proposed)
- **Repository:** https://github.com/Piyush-Sharma788/Mindmap (name `Mindmap`, owner `Piyush-Sharma788`)
- **Description (one line):** "Mini mindmap engine (Visualli AI Challenge): generate a 5–9 node mindmap from text and grow it with a second document within 2 LLM calls and 25 nodes. Python library + CLI, offline-tested."
- **Topics:** `llm`, `structured-output`, `mindmap`, `python`, `pydantic`, `cli`, `evaluation`, `prompt-injection`, `anthropic`, `gemini`

## README opening section (proposed)
```markdown
# Mini Mindmap Engine

A Python library and CLI for the Visualli AI Challenge. `generate` turns prose into a
5–9 node mindmap; `grow` merges a second document into an existing map:
- existing nodes stay byte-identical;
- material already covered is dropped;
- the map never exceeds 25 nodes, and everything left out is reported with a reason;
- **at most 2 LLM requests, however long the document is.**

- Setup: `make setup`
- Tests (offline, no API key): `make test`
- Design and trade-offs: APPROACH.md

> Status: verified with 191 offline tests and a deterministic pipeline bench.
> Live: one Gemini smoke-test case passed (see LIVE_EVALUATION_REPORT.md); the full live suite has not been run.
```
*(The current README already contains this information. Adopt the block above only if you want a shorter top section.)*

## Files that must be in the repository
| File | Present |
|---|---|
| README.md (setup, tests, providers/models) | yes |
| APPROACH.md (main write-up and time note) | yes; **2 author placeholders** |
| Source `src/mindmap/`, tests `tests/`, eval suite `evals/` | yes |
| `pyproject.toml`, `Makefile`, `.gitignore`, `.env.example` | yes |
| `schema/mindmap.schema.json` (generated; a drift test guards it) | yes |
| Supporting: ARCHITECTURE, TECHNICAL_DECISIONS, REQUIREMENTS_CHECKLIST, FINAL_REQUIREMENTS_AUDIT, LIVE_EVALUATION_REPORT, CODE_WALKTHROUGH, PROJECT_CONTEXT, PHASE_9_FINAL_AUDIT, SUBMISSION_READINESS_REPORT | yes |
| **Must NOT be present:** `.env`, the assignment PDF, `.venv/`, caches | confirmed untracked and ignored |

## Commands for a reviewer
```bash
git clone https://github.com/Piyush-Sharma788/Mindmap.git && cd Mindmap
make setup                                   # Python 3.11 venv + install (PYTHON=python3.12 to override)
make test                                    # 191 offline tests, no key, no network
.venv/bin/mindmap eval --mode pipeline       # deterministic pipeline bench (~1 s)
.venv/bin/mindmap render --map evals/maps/photosynthesis_seed.json --out seed.mmd
# Live (needs a key; Gemini free tier or Anthropic):
cp .env.example .env    # set MINDMAP_PROVIDER and the key
.venv/bin/mindmap generate --in evals/docs/photosynthesis.txt --out map.json
.venv/bin/mindmap grow --map map.json --in evals/docs/photosynthesis_part2.txt --out map2.json
.venv/bin/mindmap eval --suite evals --mode record --max-cost-usd 2 --pause-s 10
```

## Limitations to disclose (already in APPROACH §12 and the reports)
1. **Live evaluation is a single Gemini smoke test (n = 1, generate only).** Grow, Anthropic, variance and most model-quality metrics are unmeasured, and most cost figures are estimates.
2. Pipeline-bench numbers come from scripted model output; they are not model quality.
3. Small, AI-written eval set (10 cases) with lexical concept matching.
4. Greedy admission is not guaranteed optimal. Duplicates share the 15-candidate limit.
5. The duplicate backstop misses paraphrases and some plurals ("Buses", "Analyses").
6. Sentence splitting and the one-sentence check are heuristics.
7. Text dropped from the excerpt is reported only as a ratio.
8. A refusal retry probably wastes the second request.
9. Development was agent-assisted, in fast bursts (disclosed with times).

## Before making the repository public (your tasks)
- [ ] Fill APPROACH §14 (your code-review %) and §15 (your hands-on time).
- [ ] Optional but strongly recommended: approve the live Gemini smoke test, then the full run, so APPROACH §7/§10 and LIVE_EVALUATION_REPORT carry real numbers. `.env` is now present locally with a Gemini key line; no request has been made.
- [ ] Read CODE_WALKTHROUGH.md and work through your local interview and code-review notes (not part of the public repo).
- [ ] Run `make test` and the secret scan again after any edit.
- [ ] Approve: create the public GitHub repository and push `main` (not done yet).
