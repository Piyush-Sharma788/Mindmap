# REQUIREMENTS_CHECKLIST — Visualli Mini Mindmap Engine

> Every requirement is individually checkable. Update **Status** as work progresses.
> Status values: `NOT STARTED` · `DESIGNED` (architecture only: no code, no tests) · `IN PROGRESS` · `DONE` · `BLOCKED` · `DEVIATION (see TD-x)`
> **Crit** = ⛔ critical (a direct [SPEC] constraint or a listed submission-sinker) · ● normal
> **Verification** says *how* to prove the item, ideally with an automated, offline test.

Last updated: Phase 1 (2026-11-11). Every implementation item (sections A–I) is still **NOT STARTED**. The architecture decisions are in section J and marked **DESIGNED**. See `ARCHITECTURE.md` and `TECHNICAL_DECISIONS.md`.

---

## A. Data contract

| ID | Requirement | Crit | Status | Verification |
|---|---|---|---|---|
| DC-1 | `MindmapNode {id, label, summary}`, `MindmapConnection {from, to, label}` and `Mindmap {title, rootId, nodes, connections}` are implemented exactly as specified | ⛔ | NOT STARTED | Unit test: round-trip a valid fixture; unknown or missing fields are rejected |
| DC-2 | The contract is defined in **one place** | ⛔ | NOT STARTED | Code review plus a grep showing no second definition of the field names |
| DC-3 | The provider schema (tool / JSON schema) is **derived** from that definition, not hand-written | ⛔ | NOT STARTED | Test: the schema sent to the provider equals the schema produced from the contract module |
| DC-4 | Node ids are unique | ⛔ | NOT STARTED | Unit test: duplicate ids fail validation or are repaired, with the repair logged |
| DC-5 | `rootId` matches a real node | ⛔ | NOT STARTED | Unit test: a bogus rootId fails validation |
| DC-6 | No dangling edges | ⛔ | NOT STARTED | Unit test: an edge to an unknown id fails or is dropped and reported |
| DC-7 | No self-loops | ⛔ | NOT STARTED | Unit test: `from == to` fails or is dropped and reported |
| DC-8 | `label` is 1–4 words (enforcement policy per TD-12) | ● | NOT STARTED | Unit test using the chosen policy |
| DC-9 | `summary` is one sentence (policy per TD-12) | ● | NOT STARTED | Unit test using the chosen policy |
| DC-10 | Ids are **stable**: code assigns them, they are deterministic or persisted, and grow never changes them | ⛔ | NOT STARTED | Test: every id from before grow is present and unchanged after grow |
| DC-11 | Validation runs on **every** model output before it is returned or written | ⛔ | NOT STARTED | Test: a fake provider returning invalid output never yields an invalid map |

## B. Generate

| ID | Requirement | Crit | Status | Verification |
|---|---|---|---|---|
| GEN-1 | `generate(text) -> Mindmap` exists as a library function | ⛔ | NOT STARTED | Unit test with a fake provider |
| GEN-2 | Output has **5–9 nodes** | ⛔ | NOT STARTED | Tests: fake provider returns 3 / 7 / 12 nodes → the result is 5–9 or an explicit error (never a silently invalid map) |
| GEN-3 | Output passes all DC validations | ⛔ | NOT STARTED | Test plus an eval metric (validity rate on live runs) |
| GEN-4 | LLM calls and input tokens are bounded (a defined maximum input size) | ● | NOT STARTED | Test: a huge doc → bounded prompt size, or a clear rejection |
| GEN-5 | Any retry or repair loop has a hard cap | ● | NOT STARTED | Test: an always-invalid fake provider → stops after N calls with an error |

## C. Grow

