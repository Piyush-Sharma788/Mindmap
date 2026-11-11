# Live Evaluation Report

> **Status: SMOKE TEST ONLY (1 case, 1 live request), run 2026-11-11 09:36 IST.** The full suite has **not** been run; it needs separate approval. Measured values come from the provider response recorded in `evals/cassettes/22450a4b2b700e0fe308fcb03c65ac34.json` and `evals/results/smoke-gemini-gen-photosynthesis.json`. Anything not measured is labelled **estimate** or **inference**.

## 1. Provider and model under test
| | |
|---|---|
| Provider | Google Gemini API (Google AI Studio, free tier as confirmed by the user), SDK `google-genai` 3.1.0 |
| Model requested / reported by the API | `gemini-3.6-flash` / `gemini-3.6-flash` |
| Configuration | `MINDMAP_PROVIDER=gemini` from `.env`; no shell overrides; `max_output_tokens=16000`; SDK `HttpRetryOptions(attempts=1)`; timeout 180,000 ms; default thinking; JSON-schema output |
| Paid-equivalent price (estimate basis only) | $0.75 input / $3.75 output (thinking included) per MTok, valid until 2026-12-31 (aistudio.google.com/docs/pricing, checked 2026-11-11). **On the free tier the billed cost is $0.** |
| Not under test | Anthropic Claude: no Claude figure in this repository is measured |

## 2. Preflight (all checked before the request)
- [x] `.env` sets `MINDMAP_PROVIDER` and `GEMINI_API_KEY`. Variable names were checked, values never printed. No shell overrides.
- [x] The key was rotated after the Phase 7 incident. The new key's hash differs from the leaked one; `.env` is gitignored and was never tracked.
- [x] The resolved provider/model is `gemini` / `gemini-3.6-flash`, and its price is known, so the ceiling is enforceable.
- [x] Request budget for generate: 2. Worst case for the case: 2 × (40K × $0.75 + 16K × $3.75)/1M = **$0.18 ≤ the $0.20 ceiling**.
- [x] No server-side fallback, embeddings or token-count calls. The SDK makes one attempt per request.
- [x] Free tier with no billing: **confirmed by the user**. It can't be checked from the code.

## 3. Command
```bash
.venv/bin/mindmap -v eval --suite evals --mode record --cases gen-photosynthesis \
    --max-cost-usd 0.20 --out evals/results/smoke-gemini-gen-photosynthesis.json
```

## 4. Smoke-test results: `gen-photosynthesis`

### 4.1 Measured (from the provider response and our timer)
| Metric | Value | Source |
|---|---|---|
| Provider requests | **1** (budget 2; no retry or repair needed) | `usage` records / `-v` log |
| Outcome / stop reason | `ok` / `end_turn` (Gemini `STOP`) | response |
| Input tokens | **563** | Gemini `usage_metadata` (prompt minus cached) |
| Output tokens (thinking included) | **1,659** | Gemini `candidates_token_count + thoughts_token_count` |
| Cached tokens | 0 | `usage_metadata` |
| Latency | **10,982 ms** (one request) | `BudgetedCaller` timer |
| Prompt characters sent (system + user) | 2,506 | measured locally |
| Raw JSON response length | 1,850 characters | cassette |
| Contract-valid map | yes | `Mindmap` validation |
| Node count (5–9) | **6**, within range | |
| Connected to root | yes (5 edges, a tree) | |
| First-pass success / repairs | yes / **0 repairs**, nothing trimmed | |
| Concept recall (lexical, 7 expected concepts) | **7/7 = 1.0** | eval runner |

### 4.2 Estimated (derived, not billed)
| Item | Value | How |
|---|---|---|
| Paid-equivalent cost | **$0.006644** | 563 × $0.75/M + 1,659 × $3.75/M (list price × measured tokens) |
| Billed cost | **$0** | free tier, confirmed by the user, not verifiable from code |
| Share of the cost that is output | ~94% | from the line above |
| Thinking tokens | **inferred ~1,200** of the 1,659 output tokens | the JSON is ~1,850 characters, roughly 450 tokens. The cassette does not store Gemini's separate `thoughts_token_count`, so this is not a measurement |

