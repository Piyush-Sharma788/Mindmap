# REQUIREMENTS_CHECKLIST — Visualli Mini Mindmap Engine

> Every requirement is individually checkable. Update **Status** as work progresses.
> Status values: `NOT STARTED` · `DESIGNED` (architecture only) · `IN PROGRESS` · `IMPLEMENTED` · `VERIFIED` · `BLOCKED` · `DEVIATION (see TD-x)`
> **Crit** = ⛔ critical (a direct [SPEC] constraint or a listed submission-sinker) · ● normal
> **Verification** says *how* to prove the item, ideally with an automated, offline test.

Last updated: Phase 2 (2026-11-11). **VERIFIED** = an automated offline test (in `make test`) or a recorded command run supports the item. **IMPLEMENTED** = the code exists but nothing automated checks it yet. **BLOCKED** = needs a live, paid model run, which awaits approval.

Phase 2 notes:
- No live LLM request has been made. Every model-dependent item is verified only against scripted fake responses. Live quality, real token counts and real cost are BLOCKED.
- SEC-1: the structural defences are verified (delimiters neutralised, output validated and bounded). Whether the model actually ignores injected instructions needs the live eval.
- DEL-4: the README names the provider, models and parameters; the IDs are not yet confirmed by a live call.
- AR-16: the design (no agent loop) is implemented; its justification belongs in APPROACH.md.

---

## A. Data contract

| ID | Requirement | Crit | Status | Verification |
|---|---|---|---|---|
| DC-1 | `MindmapNode {id, label, summary}`, `MindmapConnection {from, to, label}` and `Mindmap {title, rootId, nodes, connections}` are implemented exactly as specified | ⛔ | VERIFIED | Unit test: round-trip a valid fixture; unknown or missing fields are rejected |
| DC-2 | The contract is defined in **one place** | ⛔ | VERIFIED | Code review plus a grep showing no second definition of the field names |
| DC-3 | The provider schema (tool / JSON schema) is **derived** from that definition, not hand-written | ⛔ | VERIFIED | Test: the schema sent to the provider equals the schema produced from the contract module |
| DC-4 | Node ids are unique | ⛔ | VERIFIED | Unit test: duplicate ids fail validation or are repaired, with the repair logged |
| DC-5 | `rootId` matches a real node | ⛔ | VERIFIED | Unit test: a bogus rootId fails validation |
| DC-6 | No dangling edges | ⛔ | VERIFIED | Unit test: an edge to an unknown id fails or is dropped and reported |
| DC-7 | No self-loops | ⛔ | VERIFIED | Unit test: `from == to` fails or is dropped and reported |
| DC-8 | `label` is 1–4 words (enforcement policy per TD-12) | ● | VERIFIED | Unit test using the chosen policy |
| DC-9 | `summary` is one sentence (policy per TD-12) | ● | VERIFIED | Unit test using the chosen policy |
| DC-10 | Ids are **stable**: code assigns them, they are deterministic or persisted, and grow never changes them | ⛔ | VERIFIED | Test: every id from before grow is present and unchanged after grow |
| DC-11 | Validation runs on **every** model output before it is returned or written | ⛔ | VERIFIED | Test: a fake provider returning invalid output never yields an invalid map |

## B. Generate

| ID | Requirement | Crit | Status | Verification |
|---|---|---|---|---|
| GEN-1 | `generate(text) -> Mindmap` exists as a library function | ⛔ | VERIFIED | Unit test with a fake provider |
| GEN-2 | Output has **5–9 nodes** | ⛔ | VERIFIED | Tests: fake provider returns 3 / 7 / 12 nodes → the result is 5–9 or an explicit error (never a silently invalid map) |
| GEN-3 | Output passes all DC validations | ⛔ | VERIFIED | Test plus an eval metric (validity rate on live runs) |
| GEN-4 | LLM calls and input tokens are bounded (a defined maximum input size) | ● | VERIFIED | Test: a huge doc → bounded prompt size, or a clear rejection |
| GEN-5 | Any retry or repair loop has a hard cap | ● | VERIFIED | Test: an always-invalid fake provider → stops after N calls with an error |

## C. Grow