| ID | Requirement | Crit | Status | Verification |
|---|---|---|---|---|
| GROW-1 | `grow(map, text) -> larger Mindmap` exists as a library function | ⛔ | NOT STARTED | Unit test with a fake provider |
| GROW-2 | **Existing nodes survive** (id, label, summary unchanged per TD-9) | ⛔ | NOT STARTED | Property test: the old node set ⊆ the new node set, byte-identical |
| GROW-3 | The map is **not regenerated** (existing structure kept, existing edges kept per TD-9) | ⛔ | NOT STARTED | Test: old edges ⊆ new edges; the old rootId and title are unchanged |
| GROW-4 | Material already covered is **dropped** | ⛔ | NOT STARTED | Offline test: a fake provider proposes a duplicate concept and it is not added. Eval: duplication-rate metric on paired docs |
| GROW-5 | Result has **≤ 25 nodes** | ⛔ | NOT STARTED | Property test: any input (including a map already at 25) gives a result ≤ 25 |
| GROW-6 | When the ceiling binds, the **most valuable** material is kept (value definition per TD-6) | ⛔ | NOT STARTED | Test: candidates with known priorities → the top-k are kept |
| GROW-7 | Left-out material is **reported** and never silently discarded | ⛔ | NOT STARTED | Test: the overflow report lists every candidate not added (with a reason: duplicate or ceiling) |
| GROW-8 | **≤ 2 LLM calls per grow**, retries included | ⛔ | NOT STARTED | Test: a counting fake provider with docs of 1 KB, 100 KB and 1 MB → calls ≤ 2 every time. Also a hard guard in code (raises on a 3rd call) |
| GROW-9 | **Grow cost does not grow with document length** (bounded prompt tokens) | ⛔ | NOT STARTED | Test: prompt size for a 1 KB and a 1 MB doc ≤ a fixed constant |
| GROW-10 | New nodes connect into the existing graph (no orphans; policy per TD-11) | ● | NOT STARTED | Unit test |
| GROW-11 | Grow on an unchanged or duplicate document adds nothing and reports it | ● | NOT STARTED | Test with a fake provider, plus an eval case |
| GROW-12 | Grow of a map already at 25 nodes adds nothing and reports all candidates as overflow | ● | NOT STARTED | Unit test |
| GROW-13 | Accounting invariant: candidates = added + duplicates + omitted, and every omitted item has a reason | ⛔ | NOT STARTED | Property test with a fake provider |
| GROW-14 | Excerpt coverage (`sent_ratio`) is reported in GrowResult, so text dropped before the model is not silent | ● | NOT STARTED | Unit test on a long document |
| GROW-15 | SDK automatic retries are disabled (`max_retries=0`) | ⛔ | NOT STARTED | Offline construction test with a dummy key and no request |
| GROW-16 | Transient errors, refusals and truncations each consume a budget slot. Exactly 2 attempts, then a typed error | ⛔ | NOT STARTED | Fakes that always raise or always return garbage → exactly 2 calls |
| GROW-17 | No embedding or token-count requests. `anthropic` is imported in exactly one module | ⛔ | NOT STARTED | Grep test |

## D. Render & CLI

| ID | Requirement | Crit | Status | Verification |
|---|---|---|---|---|
| CLI-1 | `generate --in --out` command | ⛔ | NOT STARTED | CLI test with a fake provider |
| CLI-2 | `grow --map --in --out` command | ⛔ | NOT STARTED | CLI test with a fake provider |
| CLI-3 | `render --map --out` produces valid **Mermaid** | ⛔ | NOT STARTED | Snapshot test, plus a test that labels containing Mermaid-special characters are escaped |
| CLI-4 | `eval --suite <dir>` runs the eval suite | ⛔ | NOT STARTED | Run it in replay or offline mode in tests |
| CLI-5 | The CLI reports errors with a non-zero exit code. Provider failures are never shown as success | ⛔ | NOT STARTED | Test: a failing fake provider → non-zero exit and no output file written |
| CLI-6 | The overflow report is visible to the CLI user (stdout, a sidecar file or a result field) | ⛔ | NOT STARTED | CLI test |
| CLI-7 | The CLI is thin: logic lives in the library | ● | NOT STARTED | Code review |

## E. Evaluation (20%)

| ID | Requirement | Crit | Status | Verification |
|---|---|---|---|---|
| EV-1 | Define what is measured (metrics chosen and justified in APPROACH.md) | ⛔ | NOT STARTED | APPROACH.md section exists |
| EV-2 | An eval suite directory with a set of document cases (generate and grow pairs) | ⛔ | NOT STARTED | `evals/` exists, with the case count stated |
| EV-3 | `eval` outputs **real numbers** (e.g. validity rate, call count, duplicate rate, preservation, coverage, cost) | ⛔ | NOT STARTED | Run the command; the output is saved in the repo and quoted in APPROACH.md |
| EV-4 | Two runs can be compared, so that a change can be shown to be better or worse | ● | NOT STARTED | Results stored as JSON with a diff or compare step |
| EV-5 | Every number in APPROACH.md is reproducible by the code | ⛔ | NOT STARTED | Cross-check each number against an eval output file before submission |
| EV-6 | Adversarial or injection cases are included in the suite | ● | NOT STARTED | Suite contents |

## F. Untrusted input & security

