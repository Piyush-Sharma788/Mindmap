# Phase 9 Final Audit: offline evaluation and quality

**Date:** 2026-11-11.

**Scope:** everything was run from existing offline resources. **Zero API calls, zero spending.** `.env` was not loaded or used. Live and record modes were not run, and Git history is unchanged (17 commits, HEAD `2417b0e`). All changes are left uncommitted.

**Labels used:**
- **MEASURED:** an observed value from a test, run or recorded provider response.
- **ESTIMATE:** list price × measured or assumed tokens.
- **INFERRED:** derived reasoning, not directly measured.
- **UNTESTED:** no evidence.

## 1. Commands executed (all offline)
| # | Command | Offline safeguard | Network attempts |
|---|---|---|---|
| 1 | `make test` (start and end) | conftest removes every key variable, sets `MINDMAP_NO_DOTENV=1`, blocks `socket.connect` / `create_connection` | 0 possible (blocked) |
| 2 | `eval --mode pipeline` | wrapper `scratchpad/offline_cli.py`: unsets keys, disables `.env`, blocks sockets and counts attempts | **0** |
| 3 | `eval --suite evals --mode replay` (default provider) | same wrapper | **0** |
| 4 | `MINDMAP_PROVIDER=gemini eval --suite evals --mode replay` | same wrapper | **0** |
| 5 | Fixture audit: generate/grow on every `evals/` document and seed map with scripted adversarial output (`scratchpad/fixture_audit.py`) | `FakeProvider`, sockets blocked, keys unset | **0** |
| 6 | New tests `tests/test_offline_guarantees.py` (run inside `make test`) | real-provider construction is made to raise | n/a |

## 2. Test and benchmark results (MEASURED)
- **Offline tests:** **190 passed** (187 before plus 3 new offline-guarantee tests).
- **Pipeline bench:** output is **byte-identical** to the committed `evals/results/pipeline-bench-after-phase4.json`. Key values:
  - grow fuzz (400 runs): valid, preserved, ≤ 25, accounted and ≤ 2 requests all **1.0**; admitted value vs exact optimum, worst case **1.0**; lexical-variant duplicates caught **1.0**;
  - generate fuzz (300 runs): 0 invalid maps, 0 runs over 2 requests;
  - selection: topic retention 1.0; appendix junk 0.5% at 107K;
  - delimiter integrity **1.0**; Mermaid allow-list **1.0**;
  - dedup pairs: 0 false merges; 2 known misses ("Buses", "Analyses").

  *These measure the code with scripted model output. They are not model quality.*
- **Replay with the default provider:** 0/10 scored; 9 `not_recorded`, 1 expected `InputError`. **Correct by design:** the request key includes the model, and the recording is Gemini.
- **Replay with `MINDMAP_PROVIDER=gemini`:** `gen-photosynthesis` scored. It is **identical to the live run on 11 metrics** (requests, outcomes, nodes, validity, connectivity, first-pass, repairs, input and output tokens, estimated cost, recall). **Latency is not reproduced:** replay shows 0 ms, because cassettes don't store latency.

## 3. Generate and grow coverage on the real fixtures (MEASURED; scripted model output)
| Requirement | Result on fixtures |
|---|---|
| Generate 5–9 nodes | 4/4 generate fixtures: a 12-node reply trimmed to 9 (3 trimmed, reported); valid; connected; self-loop removed |
| Invalid model output → bounded repair | every fixture: invalid first reply → **exactly 2 requests** → valid result |
| Grow ≤ 2 requests | 5/5 grow fixtures: 2 requests (1 invalid + 1 repair); never 3 |
| Existing nodes and connections preserved | 5/5: nodes, edges, title and root byte-identical |
| ≤ 25 nodes and overflow | `grow-ceiling` (23-node seed): final 25, omissions with reason `ceiling` |
| Every candidate accounted for | 5/5 |
| Duplicates excluded | **5/5 planted duplicates caught** on each fixture (4 "The X" variants via the backstop, 1 flagged by the model) |
| Input budget | `grow-long-document`: 63,201 characters in, **22,968 sent** (≤ 24,000); short documents pass through whole |
| Injection containment | delimiters intact on all fixtures, including both injection fixtures |
| Mermaid safety | every rendered map passes the line allow-list |
| Empty document | `InputError`, **0 requests** |
| Cost and token accounting | replay recomputes $0.006644 from the recorded 563 / 1,659 tokens, matching the live record (ESTIMATE basis: list price) |