| ID | Requirement | Crit | Status | Verification |
|---|---|---|---|---|
| GROW-1 | `grow(map, text) -> larger Mindmap` exists as a library function | ⛔ | VERIFIED | Unit test with a fake provider |
| GROW-2 | **Existing nodes survive** (id, label, summary unchanged per TD-9) | ⛔ | VERIFIED | Property test: the old node set ⊆ the new node set, byte-identical |
| GROW-3 | The map is **not regenerated** (existing structure kept, existing edges kept per TD-9) | ⛔ | VERIFIED | Test: old edges ⊆ new edges; the old rootId and title are unchanged |
| GROW-4 | Material already covered is **dropped** | ⛔ | VERIFIED | Offline test: a fake provider proposes a duplicate concept and it is not added. Eval: duplication-rate metric on paired docs |
| GROW-5 | Result has **≤ 25 nodes** | ⛔ | VERIFIED | Property test: any input (including a map already at 25) gives a result ≤ 25 |
| GROW-6 | When the ceiling binds, the **most valuable** material is kept (value definition per TD-6) | ⛔ | VERIFIED | Test: candidates with known priorities → the top-k are kept |
| GROW-7 | Left-out material is **reported** and never silently discarded | ⛔ | VERIFIED | Test: the overflow report lists every candidate not added (with a reason: duplicate or ceiling) |
| GROW-8 | **≤ 2 LLM calls per grow**, retries included | ⛔ | VERIFIED | Test: a counting fake provider with docs of 1 KB, 100 KB and 1 MB → calls ≤ 2 every time. Also a hard guard in code (raises on a 3rd call) |
| GROW-9 | **Grow cost does not grow with document length** (bounded prompt tokens) | ⛔ | VERIFIED | Test: prompt size for a 1 KB and a 1 MB doc ≤ a fixed constant |
| GROW-10 | New nodes connect into the existing graph (no orphans; policy per TD-11) | ● | VERIFIED | Unit test |
| GROW-11 | Grow on an unchanged or duplicate document adds nothing and reports it | ● | VERIFIED | Test with a fake provider, plus an eval case |
| GROW-12 | Grow of a map already at 25 nodes adds nothing and reports all candidates as overflow | ● | VERIFIED | Unit test |
| GROW-13 | Accounting invariant: candidates = added + duplicates + omitted, and every omitted item has a reason | ⛔ | VERIFIED | Property test with a fake provider |
| GROW-14 | Excerpt coverage (`sent_ratio`) is reported in GrowResult, so text dropped before the model is not silent | ● | VERIFIED | Unit test on a long document |
| GROW-15 | SDK automatic retries are disabled (`max_retries=0`) | ⛔ | VERIFIED | Offline construction test with a dummy key and no request |
| GROW-16 | Transient errors, refusals and truncations each consume a budget slot. Exactly 2 attempts, then a typed error | ⛔ | VERIFIED | Fakes that always raise or always return garbage → exactly 2 calls |
| GROW-17 | No embedding or token-count requests. `anthropic` is imported in exactly one module | ⛔ | VERIFIED | Grep test |

## D. Render & CLI

| ID | Requirement | Crit | Status | Verification |
|---|---|---|---|---|
| CLI-1 | `generate --in --out` command | ⛔ | VERIFIED | CLI test with a fake provider |
| CLI-2 | `grow --map --in --out` command | ⛔ | VERIFIED | CLI test with a fake provider |
| CLI-3 | `render --map --out` produces valid **Mermaid** | ⛔ | VERIFIED | Snapshot test, plus a test that labels containing Mermaid-special characters are escaped |
| CLI-4 | `eval --suite <dir>` runs the eval suite | ⛔ | VERIFIED | Run it in replay or offline mode in tests |
| CLI-5 | The CLI reports errors with a non-zero exit code. Provider failures are never shown as success | ⛔ | VERIFIED | Test: a failing fake provider → non-zero exit and no output file written |
| CLI-6 | The overflow report is visible to the CLI user (stdout, a sidecar file or a result field) | ⛔ | VERIFIED | CLI test |
| CLI-7 | The CLI is thin: logic lives in the library | ● | IMPLEMENTED | Code review |

## E. Evaluation (20%)

