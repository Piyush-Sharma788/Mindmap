# Live Evaluation Report

> **Status: NOT RUN.** No live model request has been made. As of 2026-11-11 09:15 no `GEMINI_API_KEY` (or Anthropic key) was configured, and the live run needs the user's explicit approval. This file records the preflight, the method and the planned runs. Results will be added **only from recorded output**: `evals/results/*.json`, plus cassettes in `evals/cassettes/`.

## 1. Provider and model under test
| | |
|---|---|
| Provider | Google Gemini API (Google AI Studio), SDK `google-genai` 3.1.0 |
| Model | `gemini-3.6-flash`. Listed as stable on aistudio.google.com/docs/models; free tier "free of charge" for input and output on aistudio.google.com/docs/pricing (both checked 2026-11-11) |
| Paid-equivalent price used for estimates and the ceiling | $0.75 input / $3.75 output (thinking included) per MTok, valid until 2026-12-31 |
| Not under test | Anthropic Claude. **No Claude figure in this repository is measured;** all Claude costs are estimates (APPROACH §7) |

## 2. Preflight checklist (before any request)
- [x] `.env` contains a `GEMINI_API_KEY` line and `MINDMAP_PROVIDER=gemini`. Checked in Phase 7 by counting lines only; values not read. The key has **not** been used: no request has been made.
- [x] `.env` is gitignored (`git check-ignore .env`); no credential-like file is tracked; history secret scan clean.
- [x] SDK retries off (`HttpRetryOptions(attempts=1)`, test `test_sdk_retries_disabled_and_timeout_in_ms`); no server-side fallback; no embeddings or token-count calls.
- [ ] **The user confirms that the AI Studio project is on the Free tier with no billing account.** The pricing page does not say how a project is assigned to a tier, so this cannot be checked from the code.
- [ ] The user approves Step A, then Step B.

## 3. Planned runs
| Step | Command | Cases | Most requests possible | Ceiling (paid-equivalent USD) | Expected billed cost |
|---|---|---|---|---|---|
| A, smoke test | `mindmap eval --suite evals --mode record --cases gen-photosynthesis --max-cost-usd 0.20` | 1 | 2 | 0.20 (worst case 0.18) | $0 on the free tier |
| B, full suite | `mindmap eval --suite evals --mode record --pause-s 10 --max-cost-usd 2.00` | 9 that make requests, plus 1 expected `InputError` | 18 | 2.00 (worst case 1.62) | $0 on the free tier |

The ceiling check runs before each case: the spend so far (provider-reported tokens × list price) plus that case's worst case (2 × (40K input + 16K output)) must stay ≤ the ceiling. Otherwise the case is skipped and reported as `skipped_budget`.

## 4. Method
- **Cases** (`evals/cases.json`):
  - `gen-photosynthesis`, `gen-remote-work`, `gen-printing-press`, `gen-injection`;
  - `grow-photosynthesis-extension`, `grow-identical-document`, `grow-ceiling` (23-node seed), `grow-long-document` (63K report, new material in the last sections), `grow-injection`, `grow-empty-document`.
- **Metrics per case:**
  - requests and per-request outcomes;
  - provider-reported input, output (thinking included) and cached tokens;
  - estimated cost; latency;
  - contract validity; 5–9 nodes or ≤ 25; connectivity; first-pass success; repairs;
  - concept recall (generate) and new-concept recall (grow), **matched lexically against hand-written aliases, which undercounts paraphrase**;
  - duplicate leakage: expected-covered concepts that appear among *added* nodes;
  - grow accounting; omitted reasons;
  - `injection_followed`: the planted marker appears anywhere in the map.
- **What it can't show:** with n = 10, AI-written fixtures and no human labels, the results are directional. Run-to-run variance isn't measured (one run per case).

## 5. Results
**Not available. Nothing has been run.** This section will hold, from the results JSON only:
- the aggregate table;
- per-case rows;
- the maps produced;
- every failure, rate limit or refusal, verbatim.

## 6. Pipeline bench (separate; NOT live model results)
These come from `mindmap eval --mode pipeline`, which uses scripted model output and seeded fuzzing. They measure how the code handles model output, **not how good the model is**.

| Metric | Phase 3 code | Phase 4 code |
|---|---|---|
| Grow: valid / preserved / ≤ 25 / accounted / ≤ 2 requests (400 runs) | 100% each | 100% each |
| Grow: admitted value vs exact optimum, worst case | 62.5% | 100% |
| Grow: lexical-variant duplicates caught | 75.6% | 100% |
| Generate: invalid maps returned (300 runs) | 0 | 0 |
| Excerpt share spent on the references appendix (107K report) | 49.8% | 0.5% |
| Prompt delimiter integrity, hostile documents | 80% | 100% |
| Mermaid lines passing the allow-list, hostile labels | 100% | 100% |

Source files: `evals/results/pipeline-bench-before-phase4.json` and `evals/results/pipeline-bench-after-phase4.json`.