| ID | Requirement | Crit | Status | Verification |
|---|---|---|---|---|
| SEC-1 | Document text is treated as data, never as instructions (delimiting, system/user separation, structured output) | ⛔ | NOT STARTED | Eval case: a doc containing "ignore previous instructions…" still yields a valid, on-topic map |
| SEC-2 | Model output is validated and sanitised (lengths, control characters, no instructions passed through) | ⛔ | NOT STARTED | Unit tests |
| SEC-3 | Input size and encoding limits (huge, binary or invalid UTF-8 files fail cleanly) | ● | NOT STARTED | Unit tests |
| SEC-4 | Mermaid output escapes user-derived text (no syntax breakage or injection into the rendered output) | ● | NOT STARTED | Unit test with hostile labels |
| SEC-5 | No credentials in the repo **at any commit**. `.env` is gitignored before the first commit | ⛔ | NOT STARTED | `git log -p` secret scan (e.g. gitleaks or a grep) before pushing |
| SEC-6 | Logs do not leak full user documents or API keys by default | ● | NOT STARTED | Code review |

## G. Agentic design, model strategy, cost, observability

| ID | Requirement | Crit | Status | Verification |
|---|---|---|---|---|
| AG-1 | A justified position on where an agent loop is used or rejected | ⛔ | NOT STARTED | APPROACH.md |
| AG-2 | Guardrails: hard call caps, validation gates, timeouts | ⛔ | NOT STARTED | Code plus tests (GROW-8, GEN-5) |
| AG-3 | Observability: each LLM call is logged with model, tokens, latency, purpose and call index | ● | NOT STARTED | Test: a trace or usage record is produced per operation |
| MS-1 | Model per step is chosen and justified | ⛔ | NOT STARTED | APPROACH.md |
| MS-2 | Parameters set (temperature, max_tokens, etc.), with the effect of each stated | ⛔ | NOT STARTED | APPROACH.md, ideally with eval evidence |
| COST-1 | Cost of one generate and one grow is computed from real token usage | ⛔ | NOT STARTED | Eval output records tokens × price |
| COST-2 | The cheapest change that would roughly halve the cost is identified | ⛔ | NOT STARTED | APPROACH.md |
| ERR-1 | Provider errors propagate as errors. No catch-all returns canned output | ⛔ | NOT STARTED | Test: a fake provider raises → the library raises a typed error |
| ERR-2 | No function implies a model call while doing keyword or hardcoded work | ⛔ | NOT STARTED | Code review of names |

## H. Testing & code quality (15%)

| ID | Requirement | Crit | Status | Verification |
|---|---|---|---|---|
| TEST-1 | All tests pass with **no API key** | ⛔ | NOT STARTED | Run tests with provider env vars unset |
| TEST-2 | Tests pass on a **clean clone** (no local state, fixed seeds, no absolute paths, no network) | ⛔ | NOT STARTED | Fresh `git clone` into a temp dir → setup command → test command |
| TEST-3 | The provider is injectable (fake or recorded provider for tests) | ⛔ | NOT STARTED | Code review |
| TEST-4 | Reasonable module structure and typing | ● | NOT STARTED | Code review |

## I. Deliverables & process

| ID | Requirement | Crit | Status | Verification |
|---|---|---|---|---|
| DEL-1 | A public repository URL | ⛔ | NOT STARTED | Open the URL logged out |
| DEL-2 | README: a **one-command** setup | ⛔ | NOT STARTED | Run it on a clean clone |
| DEL-3 | README: a **one-command** test run with no key | ⛔ | NOT STARTED | Run it on a clean clone |
| DEL-4 | README: the providers and models used | ⛔ | NOT STARTED | README review |
| DEL-5 | APPROACH.md: design blocks and where model calls sit | ⛔ | NOT STARTED | Review |
| DEL-6 | APPROACH.md: every number with the failure it prevents (or "guessed, untested") | ⛔ | NOT STARTED | Grep code constants against the APPROACH table |
| DEL-7 | APPROACH.md: cost of generate and grow, plus a change that halves it | ⛔ | NOT STARTED | Review |
| DEL-8 | APPROACH.md: one thing deliberately not done with a model | ⛔ | NOT STARTED | Review |
| DEL-9 | APPROACH.md: what was built and thrown away | ⛔ | NOT STARTED | Review (keep a running log during development) |
| DEL-10 | APPROACH.md: known bugs not fixed | ⛔ | NOT STARTED | Review (keep a running log) |
| DEL-11 | APPROACH.md: what was cut, and what we would do with a month | ⛔ | NOT STARTED | Review |
| DEL-12 | APPROACH.md: the AI tools used and which parts they wrote | ⛔ | NOT STARTED | Review |
| DEL-13 | APPROACH.md is short, honest and lists trade-offs (not only strengths) | ⛔ | NOT STARTED | Review |
| DEL-14 | A time note: actual time, and what is rough | ⛔ | NOT STARTED | Review |
| PROC-1 | Commit at each logical milestone. Bursts disclosed | ⛔ | NOT STARTED | `git log` review |
| PROC-2 | Each AI-assisted line can be defended and every number explained (interview readiness) | ⛔ | NOT STARTED | Self-review pass over constants and prompts |
| PROC-3 | Every tunable number lives in `config.py`, with its reason and status (spec, reasoned or guessed) | ⛔ | NOT STARTED | Code review. APPROACH.md's numbers table is generated from, or cross-checked against, config |