| ID | Requirement | Crit | Status | Verification |
|---|---|---|---|---|
| EV-1 | Define what is measured (metrics chosen and justified in APPROACH.md) | ⛔ | IMPLEMENTED (APPROACH §10) | APPROACH.md section exists |
| EV-2 | An eval suite directory with a set of document cases (generate and grow pairs) | ⛔ | IMPLEMENTED (10 live cases + offline pipeline bench) | `evals/` exists, with the case count stated |
| EV-3 | `eval` outputs **real numbers** (e.g. validity rate, call count, duplicate rate, preservation, coverage, cost) | ⛔ | BLOCKED | Run the command; the output is saved in the repo and quoted in APPROACH.md |
| EV-4 | Two runs can be compared, so that a change can be shown to be better or worse | ● | IMPLEMENTED (results JSON diff; before/after bench files; `eval compare` not built) | Results stored as JSON with a diff or compare step |
| EV-5 | Every number in APPROACH.md is reproducible by the code | ⛔ | IN PROGRESS (pipeline numbers trace to evals/results; live numbers pending) | Cross-check each number against an eval output file before submission |
| EV-6 | Adversarial or injection cases are included in the suite | ● | IMPLEMENTED | Suite contents |

## F. Untrusted input & security

| ID | Requirement | Crit | Status | Verification |
|---|---|---|---|---|
| SEC-1 | Document text is treated as data, never as instructions (delimiting, system/user separation, structured output) | ⛔ | IN PROGRESS | Eval case: a doc containing "ignore previous instructions…" still yields a valid, on-topic map |
| SEC-2 | Model output is validated and sanitised (lengths, control characters, no instructions passed through) | ⛔ | VERIFIED | Unit tests |
| SEC-3 | Input size and encoding limits (huge, binary or invalid UTF-8 files fail cleanly) | ● | VERIFIED | Unit tests |
| SEC-4 | Mermaid output escapes user-derived text (no syntax breakage or injection into the rendered output) | ● | VERIFIED | Unit test with hostile labels |
| SEC-5 | No credentials in the repo **at any commit**. `.env` is gitignored before the first commit | ⛔ | VERIFIED | `git log -p` secret scan (e.g. gitleaks or a grep) before pushing |
| SEC-6 | Logs do not leak full user documents or API keys by default | ● | IMPLEMENTED | Code review |

## G. Agentic design, model strategy, cost, observability

| ID | Requirement | Crit | Status | Verification |
|---|---|---|---|---|
| AG-1 | A justified position on where an agent loop is used or rejected | ⛔ | IMPLEMENTED (APPROACH.md written) | APPROACH.md |
| AG-2 | Guardrails: hard call caps, validation gates, timeouts | ⛔ | VERIFIED | Code plus tests (GROW-8, GEN-5) |
| AG-3 | Observability: each LLM call is logged with model, tokens, latency, purpose and call index | ● | VERIFIED | Test: a trace or usage record is produced per operation |
| MS-1 | Model per step is chosen and justified | ⛔ | IN PROGRESS (justified in APPROACH §4; no live comparison) | APPROACH.md |
| MS-2 | Parameters set (temperature, max_tokens, etc.), with the effect of each stated | ⛔ | IMPLEMENTED (APPROACH §4; effects not measured) | APPROACH.md, ideally with eval evidence |
| COST-1 | Cost of one generate and one grow is computed from real token usage | ⛔ | BLOCKED | Eval output records tokens × price |
| COST-2 | The cheapest change that would roughly halve the cost is identified | ⛔ | IMPLEMENTED (estimate only; APPROACH §7) | APPROACH.md |
| ERR-1 | Provider errors propagate as errors. No catch-all returns canned output | ⛔ | VERIFIED | Test: a fake provider raises → the library raises a typed error |
| ERR-2 | No function implies a model call while doing keyword or hardcoded work | ⛔ | IMPLEMENTED | Code review of names |

## H. Testing & code quality (15%)

| ID | Requirement | Crit | Status | Verification |
|---|---|---|---|---|
| TEST-1 | All tests pass with **no API key** | ⛔ | VERIFIED | Run tests with provider env vars unset |
| TEST-2 | Tests pass on a **clean clone** (no local state, fixed seeds, no absolute paths, no network) | ⛔ | VERIFIED | Fresh `git clone` into a temp dir → setup command → test command |
| TEST-3 | The provider is injectable (fake or recorded provider for tests) | ⛔ | VERIFIED | Code review |
| TEST-4 | Reasonable module structure and typing | ● | IMPLEMENTED | Code review |

