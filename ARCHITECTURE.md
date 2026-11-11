# ARCHITECTURE — Visualli Mini Mindmap Engine

> **Phase 2 status:** implemented and covered by offline tests, except `--trace`, `--debug-prompts` and `eval compare` (not built), and except anything needing a live model run (not yet done). Deviations are listed in TECHNICAL_DECISIONS.md under "Phase 2 implementation notes".
>
> **Original Phase 1 status: DESIGNED, not implemented, not tested.** Every number here is a design-time choice. Each one is labelled *spec* (given by the PDF), *reasoned* (derived from another constraint) or *guessed* (untested; it must be confirmed or revised by the eval in a later phase).
> Requirements live in `PROJECT_CONTEXT.md`. Decision rationale lives in `TECHNICAL_DECISIONS.md`.

---

## 1. System overview

```
            ┌──────────────────────── CLI (Typer, thin) ─────────────────────────┐
            │ generate │ grow │ render │ eval      → exit codes, files, report      │
            └────┬───────────┬─────────┬──────────┬──────────────────────────────┘
                 │           │         │          │
        ┌────────▼──┐  ┌─────▼─────┐ ┌─▼──────┐ ┌─▼─────────────┐
        │ generate  │  │   grow    │ │ render │ │ eval runner   │
        │ service   │  │  service  │ │(mermaid│ │ metrics,      │
        └──┬──┬──┬──┘  └─┬──┬──┬──┬┘ │ no LLM)│ │ replay/live   │
           │  │  │       │  │  │  │  └────────┘ └──────┬────────┘
           │  │  │       │  │  │  └── dedup · ranking (pure code)
           │  │  │       │  │  └───── assemble/repair (pure code)
           │  │  └───────┼──┴──────── textprep: load, sanitise, select_passages (pure code)
           │  │          │
           │  └──────────┴─► LLMProvider interface ◄── CallBudget (hard cap, raises)
           │                    │            │
           │          AnthropicProvider   FakeProvider / ReplayProvider (tests, eval)
           │          (max_retries=0)
           ▼
        contract.py  ── the single source of truth: Mindmap types, validators, field
                        definitions. wire.py derives the LLM response schemas from it.
```

**Where the model calls are:** only inside `generate` (≤ 2 requests) and `grow` (≤ 2 requests), and only through `LLMProvider.complete()`, which consumes a `CallBudget` slot *before* sending the request. Everything else is deterministic Python: render, dedup, ranking, assembly, passage selection, validation, and the eval scoring.

**No agent loop.** The pipeline is a fixed DAG. The only iteration is one bounded "repair" request when the first response is unusable (§5). The reasons are in TD-13.

---

## 2. Component responsibilities

