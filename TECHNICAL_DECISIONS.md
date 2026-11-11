# TECHNICAL_DECISIONS

> Phase 1 update (2026-11-11). Status: `DECIDED (design)` = chosen, not yet implemented or tested · `PENDING USER` = needs your call · `OPEN` = still to be decided · `DEFERRED` = decided in a later phase with data.
> **Nothing below is proven.** "Guessed" means a number or behaviour chosen by reasoning, which the eval must confirm.
> Architecture: `ARCHITECTURE.md`.

## Summary

| TD | Topic | Status |
|---|---|---|
| 1 | Language / stack | DECIDED (design) |
| 2 | Provider & models | Provider DECIDED · models per step **PENDING USER** |
| 3 | Grow call allocation | DECIDED (design) |
| 4 | Long-document bounding | DECIDED (design), numbers guessed |
| 5 | Duplicate detection | DECIDED (design) |
| 6 | Prioritisation & ceiling | DECIDED (design) |
| 7 | Overflow report format | DECIDED (design) |
| 8 | Node ids | DECIDED (design) |
| 9 | "Survive" strictness | DECIDED (design) |
| 10 | Validation failure policy | DECIDED (design) |
| 11 | Graph shape | DECIDED (design), our own addition |
| 12 | Label / summary rules | DECIDED (design) |
| 13 | Agent loop placement | DECIDED (design) |
| 14 | Evaluation methodology | DECIDED (design), dataset to be written |
| 15 | Offline testing | DECIDED (design) |
| 16 | Untrusted input | DECIDED (design) |
| 17 | Observability | DECIDED (design) |
| 18 | Cost model | DECIDED (design), numbers are estimates |
| 19 | Generate input bounding | DECIDED (design) |
| 20 | Repo / commits | DECIDED (design); committing the PDF is **PENDING USER** |
| 21 | Server-side refusal fallback vs call counting | **PENDING USER** |
| 22 | Sentence segmentation quality | OPEN (accepting a regex heuristic) |

---

## TD-1 Stack — DECIDED (design)
Python 3.11+, Pydantic v2, pytest, Typer, Mermaid text output, stdlib `logging`, official `anthropic` SDK.
- **Why:** Pydantic's `model_json_schema()` lets the contract produce the provider schema (C8), and `messages.parse()` accepts Pydantic models directly.
- **Alternative:** TypeScript with Zod. Equivalent single-source story, but more tooling in a 5–6 h budget.
- **Trade-off:** Pydantic's JSON Schema output may need adapting to the provider's supported subset (`provider_schema()`).
- **Test:** the schema drift tests (ARCHITECTURE §3).

## TD-2 Provider & models — provider DECIDED, models PENDING USER
**Provider: Anthropic Claude API, official Python SDK.** Checked in this phase against Anthropic's API reference, cached 2026-11-03:
| Criterion | Finding |
|---|---|
| Structured JSON output | `output_config.format` with a JSON Schema, or `client.messages.parse()` with a Pydantic model. `strict: true` tool use is also available |
| Reliability controls | Typed exception classes. `max_retries` configurable (default **2**, so it must be set to 0). Per-client and per-request `timeout`. `stop_reason` includes `refusal` and `max_tokens` |
| Pricing (per 1M input / output tokens) | Haiku 5.5 **$0.10 / $0.50** (prompts ≤ 100K tokens; $0.50 / $2.50 above). Sonnet 5.5 **$2 / $10**. Opus 5.5 **$4 / $20**. A 40× spread inside one provider |
| Model availability | `claude-haiku-5-5`, `claude-sonnet-5-5`, `claude-opus-5-5`, all with 1M context |
| Token limits | 1M context and 128K max output. Irrelevant to us because the input is bounded at roughly 8K tokens |
| Measuring real cost | `response.usage` gives `input_tokens`, `output_tokens` (thinking included), `cache_creation_input_tokens` and `cache_read_input_tokens`. Multiply by the dated price table |
| Prompt caching | Minimum cacheable prefix is 512 tokens on these models |

**Alternatives (not verified in this phase; pricing deliberately not quoted):**
- OpenAI: JSON-schema structured outputs and a mature SDK.
- Google Gemini: response schemas and low-cost tiers.

Either fits behind `LLMProvider`. Anthropic was chosen for a 40× cost range within one API, a native Pydantic parse helper, and an explicit retry setting.