## I. Deliverables & process

| ID | Requirement | Crit | Status | Verification |
|---|---|---|---|---|
| DEL-1 | A public repository URL | ⛔ | NOT STARTED | Open the URL logged out |
| DEL-2 | README: a **one-command** setup | ⛔ | VERIFIED | Run it on a clean clone |
| DEL-3 | README: a **one-command** test run with no key | ⛔ | VERIFIED | Run it on a clean clone |
| DEL-4 | README: the providers and models used | ⛔ | VERIFIED (doc-checked IDs; no live call) | README review |
| DEL-5 | APPROACH.md: design blocks and where model calls sit | ⛔ | IMPLEMENTED (APPROACH.md written) | Review |
| DEL-6 | APPROACH.md: every number with the failure it prevents (or "guessed, untested") | ⛔ | IMPLEMENTED (APPROACH.md written) | Grep code constants against the APPROACH table |
| DEL-7 | APPROACH.md: cost of generate and grow, plus a change that halves it | ⛔ | IMPLEMENTED (estimates; measured cost pending live run) | Review |
| DEL-8 | APPROACH.md: one thing deliberately not done with a model | ⛔ | IMPLEMENTED (APPROACH.md written) | Review |
| DEL-9 | APPROACH.md: what was built and thrown away | ⛔ | IMPLEMENTED (APPROACH.md written) | Review (keep a running log during development) |
| DEL-10 | APPROACH.md: known bugs not fixed | ⛔ | IMPLEMENTED (APPROACH.md written) | Review (keep a running log) |
| DEL-11 | APPROACH.md: what was cut, and what we would do with a month | ⛔ | IMPLEMENTED (APPROACH.md written) | Review |
| DEL-12 | APPROACH.md: the AI tools used and which parts they wrote | ⛔ | IMPLEMENTED (APPROACH.md written) | Review |
| DEL-13 | APPROACH.md is short, honest and lists trade-offs (not only strengths) | ⛔ | IMPLEMENTED (APPROACH.md written) | Review |
| DEL-14 | A time note: actual time, and what is rough | ⛔ | IMPLEMENTED (APPROACH §15; author must add own review time) | Review |
| PROC-1 | Commit at each logical milestone. Bursts disclosed | ⛔ | IMPLEMENTED (milestone commits; bursts disclosed in APPROACH §15) | `git log` review |
| PROC-2 | Each AI-assisted line can be defended and every number explained (interview readiness) | ⛔ | IN PROGRESS (author review needed) | Self-review pass over constants and prompts |
| PROC-3 | Every tunable number lives in `config.py`, with its reason and status (spec, reasoned or guessed) | ⛔ | IMPLEMENTED | Code review. APPROACH.md's numbers table is generated from, or cross-checked against, config |

## J. Architecture decisions (Phase 1). Status DESIGNED = specified on paper only, not implemented or tested