**Demonstrated limitation:** duplicates use candidate slots. On each grow fixture, 5 duplicates consumed 5 of the 15 slots, pushing 2 new ideas out as `over_candidate_limit` (reported, not silent).

## 4. Phase 8 live smoke test (**n = 1**; generate only; Gemini)
**MEASURED:**
- 1 request; `end_turn`;
- 563 input / 1,659 output tokens; 0 cached;
- 10,982 ms;
- a valid 6-node connected map, 0 repairs, lexical recall 7/7 (3 concepts matched only inside summaries).

**ESTIMATE:** $0.006644 paid-equivalent; $0 billed (free tier, confirmed by the user).

**INFERRED:** about 1,200 of the output tokens were thinking.

**UNTESTED live:** grow, duplicate leakage, preservation and the two-request limit on a real model; injection resistance; error and rate-limit paths; variance; Anthropic.

## 5. Failures, weaknesses and untested requirements
1. **Model quality is essentially unmeasured** beyond one generate sample. No live grow has run.
2. **Replay latency is 0 ms** and its latency aggregates are meaningless. Only quote live latency.
3. **Replay needs matching settings** (provider/model/effort). Otherwise it reports misses. Documented in README now; not a bug.
4. **The CLI loads `.env` in every mode**, including `replay`, `pipeline` and `render` ([cli.py:124](src/mindmap/cli.py#L124)). Keys enter the process environment even though no provider is built in those modes. **No live-call risk** (proved by the new tests), but it's unnecessary exposure. Fix: load it only when constructing a real provider. Not changed in this phase.
5. **Duplicates share the 15-candidate limit** (demonstrated on fixtures, §3).
6. The cassette stores only aggregate usage, not Gemini's thinking-token count.
7. `test_replay_scores_recorded_gemini_case_without_any_provider` **skips** if the cassette isn't committed. The cassette is currently untracked.
8. Everything else in APPROACH §12: greedy admission, lexical backstop misses, sentence heuristics, excerpt loss reported only as a ratio, refusal retry wasting a request, a small AI-written eval set.

**No requirement failed** in any offline check.

## 6. Files modified and created (all uncommitted)
- **Created:** `PHASE_9_FINAL_AUDIT.md`, `tests/test_offline_guarantees.py`.
- **Modified:**
  - `LIVE_EVALUATION_REPORT.md` (new §4.5, the offline re-verification);
  - `FINAL_REQUIREMENTS_AUDIT.md` (P8 and L4 evidence; test count 190);
  - `README.md` (how to replay, the latency caveat);
  - `APPROACH.md`, `CODE_WALKTHROUGH.md`, `SUBMISSION_CHECKLIST.md` (test count 190).
- **Uncommitted since Phase 8** (also untracked or modified): `INTERVIEW_PREPARATION.md`, the evaluation cassette, and the `evals/results/smoke-gemini-*` files.
- **Not touched:** source code, existing cassettes and results, Git history, `.env`.

## 7. Final submission blockers
1. **Author placeholders:** APPROACH §14 (your code-review %) and §15 (your hands-on time). These are PDF-required disclosures; only you can fill them.
2. **Commit the pending changes:** docs, the new test, and the cassette and results files (needed for replay evidence on a fresh clone).
3. **Publish:** create the public repository and push, after your approval.
4. *(Strongly recommended, not strictly required)* An approved live full-suite run, especially grow, so that "grow works on a real model" is evidence and not inference.

## 8. Recommendation
**NO-GO for publishing today; GO once blockers 1–3 are cleared.**
- **Engineering:** every offline requirement check passes, on unit tests, fuzzing and real fixtures, with no network access.
- **Not yet submittable as-is:** the PDF-required personal disclosures are unfilled, and the evaluation evidence isn't committed.
- **Without blocker 4:** the submission is honest but thin on live evidence (n = 1, generate only). Disclose that plainly, as the documents already do.