## J. Architecture decisions (Phase 1). Status DESIGNED = specified on paper only, not implemented or tested

| ID | Decision | Covers | Status | Architecture verification criterion (checked in implementation phases) |
|---|---|---|---|---|
| AR-1 | Single-source contract (`contract.py`). Wire schemas reuse the contract's field types. The provider schema comes from `model_json_schema()` | DC-1–3 | DESIGNED | Drift tests: schema sent to the provider equals the derived one; field descriptions are identical; committed `schema/mindmap.schema.json` matches the regenerated file |
| AR-2 | `LLMProvider` protocol. Services never import `anthropic` or `typer` | TEST-3, CLI-7 | DESIGNED | Import-graph test: no `anthropic` import outside `llm/anthropic_provider.py` |
| AR-3 | Five-layer call-budget enforcement (no SDK retries, CallBudget, every attempt counts, no hidden requests, tests) | GROW-8, GROW-15–17 | DESIGNED | Tests listed in ARCHITECTURE §7 pass |
| AR-4 | Grow = one main call plus at most one repair call (TD-3) | GROW-8 | DESIGNED | Happy path = 1 call. Failure path = exactly 2 calls, then an error |
| AR-5 | Deterministic `select_passages` bounds the document part of the prompt (TD-4) | GROW-9, GEN-4 | DESIGNED | Prompt size ≤ bound for 1 KB, 100 KB and 1 MB documents. Selection is deterministic |
| AR-6 | Hybrid dedup: model `duplicate_of` plus a normalised-label backstop (TD-5) | GROW-4 | DESIGNED | Unit tests for both paths. Eval `duplicate_leakage` reported |
| AR-7 | Importance ranking plus parent-aware admission under capacity (TD-6) | GROW-5–7, GROW-12 | DESIGNED | Exact-set tests. Ceiling never exceeded. Every omission has a reason |
| AR-8 | `GrowResult` / `GenerateResult` report objects. The contract file stays pure. Report goes to a sidecar JSON (TD-7) | GROW-7, CLI-6 | DESIGNED | CLI test: `--out` validates as a pure `Mindmap`, and the report file exists |
| AR-9 | Code-assigned slug ids with collision suffixes (TD-8) | DC-4, DC-10 | DESIGNED | Collision test against existing ids |
| AR-10 | Strict append-only "survive" with a post-condition check (TD-9) | GROW-2, GROW-3 | DESIGNED | Property test: old nodes and edges ⊆ new, byte-equal |
| AR-11 | Validation and repair policy table, with every repair logged (TD-10) | DC-5–9, GEN-2, ERR-1 | DESIGNED | Each table row has a fake-provider test |
| AR-12 | Typed errors, CLI exit codes, atomic writes, no catch-all in services | ERR-1, CLI-5 | DESIGNED | Failing-provider test: non-zero exit, no output file |
| AR-13 | Untrusted-input protections (ARCHITECTURE §10) | SEC-1–6 | DESIGNED | Injection eval cases, hostile Mermaid snapshot, size and encoding tests |
| AR-14 | Observability: a UsageRecord per request, `--trace`, no document text in logs | AG-3, COST-1 | DESIGNED | Test: one record per request, with the expected fields |
| AR-15 | Eval: deterministic tier plus quality tier; replay/live/record modes; cassettes; `compare` (TD-14) | EV-1–6 | DESIGNED | `eval --mode replay` runs from a clean clone with no key and reproduces the committed results JSON |
| AR-16 | No agent loop. A fixed DAG with a bounded repair step (TD-13) | AG-1, AG-2 | DESIGNED | APPROACH.md argument plus the call-budget tests |
| AR-17 | Provider: Anthropic. Model per step from config. **Model choice pending the user and eval data** (TD-2) | MS-1, MS-2 | DESIGNED (partial) | Eval comparison table: model × effort → quality and cost |
| AR-18 | Cost from real `usage` × a dated price table (TD-18) | COST-1, COST-2 | DESIGNED | Unit test of `cost()`. Eval output includes $ per operation |