| Module (planned) | Responsibility | Calls the LLM? |
|---|---|---|
| `contract.py` | Pydantic `MindmapNode`, `MindmapConnection`, `Mindmap`. Shared annotated field types (`Label`, `Summary`, `RelationLabel`, `NodeId`). Graph validators: unique ids, real `rootId`, no dangling edges, no self-loops, no duplicate edges, connectivity. Count rules (5–9 / ≤25) are parameters of the validators, not new types | No |
| `wire.py` | LLM response schemas (`GenerateProposal`, `GrowProposal`), built **from the contract's field types**. `provider_schema(model)` exports the JSON Schema sent to the provider | No |
| `config.py` | **Every tunable number in one place**, each with a comment giving its reason and status (spec, reasoned or guessed) | No |
| `errors.py` | Typed errors: `InputError`, `ConfigError`, `ProviderError` (subtypes: RateLimited, Timeout, Unavailable, BadRequest), `ModelOutputError`, `CallBudgetExceeded` | No |
| `textprep.py` | Decode and sanitise the document, segment it into sentences and paragraphs, and `select_passages()` deterministic extractive selection into a fixed character budget | **No** (named to make that clear) |
| `prompts.py` | Versioned prompt templates (`PROMPT_VERSION`). Wraps untrusted text in delimiters | No |
| `llm/base.py` | `LLMProvider` protocol, `LLMRequest`, `LLMResult` (parsed object, `stop_reason`, usage, latency) | Interface |
| `llm/budget.py` | `CallBudget(max_calls)`: `acquire()` raises `CallBudgetExceeded` once exhausted | No |
| `llm/anthropic_provider.py` | The only file that imports `anthropic`. Client built with `max_retries=0` and an explicit timeout. Uses structured outputs. Maps SDK errors to typed errors. Checks `stop_reason` (`refusal`, `max_tokens`) before it parses anything | **Yes** |
| `llm/fake.py` | `FakeProvider` (scripted responses, records every request, counts calls), `ReplayProvider` (serves recorded cassettes keyed by request hash) and `RecordingProvider` (wraps the real provider and writes cassettes) | Fake / replay |
| `assemble.py` | Turns a validated wire proposal into a contract `Mindmap`: assigns ids, resolves refs, applies deterministic repairs, and logs every repair | No |
| `dedup.py` | Applies the model's `duplicate_of` marks. Deterministic backstop: normalised-label equality against existing nodes and within the batch | No |
| `ranking.py` | Orders candidates and admits them under the capacity limit, keeping each child attached to a parent that was admitted | No |
| `generate.py` / `grow.py` | Orchestration. Each returns a result object (`GenerateResult` / `GrowResult`) holding the map plus a report | Via provider |
| `render.py` | Mermaid output. Generated aliases (`n0`…) stand in for ids, and every label is escaped | No |
| `pricing.py` | Dated price table and `cost(usage, model)` | No |
| `observability.py` | `UsageRecord` per request, the trace collector, and logging setup (no document text in logs by default) | No |
| `evals/` (package) | Suite loader, runner (modes: replay, live, record), metrics and lexical concept matcher, results JSON and a compare command | Only in live and record modes |
| `cli.py` | Typer commands. Argument parsing, file I/O, exit codes, `.env` loading, `<out>.report.json` | No |

Business logic (`generate`, `grow`, `dedup`, `ranking`, `assemble`) depends only on `LLMProvider` and `contract`. It never imports `anthropic` or `typer`.

---

## 3. Single source of truth for the contract

```
contract.py
  Label        = Annotated[str, Field(description="1-4 words ...")] + validator (word count)
  Summary      = Annotated[str, Field(description="One sentence ...")] + validator
  RelationLabel, NodeId ...
  MindmapNode(id: NodeId, label: Label, summary: Summary)
  MindmapConnection(from_: NodeId alias "from", to: NodeId, label: RelationLabel)
  Mindmap(title, rootId, nodes, connections) + model_validator(graph rules)
        │  (field types reused, never retyped)
        ▼
wire.py
  CandidateNode(ref, label: Label, summary: Summary, importance, ...)
  GenerateProposal / GrowProposal
        │  .model_json_schema()  → provider_schema() adapts it to the provider's supported subset
        ▼
AnthropicProvider: output_config.format = provider_schema(GrowProposal)
```

- **Drift tests (offline):**
  1. The schema handed to the provider equals `provider_schema(WireModel)`, captured through `FakeProvider`.
  2. Every description in the wire schema for `label` and `summary` is byte-identical to the contract's.
  3. `Mindmap.model_json_schema()` is exported to `schema/mindmap.schema.json` and a test fails if the committed file differs. That file is a generated artifact, never hand-edited.
- **Why wire models differ from `Mindmap`:** the model must not invent ids (collisions, drift), and grow needs extra fields (`duplicate_of`, `importance`, `attach_to`). They are separate *shapes* built from the same *field definitions*, so the drift risk is in the shapes only, and the tests above cover it.
- **Known risk:** structured-output engines usually support only a subset of JSON Schema. Keywords such as `minItems`/`maxItems`, `pattern` or `maxLength` may be stripped or rejected. Any constraint the provider can't express is enforced in code, which the contract requires anyway. This must be checked against the provider docs in Phase 2.