| ID | Decision | Covers | Status | Architecture verification criterion (checked in implementation phases) |
|---|---|---|---|---|
| AR-1 | Single-source contract (`contract.py`). Wire schemas reuse the contract's field types. The provider schema comes from `model_json_schema()` | DC-1–3 | VERIFIED | Drift tests: schema sent to the provider equals the derived one; field descriptions are identical; committed `schema/mindmap.schema.json` matches the regenerated file |
| AR-2 | `LLMProvider` protocol. Services never import `anthropic` or `typer` | TEST-3, CLI-7 | VERIFIED | Import-graph test: no `anthropic` import outside `llm/anthropic_provider.py` |
| AR-3 | Five-layer call-budget enforcement (no SDK retries, CallBudget, every attempt counts, no hidden requests, tests) | GROW-8, GROW-15–17 | VERIFIED | Tests listed in ARCHITECTURE §7 pass |
| AR-4 | Grow = one main call plus at most one repair call (TD-3) | GROW-8 | VERIFIED | Happy path = 1 call. Failure path = exactly 2 calls, then an error |
| AR-5 | Deterministic `select_passages` bounds the document part of the prompt (TD-4) | GROW-9, GEN-4 | VERIFIED | Prompt size ≤ bound for 1 KB, 100 KB and 1 MB documents. Selection is deterministic |
| AR-6 | Hybrid dedup: model `duplicate_of` plus a normalised-label backstop (TD-5) | GROW-4 | VERIFIED | Unit tests for both paths. Eval `duplicate_leakage` reported |
| AR-7 | Importance-based admission under capacity: greedy by parent chain (Phase 4, TD-6, P4-3) | GROW-5–7, GROW-12 | VERIFIED | Exact-set tests. Ceiling never exceeded. Every omission has a reason |
| AR-8 | `GrowResult` / `GenerateResult` report objects. The contract file stays pure. Report goes to a sidecar JSON (TD-7) | GROW-7, CLI-6 | VERIFIED | CLI test: `--out` validates as a pure `Mindmap`, and the report file exists |
| AR-9 | Code-assigned slug ids with collision suffixes (TD-8) | DC-4, DC-10 | VERIFIED | Collision test against existing ids |
| AR-10 | Strict append-only "survive" with a post-condition check (TD-9) | GROW-2, GROW-3 | VERIFIED | Property test: old nodes and edges ⊆ new, byte-equal |
| AR-11 | Validation and repair policy table, with every repair logged (TD-10) | DC-5–9, GEN-2, ERR-1 | VERIFIED | Each table row has a fake-provider test |
| AR-12 | Typed errors, CLI exit codes, atomic writes, no catch-all in services | ERR-1, CLI-5 | VERIFIED | Failing-provider test: non-zero exit, no output file |
| AR-13 | Untrusted-input protections (ARCHITECTURE §10) | SEC-1–6 | VERIFIED | Injection eval cases, hostile Mermaid snapshot, size and encoding tests |
| AR-14 | Observability: a UsageRecord per request (in `<out>.report.json`; `--trace` not built), no document text in logs | AG-3, COST-1 | VERIFIED | Test: one record per request, with the expected fields |
| AR-15 | Eval: deterministic tier plus quality tier; replay/live/record modes; cassettes; `compare` (TD-14) | EV-1–6 | IMPLEMENTED | `eval --mode replay` runs from a clean clone with no key and reproduces the committed results JSON |
| AR-16 | No agent loop. A fixed DAG with a bounded repair step (TD-13) | AG-1, AG-2 | IMPLEMENTED (argued in APPROACH §1) | APPROACH.md argument plus the call-budget tests |
| AR-17 | Provider: Anthropic. Model per step from config. **Model choice pending the user and eval data** (TD-2) | MS-1, MS-2 | IN PROGRESS | Eval comparison table: model × effort → quality and cost |
| AR-18 | Cost from real `usage` × a dated price table (TD-18) | COST-1, COST-2 | VERIFIED | Unit test of `cost()`. Eval output includes $ per operation |

## K. Gemini provider (Phase 3, live-eval provider)

| ID | Requirement | Crit | Status | Verification |
|---|---|---|---|---|
| GEM-1 | GeminiProvider uses the official `google-genai` SDK. It is the only module importing it, and the Anthropic provider is untouched | ⛔ | VERIFIED | `test_each_sdk_is_imported_in_exactly_one_module` |
| GEM-2 | SDK retries disabled (`HttpRetryOptions(attempts=1)`), timeout set in ms | ⛔ | VERIFIED | `test_sdk_retries_disabled_and_timeout_in_ms` |
| GEM-3 | Structured output uses the derived schema (with the nullable rewrite only) | ⛔ | VERIFIED | `test_request_uses_derived_schema...`, `test_gemini_schema_only_rewrites_nullable_anyof` |
| GEM-4 | Usage read from `usage_metadata` (input excludes cached tokens; output includes thinking) | ● | VERIFIED (mocked) | `test_usage_text_and_metadata_mapping`. Real field values: BLOCKED (no live call) |
| GEM-5 | Safety blocks, token limits and empty responses become stop reasons, never invented text | ⛔ | VERIFIED (mocked) | `test_finish_reasons_mapped_without_inventing_text` |
| GEM-6 | 429 (with RetryInfo), auth, 4xx, 5xx, timeout and connection errors map to typed errors | ⛔ | VERIFIED (mocked) | `test_errors_mapped_to_typed_provider_errors` |
| GEM-7 | Grow stays ≤ 2 requests with the Gemini provider | ⛔ | VERIFIED (mocked) | `test_grow_with_gemini_never_exceeds_two_requests` |
| GEM-8 | `GEMINI_API_KEY` from env or `.env`. Values never printed. `.env` gitignored. No Anthropic key needed | ⛔ | VERIFIED | dotenv tests, `test_gemini_selected_without_key_exits_2...`, `git check-ignore .env` |
| GEM-9 | The model works on the live API and returns valid structured output | ⛔ | BLOCKED | Needs the user's key and approval for a smoke test |
| GEM-10 | Free-tier status of the user's project confirmed (no billing) | ⛔ | BLOCKED | The user checks AI Studio → Projects (tier) and the rate-limit page; it cannot be seen offline |