**Facts that shape the "parameters" story (verify in Phase 2):**
- **`temperature`, `top_p` and `top_k` cannot be set** on these models (they return 400). Temperature 0 is not available, so **output consistency must be measured** (a consistency metric) rather than assumed.
- The controls we have are `output_config.effort` (low → max: thinking depth and token spend), `max_tokens` (a hard output cap; thinking counts against it), and the schema itself.
- Opus 5.5 always thinks; `effort` defaults to `medium`. Haiku 5.5 has thinking on by default and allows `between_tools` mode only at effort `high` or below. Thinking tokens are billed as output.
- Haiku 5.5 refusals have **no** server-side fallback.

**Models per step: PENDING USER.**
- Engineering default in config: `claude-opus-5-5` for both steps (the quality baseline).
- Candidates the eval will compare: `claude-haiku-5-5` (about 40× cheaper) and `claude-sonnet-5-5`, each at effort `low` and `medium`.
- My recommendation: **pick the per-step model from measured eval numbers** (quality metrics against cost per operation), not from intuition. This is your decision because it trades quality against cost.

## TD-3 Grow call allocation — DECIDED (design): one main call plus at most one repair call
- **Chosen:** call 1 does extraction, novelty judgement (`duplicate_of`), importance and attachment in one structured response. Call 2 is used **only** if call 1 is unusable (transient provider error, refusal, truncation, or a schema- or wire-invalid result). Otherwise grow makes exactly 1 request.
- **Why:**
  - dedup needs the map and the new text in the same context;
  - splitting into extract → dedup calls sends the candidates twice (roughly 2× tokens) and leaves no request for recovery;
  - expected cost ≈ 1 request.