### 4.3 The map the model produced
Rebuilt offline from the recorded response, with no extra API call. Saved as `evals/results/smoke-gemini-gen-photosynthesis.map.json` and `.mmd`.

- **Title:** "Photosynthesis Overview"; root `photosynthesis`.
- **Nodes:** Photosynthesis (importance 5), Chloroplasts (4), Light-Dependent Reactions (4), Calvin Cycle (4), Stomata (3), Global Ecological Impact (4).
- **Edges:**
  - photosynthesis *takes place in* chloroplasts;
  - chloroplasts *hosts* light-dependent-reactions;
  - chloroplasts *hosts* calvin-cycle;
  - photosynthesis *exchanges gas via* stomata;
  - photosynthesis *drives* global-ecological-impact.
- **Manual quality review** (by the assistant; one reviewer, one sample):
  - every summary is a single accurate sentence supported by the document;
  - the structure is sensible;
  - no invented facts were noticed.
- **Caveat on recall:** "chlorophyll", "sugar/glucose" and "oxygen" were matched inside *summaries*. Chlorophyll and glucose are not separate nodes. The generator aimed for about 7 nodes and returned 6.

### 4.4 What this smoke test verifies, and what it doesn't
- **Verified live:**
  - the Gemini integration works end to end: model ID, `response_json_schema` with `$defs`/`$ref` and the nullable rewrite path, usage fields, our parser and validator;
  - the spending ceiling admitted the case correctly;
  - the request count stayed within budget.
- **Not verified by this test:**
  - grow (no grow case was run), and therefore live duplicate leakage, preservation, overflow and the two-request limit under real conditions;
  - injection resistance;
  - error and rate-limit handling against the real API (no error occurred);
  - run-to-run variability (one sample);
  - any Anthropic behaviour.

## 4.5 Offline re-verification (Phase 9, no API calls)
- Replaying the cassette with `MINDMAP_PROVIDER=gemini`, all sockets blocked and `.env` loading disabled reproduces the live result **exactly on 11 metrics**: requests, outcomes, nodes, validity, connectivity, first-pass, repairs, input and output tokens, estimated cost, recall. There were 0 network attempts.
- **Latency is not reproduced:** replay reports 0 ms, because cassettes don't store latency. The 10,982 ms figure above comes from the live run only.
- With the default provider (Anthropic) replay reports every case as `not_recorded`, as designed. A test (`tests/test_offline_guarantees.py`) checks that replay and the pipeline bench never construct a real provider.

## 5. Findings that correct earlier estimates
- **Input tokens were much lower than estimated.** APPROACH §7 estimated ~1.6K input tokens for generate (characters ÷ 2.5, Anthropic's tokenizer ratio, *including* the 1.5K-character schema). Gemini reported **563**, about 4.5 characters per token on the prompt text alone. The JSON schema appears not to be billed as ordinary input here. That's an inference from one sample.
- **Output dominates cost.** About 94% of the paid-equivalent cost was output, consistent with the "thinking drives cost" expectation. Gemini thinking was left at the model default, and lowering it is the obvious lever. Its quality impact is unmeasured.
- **One generate on Gemini 3.6 Flash** cost **$0.0066 paid-equivalent**, inside the earlier estimated range ($0.003–0.010) but toward its top end.

## 6. Limitations
1. **n = 1.** No statistical claim is possible; this is a functional smoke test.
2. Gemini results say nothing about Claude.
3. Lexical recall can give credit for concepts mentioned only inside summaries.
4. The cassette stores only `Usage` (input, output, cache), not Gemini's thinking-token breakdown, so the thinking split above is inferred.
5. The "billed $0" figure depends on the project tier the user confirmed.
6. Fixtures and expectations are AI-written.

## 7. Next step (needs separate approval)
Full suite: 9 request-making cases (generate and grow, including the ceiling, the 63K document, injection and the identical-document case), at most 18 requests, `--pause-s 10`, `--max-cost-usd 2.00` paid-equivalent.

## 8. Pipeline bench (separate; NOT live model results)
These come from `mindmap eval --mode pipeline`, with scripted model output and seeded fuzzing. They measure how the code handles model output, **not model quality**.

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