---

## 4. Generate workflow

```
doc bytes
 → [1] load & validate input      (size ≤ MAX_INPUT_BYTES, strict UTF-8, strip control chars, non-empty)   code
 → [2] select_passages(doc, budget=EXCERPT_MAX_CHARS)  (passes through verbatim if it already fits)      code
 → [3] build prompt (system: task + rules; user: <document>…</document>; target 7 nodes)                  code
 → [4] LLM call #1 → GenerateProposal (structured output)                                                LLM
 → [5] check stop_reason; parse; validate wire model ─ unusable? ─→ [4b] repair call #2 (with errors)     LLM (≤1)
 → [6] assemble: ref→id (slugs), resolve root, drop dangling/self/dup edges, attach orphans to root,
       enforce 5–9 (trim lowest importance if > 9; if < 5 and budget left → repair call; else error)     code
 → [7] Mindmap.model_validate (final contract gate)                                                     code
 → GenerateResult { mindmap, repairs[], trimmed[], excerpt, usage[], usage_summary }
```

- **Budget:** `GENERATE_MAX_CALLS = 2` (reasoned: the PDF sets no limit, but grow's discipline is applied for consistency and cost predictability).
- **< 5 nodes after repair:** raise `ModelOutputError`. Never pad with invented nodes.
- **> 9 nodes:** trim deterministically by `importance`, then by emission order. The trimmed nodes are reported.

---

## 5. Grow workflow (≤ 2 LLM requests, hard)

```
existing Mindmap (validated on load) + doc2 bytes
 → [1] load & validate input                                                           code
 → [2] capacity = 25 − len(existing.nodes)  (if ≤ 0: still one call, so that omissions
       can be reported; see TD-6)                                                        code
 → [3] select_passages(doc2, budget=EXCERPT_MAX_CHARS,
                       novelty_against = existing labels+summaries)                     code
 → [4] prompt: system rules; <existing_map> id|label|summary rows (≤25, bounded) </existing_map>;
       <document> excerpt </document>; ask for ≤ MAX_CANDIDATES candidates           code
 → [5] LLM call #1 → GrowProposal                                                     LLM
       candidates[]: { ref:"c1", label, summary, importance 1-5,
                       duplicate_of: <existing id> | null,
                       attach_to: <existing id> | "cK", relation }
 → [6] stop_reason / parse / wire validation ─ unusable? ─→ call #2 (repair, last one)  LLM (≤1)
       call #2 also unusable → raise ModelOutputError (nothing written)
 → [7] dedup:  model-marked duplicates → duplicates[] (reason "model")
              normalised label == existing label, or == an earlier candidate → duplicates[] (reason "lexical")
              invalid duplicate_of id → treated as not-a-duplicate + repair log            code
 → [8] resolve parents: attach_to → existing id | new candidate; duplicates redirect to what
              they duplicate; unusable targets and attach cycles → root (logged)        code
 → [9] admit (greedy by parent chain, Phase 4): repeatedly take the most important remaining
              candidate whose chain (itself + not-yet-admitted new ancestors) fits the
              remaining capacity, and admit the chain parents-first. Ties: shorter chain,
              attached to an existing node, emission order. The rest → omitted[] "ceiling".
              Earlier rejections: "invalid", "over_candidate_limit"                        code
 → [10] append-only merge: new nodes get fresh ids (never collide with existing ids),
        new edges attach_to → new node with relation; existing nodes/edges/title/root untouched  code
 → [11] Mindmap.model_validate(max_nodes=25) + preservation check (old ⊆ new, byte-equal)          code
 → GrowResult { mindmap, added[], duplicates[], omitted[], repairs[],
                excerpt{doc_chars, sent_chars, sent_ratio}, usage[], usage_summary }
```

**Accounting invariant (tested):** `len(candidates) == len(added) + len(duplicates) + len(omitted)`. Every proposed concept is accounted for, so nothing is discarded silently.

**Material that never reached the model** (the excerpt dropped it) is a second kind of omission. It is reported as `excerpt.sent_ratio` and listed as a known limitation. It cannot be itemised as concepts without another model call.

### 5.1 Why one main call plus one repair call (not two working calls)
- One call sees both the map and the excerpt, so it can decide "new or already covered" with full context. Splitting extraction and dedup into two calls would send the candidates twice and roughly double the tokens. It would also leave **no** request for recovery, so any malformed response would be a hard failure.
- Expected cost ≈ 1 request, worst case 2. Details and alternatives are in TD-3.

### 5.2 Arbitrary document length with bounded cost
- The only document-dependent part of the prompt is the excerpt, capped at `EXCERPT_MAX_CHARS`. The map part is capped by the 25-node ceiling and per-field length limits. The output is capped by `MAX_CANDIDATES` and `max_tokens`. So **prompt tokens ≤ a constant** and **requests ≤ 2**, whether the document is 1 KB or 5 MB.
- CPU work in `select_passages` is roughly O(n log n) in document length, and the input is hard-capped at `MAX_INPUT_BYTES`. Our reading of "cost" in the failure list is **LLM spend**. APPROACH.md will say so explicitly.
- No embeddings, no `count_tokens` request, and no per-chunk calls. Token counts before sending are **local estimates** (chars ÷ 4, conservative), so the enforced invariant is in *characters*. Billed tokens come from the API's `usage` afterwards.

---

## 6. Provider abstraction

```python
class LLMProvider(Protocol):          # llm/base.py (as implemented)
    name: str
    def complete(self, request: LLMRequest) -> LLMResponse: ...   # exactly ONE request, no internal retry
# LLMRequest: purpose, attempt, model, system, messages, schema, max_tokens, effort, cache_system_prompt
# LLMResponse: text, stop_reason, model, usage (provider-reported), provider, request_id
# Budget is NOT a provider concern: BudgetedCaller (llm/budget.py) acquires a slot, then calls complete().
```

- **AnthropicProvider:** `anthropic.Anthropic(max_retries=0, timeout=REQUEST_TIMEOUT_S)`, structured outputs via `output_config.format` (or `messages.parse` with the wire model), and a typed exception chain (most specific first) mapped to `ProviderError` subtypes. It reads content blocks **by type**, because current models may return thinking blocks before the text. It checks `stop_reason` first: `refusal` → `ProviderError(Refused)` and `max_tokens` → `ModelOutputError(Truncated)`.
- **GeminiProvider** (added in Phase 3, `llm/gemini_provider.py`) is the only module that imports `google-genai`. It sends one `models.generate_content` call per `complete()`, with:
  - `HttpRetryOptions(attempts=1)`, so the SDK never retries;
  - a timeout in milliseconds;
  - JSON-schema output, using the same derived schema with nullable `anyOf` rewritten to `type: [X, "null"]`.
  
  It maps finish reasons onto the same stop reasons the engine already handles: `SAFETY`/`PROHIBITED_CONTENT`/... become `refusal`, `MAX_TOKENS` becomes `max_tokens`, and a blocked prompt becomes `refusal`. It maps API errors to the same typed errors, parsing the server's `RetryInfo` delay on a 429. Usage: `prompt_token_count` minus cached tokens is input; candidate tokens plus thinking tokens is output; cached tokens count as cache reads.
- **Retry rule (both providers):** a retryable error is retried once, within the budget, only when the server's requested delay is at most `RETRY_AFTER_MAX_S`. A longer delay (typical of exhausted daily quotas) fails at once instead of spending the second request on another 429.
- **Model per step** comes from config or environment variables (`MINDMAP_MODEL_GENERATE`, `MINDMAP_MODEL_GROW`), so changing provider or model never touches the services. A second provider means one more file that implements the protocol.
- **Credentials:** the provider is never constructed in tests. The CLI constructs it lazily and turns a missing credential into `ConfigError` with exit code 2 *before* any file is written. The SDK also resolves `ant auth` profiles, so "no `ANTHROPIC_API_KEY`" does not always mean "no credentials". The error message mentions both.

---

## 7. Call-budget enforcement (grow ≤ 2 requests)

Five layers. Any one of them is enough on its own; together they are hard to bypass by accident.

1. **No SDK retries:** the client is built with `max_retries=0`. An offline test builds the provider with a dummy key, makes no request, and asserts `client.max_retries == 0`.
2. **CallBudget:** `grow()` creates `CallBudget(GROW_MAX_CALLS)` (=2). `provider.complete()` calls `budget.acquire()` *before* sending. A third acquire raises `CallBudgetExceeded`, which is a bug, not a recoverable state.
3. **Every attempt counts:** timeouts, 429s, 5xx responses, refusals and truncations all consume a slot. A transient error on request 1 may use request 2 as its only retry (honouring `retry-after` up to `RETRY_AFTER_MAX_S`). If that also fails, the result is a typed error, never canned output.
4. **No hidden requests:** no embeddings and no token-count requests. The only `anthropic` import is in one file (a test greps for it).
5. **Tests:**
   - a counting `FakeProvider` with documents of 1 KB, 100 KB and 1 MB asserts `calls ≤ 2` and that the prompt length is under the fixed bound;
   - a fake that always returns garbage asserts exactly 2 calls followed by `ModelOutputError`;
   - a fake that always raises a rate-limit error asserts exactly 2 calls followed by `ProviderError`.

**Open point (TD-21):** Anthropic recommends server-side refusal fallbacks (`fallbacks: "default"`) for Opus 5.5. That is one HTTP request, but the server may run a second model. We count **HTTP requests**. If an assessor counts model invocations instead, this could be challenged, so it needs your decision.

---

## 8. Data flow and result objects

- Input files are read only by the CLI or library loaders. Services take `str` and `Mindmap` objects, which keeps them pure and testable.
- The CLI writes **only the contract `Mindmap`** to `--out`. The report (added, duplicates, omitted, repairs, excerpt stats, usage, cost) goes to `<out>.report.json`, which includes the per-request `UsageRecord`s, and a short summary goes to stderr. The contract file is never polluted with extra fields.
- Writes are atomic (temporary file, then rename), and nothing is written on failure.

---

## 9. Error handling

| Situation | Behaviour | Exit code |
|---|---|---|
| Missing or invalid credentials | `ConfigError` before any request | 2 |
| Input too big, not UTF-8, empty, or invalid map JSON | `InputError` before any request | 3 |
| Provider timeout, 429, 5xx or connection error | one retry within the budget, then `ProviderError` | 4 |
| Refusal (`stop_reason: refusal`) | consumes a slot. The same request is resent once within the budget (it will probably refuse again). Then `ModelOutputError` | 5 |
| Malformed or truncated output | repair request if budget remains, else `ModelOutputError` | 5 |
| Fixable graph defects (dangling edges, self-loops, orphans, > 9 nodes, invalid `duplicate_of`) | deterministic repair, **logged in `repairs[]`** | 0 |
| Fewer than 5 nodes after repair | `ModelOutputError`, never padded | 5 |
| `CallBudgetExceeded` | a bug, so crash loudly | 70 |

There is no catch-all `except Exception` anywhere in the services. The CLI has one top-level handler that prints the error and exits non-zero. It never prints success.

---

## 10. Security: untrusted input

| Threat | Mitigation | Verification |
|---|---|---|
| Prompt injection in the document | The document goes only in the user turn, inside `<document>` tags. Any `</document>`-like sequence in it is neutralised. The system prompt says the content is data to summarise, never instructions. No tools are enabled. Output is schema-constrained, so the worst case is a misleading node, which validation bounds by length and form | Eval cases: injection document (generate) and injection document plus a poisoned existing map (grow). Metric: `injection_followed` (lexical check for the planted marker) |
| A poisoned existing map (labels or summaries from an earlier document, or a hand-edited file) | Treated as data too: wrapped in `<existing_map>`, re-validated against the contract on load, field lengths capped | Unit test |
| Malformed LLM responses | Structured outputs, then wire-model validation, then contract validation, all before anything is returned | Fake-provider tests |
| Invalid ids or connections | The model never sets ids. Refs are resolved against an allow-list. Dangling, self-loop and duplicate edges are dropped and reported | Unit tests |
| Oversized or binary input | `MAX_INPUT_BYTES`, strict UTF-8 decoding, NUL and control characters stripped, empty input rejected | Unit tests |
| Mermaid injection (`"`, `]`, `%%`, `click`, HTML in labels) | The renderer uses its own aliases, escapes quotes and brackets, strips newlines, and truncates | Snapshot test with hostile labels |
| Cost-amplification attacks (huge documents) | Bounded excerpt, bounded output, ≤ 2 requests | Budget tests (§7) |
| Data leakage in logs | No document text is logged at any level. Logs hold sizes, counts and outcomes only (`--debug-prompts` was designed but not built) | Code review |
| Credential leakage | Keys come from the environment or the SDK's profile resolution only. `.env` is in `.gitignore` before the first commit. The key is never logged. A secret scan runs over `git log -p` before every push | Pre-push check |

---

## 11. Cost control

- Cost per request = `usage` × the dated price table (`pricing.py`). Cache reads and writes are priced separately. Thinking tokens are billed as output and are included in `output_tokens`.
- **Levers designed in:** bounded excerpt; a compact map representation (`id|label|summary`, no edges); `MAX_CANDIDATES`; `max_tokens`; `effort`; an expected one request per operation (the repair request is rare); a static system prompt plus schema placed first so they can be cached (the minimum cacheable prefix is 512 tokens on current models, and our system prompt plus schema will probably exceed it); the model chosen per step from config.
- **Estimates:** see TD-18. These are *guessed, untested* until the live eval records real usage.

---

## 12. Evaluation architecture

```
evals/                    # as implemented
  cases.json              # case id, kind (generate|grow), doc, seed map, expectations
  docs/*.txt              # AI-written fixtures (incl. a generated 63K report)
  maps/*.json             # seed maps for grow cases
  cassettes/<request-hash>.json   # recorded responses (created by --mode record; none yet)
  results/*.json          # eval and pipeline-bench outputs
```

- **Modes:**
  - `pipeline` (no key): the deterministic bench on scripted model output (Phase 4). It is not a model-quality measurement.
  - `replay` (default, no key) serves cassettes and recomputes every metric offline.
  - `live` calls the real provider and costs money.
  - `record` is live plus writing cassettes.
- **What replay lets you test:** code-side changes (dedup, ranking, assembly, selection *only if the prompt stays identical*) are measured offline for free. A prompt or model change changes the request hash, so replay reports cassette misses and that case needs a live re-record. This is how we tell whether a change helped, and it is honest about what can and cannot be evaluated offline.
- **Two tiers of checks:**
  - **Deterministic invariants** (pytest plus eval, fake provider): validity, call count, prompt bound, preservation, ceiling, accounting invariant, escaping.
  - **Quality metrics** (eval, live, or replayed from live recordings): concept recall, new-concept recall, duplicate leakage, pre-repair validity, repair rate, injection, cost, latency.
- **Metric definitions** are in TD-14. Comparing two runs means diffing their results JSON; an `eval compare` command was designed but not built. Consistency across k runs was cut.
- No LLM-as-judge in this version (reasons in TD-14). Concept matching is **lexical by design and named that way** (`match_concepts_lexically`).