- **Alternatives:**
  - (B) two working calls, extract then dedup and rank. Cleaner separation, and a cheap model for extraction. Rejected because there is no recovery request and the cost is higher.
  - (A') a single call with no repair. Cheapest, but brittle.
- **Disadvantages:** one call carries several jobs, which may lower quality (mitigated by the deterministic dedup backstop and measured by the eval). A refusal on call 1 will probably repeat on call 2.
- **Tests:** counting fake (1 call on the happy path), garbage fake (exactly 2 calls, then error), and a rate-limit fake (exactly 2 calls, then error).

## TD-4 Long-document bounding — DECIDED (design), numbers guessed
- **Chosen:** `select_passages(doc, budget_chars, novelty_against=None)` is **deterministic extractive selection, with no model**.
  1. Segment into sentences (regex) inside paragraphs.
  2. Score each sentence: salience = mean TF-IDF weight of its content words (IDF computed over the document's own sentences) × `(1 − NOVELTY_WEIGHT × overlap)`, where overlap is the share of its content words found in the existing map's labels and summaries (grow only).
  3. Pick greedily by score until the budget is reached.
  4. Re-emit in **original order** with `[…]` markers for the gaps.
- A document that already fits the budget passes through verbatim (the most common case for short documents).
- **Numbers:**
  - `EXCERPT_MAX_CHARS = 24_000` (≈ 6K tokens; *guessed*). A ~4,000-word article fits verbatim, the prompt stays far below Haiku's 100K price tier, and grow input cost stays constant.
  - `NOVELTY_WEIGHT = 0.5` (*guessed*). It down-weights covered material without deleting sentences that mix old and new concepts.
  - `MAX_INPUT_BYTES = 5 MB` (*guessed*). It bounds CPU and memory for the O(n log n) selection.
- **Alternatives:**
  - head truncation: loses the end of the document;
  - uniform sampling: blind to content;
  - embeddings: an API cost per chunk would scale with document length, or a heavy local dependency;
  - map-reduce summarisation: many LLM calls, which breaks C6 and C7.
- **Disadvantages:**
  - lexical scoring misses paraphrase;
  - selection may cluster in one part of the document;
  - the regex sentence splitter mishandles abbreviations;
  - material left out of the excerpt is invisible to the model and cannot be itemised (reported only as `sent_ratio`).
- **Tests:**
  - offline: the output length is ≤ the budget for 1 KB, 100 KB and 1 MB documents;
  - selection is deterministic (same input, same output);
  - a 1 MB document produces a prompt of the same size as a 100 KB one.
  - The eval measures new-concept recall on long documents.

## TD-5 Duplicate detection — DECIDED (design): hybrid
- **Chosen:**
  1. Lexical novelty weighting before the call (TD-4).
  2. The model marks `duplicate_of: <existing id>` with the map in context.
  3. A deterministic backstop: a normalised label (lowercase, punctuation stripped, plural `s` trimmed) equal to an existing label or an earlier candidate's label is a duplicate.
  4. An invalid `duplicate_of` id is ignored and logged.
  - Every duplicate is reported with its source (`model` or `lexical`).
- **Why:** "covered" is semantic, so the model has to judge it, but code can catch obvious misses cheaply and verifiably.
- **Rejected:** fuzzy or Jaccard thresholds on labels. Example: "Machine Learning" against "Machine Learning Ethics" scores Jaccard 0.67, which would wrongly drop a genuinely new concept. Exact normalised matching is high-precision and low-recall by design.
- **Disadvantages:** paraphrased duplicates the model misses will leak through. This is measured as the **duplicate leakage** metric.
- **Tests:** a fake proposes a candidate whose label equals an existing one → dropped as `lexical`; a fake marks `duplicate_of` → dropped as `model`; the accounting invariant holds.

## TD-6 Prioritisation & ceiling — DECIDED (design)
- **Value signal:** the model assigns `importance` on a 1–5 scale. A coarse ordinal scale is likely more stable across runs than 0–100 (*guessed*).
- **Deterministic ranking in code:** importance descending → attached to an existing node before attached to another candidate → emission order.
- **Admission:** walk the ranked list. Admit while capacity > 0 and the attach target is existing or already admitted. Otherwise, omit with reason `ceiling` / `parent_omitted` / `invalid_attach`.
- `MAX_CANDIDATES = 15` (*guessed*): enough for a full refill from the minimum map size (5 → 25 needs 20, so a nearly empty map may not fill completely, which is acceptable), and it bounds output tokens.
- **Map already at or above 25 nodes:** still make one call so that omissions can be reported, as the spec requires. Add nothing and never delete existing nodes ("survive" takes precedence). A map loaded with more than 25 nodes is accepted but flagged.
- **Alternatives:** code-only value (centrality, salience), which is blind to meaning; LLM-chosen final set, which can't be verified.
- **Disadvantages:** the model's importance scores are uncalibrated. A child with high importance under a parent with low importance is omitted (`parent_omitted`). This is a known limitation.
- **Tests:** given importances → the exact admitted set; the ceiling is never exceeded; every omission has a reason.

## TD-7 Overflow report — DECIDED (design)
- A `GrowResult` with `mindmap`, `added`, `duplicates`, `omitted`, `repairs`, `excerpt_stats`, `usage` and `cost_usd`.
- The CLI writes the pure contract map to `--out`, the report to `<out>.report.json`, and a summary to stderr. The contract stays unpolluted.

## TD-8 Node ids — DECIDED (design)
- Code assigns ids. The model uses temporary refs (`c1…`) for new nodes and real ids for existing ones.
- Ids are slugs of the label (`calvin-cycle`), with a `-2`, `-3`… suffix on collision against **all** existing ids.
- They are readable in JSON and in debugging. Mermaid uses its own aliases, so slug characters don't matter there.
- **Tests:** no collision when a new label slugifies to an existing id; existing ids are never touched.

## TD-9 "Survive" — DECIDED (design): strict
Existing nodes stay byte-identical (id, label, summary). Existing edges, `title` and `rootId` are unchanged. Merge is append-only. A post-condition check raises if the rule is violated.

## TD-10 Validation failure policy — DECIDED (design)
| Defect | Action |
|---|---|
| Schema-invalid, truncated or refused output | repair request if the budget allows, else typed error |
| Root ref invalid | repair request, else error |
| Dangling, self-loop or duplicate edge | drop and log |
| Orphan node (generate) | attach to the root with relation "relates to", logged as a repair (an invented edge, which is preferable to deleting content; *debatable*) |
| More than 9 nodes (generate) | trim the lowest importance and report |
| Fewer than 5 nodes (generate) | repair request, else error. **Never pad** |
| Label longer than 4 words | if the budget allows, a repair request is made for other reasons too; otherwise keep the first 4 words and log it |
| Summary longer than one sentence | keep the first sentence and log it |

Every repair appears in `repairs[]`, and the eval reports a **repair rate** so it can never be silent.

## TD-11 Graph shape — DECIDED (design), our own addition, not [SPEC]
Every node must connect to the root (edge direction ignored for reachability). No duplicate `(from, to)` pairs. Cross-links are allowed. Grow attaches each new node with exactly one new edge.

## TD-12 Label / summary rules — DECIDED (design)
- **Label:** 1–4 whitespace-separated tokens; a hyphenated term counts as one word; at most 40 characters (*guessed*). A hard contract validator.
- **Summary:** non-empty, at most 250 characters (*guessed*), and at most one sentence terminator followed by more text (a heuristic; abbreviations like "e.g." can cause false positives, which is a known limitation).
- **Relation label:** 1–4 words, at most 30 characters.
- **Title:** non-empty, at most 80 characters.

## TD-13 Agent loop — DECIDED (design): none
- The pipeline is a fixed DAG. The only loop is "at most one repair request", triggered by validation, not decided by the model.
- **Where a loop could earn its place:**
  - multi-pass reading of very long documents (incompatible with the grow budget);
  - a self-critique pass on generate (it would double cost, and its value is unproven, so it should be tested in the eval first);
  - a free-form tool-using agent: overkill, with an unbounded cost per paid interaction.
- **Guardrails instead of autonomy:** `CallBudget`, `max_tokens`, timeouts, schema-constrained outputs, contract gates, and a repair log.

## TD-14 Evaluation methodology — DECIDED (design), dataset to be written
**Deterministic checks (offline, run in pytest and in `eval --mode replay`):**
| Metric | Definition | Target |
|---|---|---|
| structural_validity | share of outputs that pass the contract validator | 100% |
| node_count_compliance | generate 5–9, grow ≤ 25 | 100% |
| preservation | share of pre-grow nodes byte-identical afterwards | 100% |
| accounting_complete | candidates = added + duplicates + omitted | 100% |
| omitted_have_reason | every omitted item has a reason | 100% |
| grow_calls_max | the largest request count over all grow cases, including the 1 MB document | ≤ 2 |
| prompt_chars_max | the largest prompt size over all document lengths | ≤ the configured bound |

**Quality metrics (live; recorded as cassettes, then replayable offline):**
| Metric | Definition |
|---|---|
| concept_recall | share of the case's `expected_concepts` (each a list of aliases) found lexically in any node label or summary |
| new_concept_recall (grow) | the same, for `expected_new` concepts |
| duplicate_leakage (grow) | share of `expected_covered` concepts that appear in **added** nodes |
| consistency (generate) | mean pairwise Jaccard of normalised label sets across k = 3 runs (*k guessed*: cost against variance) |
| first_pass_validity | share of first responses usable without a repair request |
| repair_rate | repairs per operation |
| injection_followed | share of injection cases whose output contains the planted marker |
| cost_usd, tokens, latency_ms | per operation, from `usage` |

**Dataset plan (to be written in the eval phase):** about 6 generate documents and about 7 grow cases.
- **Generate documents:**
  - a science explainer;
  - a business memo;
  - a history passage;
  - a technical how-to;
  - a very short document (does it still reach 5 nodes?);
  - a long document of about 50K characters (selection is used).
- **Grow cases:**
  1. a disjoint extension;
  2. heavy overlap (dedup);
  3. an identical document (expect 0 added);
  4. a seed map of 23 nodes plus a rich document (the ceiling binds; omissions reported);
  5. a 1 MB synthetic document (budget and bound);
  6. an injection document;
  7. an empty document (expect `InputError` and 0 requests).
- **Each case holds:** `expected_concepts` / `expected_new` / `expected_covered` (alias lists), plus `expect_error` where relevant.

**Not doing:**
- **LLM-as-judge.** It costs money for every eval run, adds variance, and grading Claude with Claude is circular. Recorded as a future improvement.
- **A large dataset.** Six documents give a directional number, not a statistically strong one. APPROACH.md will say so.

**Known weaknesses:**
- Lexical matching under-counts paraphrase, which biases recall downward and leakage downward.
- Hand-written expectations carry the author's bias.
- If AI helps write the fixtures, that must be disclosed.

**"Did a change help?"** `eval compare` shows the difference per metric. Code-only changes are evaluated free through replay. Prompt or model changes require a live re-record (cassette miss is reported explicitly).

## TD-15 Offline testing — DECIDED (design)
`FakeProvider` (scripted, counting, records requests) and `ReplayProvider` (cassettes). Tests never construct a network client except the `max_retries=0` construction test, which uses a dummy key and sends no request. A conftest guard fails any test that tries a real HTTP connection. Cassettes contain responses only, never headers or keys.

## TD-16 Untrusted input — DECIDED (design)
See ARCHITECTURE §10. In short:
- the document is delimited and neutralised;
- the system prompt says the content is data;
- no tools;
- output is schema-constrained and contract-validated;
- size and encoding limits;
- the existing map is also treated as untrusted;
- Mermaid output is escaped;
- no document text in logs;
- no committed secrets, with a scan before every push.

## TD-17 Observability — DECIDED (design)
A `UsageRecord` per request: `op`, `purpose`, `attempt`, `model`, `prompt_version`, input/output/cache tokens, `latency_ms`, `stop_reason`, `outcome`. The records are attached to the result, written by `--trace`, and aggregated by the eval. Python `logging` uses INFO for a one-line summary per request and DEBUG for prompts (only behind `--debug-prompts`).

## TD-18 Cost model — DECIDED (design); **estimates only, untested**
Assumptions (*guessed*):
- generate: about 7.5K input tokens (≈1.5K system and schema + ≤6K excerpt) and about 1.5K output tokens including thinking;
- grow: about 9K input tokens (+ ≈1.5K map) and about 2.5K output tokens.

| Model | generate (1 request) | grow (1 request) | grow worst case (2 requests) |
|---|---|---|---|
| Haiku 5.5 | ≈ $0.0015 | ≈ $0.002 | ≈ $0.004 |
| Sonnet 5.5 | ≈ $0.03 | ≈ $0.043 | ≈ $0.086 |
| Opus 5.5 | ≈ $0.06 | ≈ $0.086 | ≈ $0.17 |

On Sonnet and Opus, output (thinking included) is about half the cost. **Candidate changes that would halve the cost:**
1. a lower `effort` (fewer thinking tokens);
2. a cheaper model for one or both steps;
3. a smaller `EXCERPT_MAX_CHARS`;
4. prompt caching of the static system prompt and schema. This saves only ≈ 15–20% of input, so it is worth doing but not a halving.

Choose the lever by eval data. Prices are dated 2026-11-03 and stored in `pricing.py`.

## TD-19 Generate input bounding — DECIDED (design)
Generate reuses `select_passages` (no novelty term) with the same budget, for the same reasons: untrusted length and cost.

## TD-20 Repo & commits — DECIDED (design)
- `git init` at the start of Phase 2.
- The first commit is `.gitignore` (`.env`, `.venv`, caches) and docs.
- Milestone commits: contract → provider and fake → textprep → generate → grow → render/CLI → eval → docs.
- The time note discloses the real elapsed time.
- **Whether to commit the PDF: PENDING USER.**

## TD-21 Server-side refusal fallback — PENDING USER
- Anthropic recommends enabling `fallbacks: "default"` (beta `server-side-fallback-2026-07-01`) on Opus 5.5 and Sonnet 5.5. A refused request is then re-run on another model **inside the same HTTP request**.
- **Option A (proposed):** enable it, count HTTP requests as "LLM calls", and document that a fallback may run a second model inside one request.
- **Option B:** disable it in grow so that one request equals one model invocation, which removes any ambiguity. A refusal then costs a request slot.
- Haiku 5.5 has no server-side fallback, so this question disappears if Haiku is chosen.

## Phase 2 user decisions (2026-11-11)
- **TD-2:** the default model is `claude-sonnet-5-5` for both steps. Haiku 5.5 is the cost comparison and Opus 5.5 the quality benchmark (evaluation only).
- **TD-20:** the PDF is not committed. `*.pdf` is in `.gitignore`.
- **TD-21:** no server-side refusal fallback anywhere. A refusal consumes a request slot.

## Phase 2 implementation notes and deviations from the design
Each item is either a change from the Phase 1 design or a choice the design left open.
1. **A map with more than 25 nodes is rejected on load** (`InputError`), instead of "accepted but flagged" (TD-6). The contract enforces the ceiling for every map, which is simpler and matches the spec's ceiling. Trade-off: grow cannot take an over-ceiling map produced by another tool.
2. **`effort = "medium"`** is set explicitly (guessed). The API default for Sonnet 5.5 is `high`, and adaptive thinking stays on. The eval has not yet checked quality at this setting.
3. **The system prompt is marked for caching** (`cache_control` on the system block). Below the model's minimum cacheable size it silently does not cache. The benefit is unmeasured.
4. **408 and 409 responses count as retryable**, matching the SDK's own retry classes, but they still use the single budgeted retry.
5. **Not built, though the Phase 1 design mentions them:** the `--trace` flag (per-request usage is in `<out>.report.json` instead), `--debug-prompts`, and `eval compare`.
6. **Contract models strip surrounding whitespace on load** (`str_strip_whitespace`). A loaded map whose labels have padding is normalised on load, so "survive" is checked against the normalised map.
7. **The sentence rule is a hard contract validator** with an abbreviation allow-list. Model output is normalised to its first sentence, and that change is logged, before the contract is applied.
8. **Duplicate-detection normalisation (`label_key`)** removes case, accents and punctuation, and strips a trailing "s" on words longer than 3 letters. This can make different words match (for example "analysis" becomes "analysi", the same as a word that really ends in "analysi"). It applies equally to both sides of a comparison.

## TD-22 Sentence segmentation — OPEN
Use a regex splitter with no NLP dependency (keeps setup to one command). Its weaknesses with abbreviations, decimals and lists are accepted and will be listed as known bugs. Revisit only if the eval shows harm.