## L. Phase 4: quality and reliability (offline evidence only; no live run)

| ID | Item | Crit | Status | Verification |
|---|---|---|---|---|
| P4-1 | Passage selection does not spend the budget on references/tables | ● | VERIFIED | bench: appendix share 49.8% → 0.5% (107K); `test_selection_keeps_topics_and_avoids_appendix_junk` |
| P4-2 | The excerpt bound holds after neutralisation | ⛔ | VERIFIED | `test_input_bound_holds_for_documents_full_of_delimiter_tags` |
| P4-3 | Grow keeps the most valuable material under the ceiling (no priority inversion) | ⛔ | VERIFIED (scripted) | `test_important_child_is_not_starved...`; bench value vs optimum, minimum 62.5% → 100% (400 seeds). Real model importance: not measured |
| P4-4 | Duplicate backstop catches article/case/plural variants without false merges | ● | VERIFIED | `test_label_key_precision`, `test_backstop_catches...`; bench 0 false merges |
| P4-5 | Spaced delimiter variants are neutralised | ⛔ | VERIFIED | `test_spaced_delimiter_variants_are_neutralised`; bench 100% integrity |
| P4-6 | The long-document eval case exercises late-document material | ● | IMPLEMENTED | all 7 late topics reach the excerpt (deterministic). Model behaviour: BLOCKED (no live run) |
| P4-7 | The offline pipeline bench is a regression gate in `make test` | ● | VERIFIED | `tests/test_pipeline_bench.py` |
| P4-8 | Model quality (concept recall, duplicate leakage, relevance) measured | ⛔ | BLOCKED | needs an approved live run (Gemini free tier proposed) |

## M. Phase 5: submission readiness (2026-11-11)

| ID | Item | Status | Evidence |
|---|---|---|---|
| P5-1 | APPROACH.md covers every PDF section plus the 16 requested topics | IMPLEMENTED | APPROACH.md §1–15; live findings marked pending |
| P5-2 | LIVE_EVALUATION_REPORT.md | IMPLEMENTED (status: NOT RUN) | No key configured; no results invented |
| P5-3 | Live Gemini smoke test (Step A) and full run (Step B) | BLOCKED | Needs `GEMINI_API_KEY`, free-tier confirmation and approval |
| P5-4 | Clean clone: setup + offline tests + CLI examples | VERIFIED | See the Phase 5 report: clean clone, `make setup`, `make test`, CLI smoke |
| P5-5 | No credentials in history; no unneeded generated files tracked | VERIFIED | `git log -p` secret scan; `git ls-files` review |

## N. Phase 6: ownership and final audit

| ID | Item | Status | Evidence |
|---|---|---|---|
| P6-1 | Code walkthrough with exact file:line references | IMPLEMENTED | CODE_WALKTHROUGH.md (line references checked against the source index) |
| P6-2 | Interview preparation: 20 Q&A, trade-offs, 5 exercises | IMPLEMENTED | INTERVIEW_PREPARATION.md; exercises 1–3 trial-run on a scratch clone (outcomes recorded), 4–5 not trial-run |
| P6-3 | Audit found no new functional defect; no code changed in Phase 6 | VERIFIED | `git diff` of Phase 6 touches only docs |
| P6-4 | The author's review % and hands-on time | BLOCKED (author) | Placeholders in APPROACH §14–15 |
