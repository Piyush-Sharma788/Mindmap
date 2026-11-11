# APPROACH

> **Status (2026-11-11):** the engine works end to end against scripted model output, and that is covered by 191 offline tests. **The only live model call so far is one live Gemini smoke-test request (`gen-photosynthesis`, see LIVE_EVALUATION_REPORT.md):** 1 request, a valid 6-node map, 0 repairs, 563 input / 1,659 output tokens, about $0.0066 paid-equivalent ($0 on the free tier). The full live suite has not been run, so most model-quality statements below are still marked *pending* or *estimate*. Pipeline numbers come from committed files you can re-run.

## 1. Design

```
CLI (Typer, thin) ──► generate() / grow()                                   ◄── eval runner
                        │
   textprep: validate → neutralise tags → select_passages (fixed char budget)   [code]
                        │
   prompts (static system + delimited untrusted text)                           [code]
                        │
   BudgetedCaller ── CallBudget(2) ──► LLMProvider.complete()  ◄── the ONLY model calls
                        │               (Anthropic | Gemini | Fake | Replay)
   structured: parse → validate → at most one repair or retry                   [code]
                        │
   generate: assemble (ids, edges, 5–9, connectivity)                           [code]
   grow:     dedup → resolve parents → greedy admission ≤ 25 → append-only merge [code]
                        │
   contract.Mindmap validation  +  report (added / duplicates / omitted / repairs / usage)
```

- **Model calls happen in exactly one place:** `LLMProvider.complete()`, called through `BudgetedCaller`. Generate and grow each make one structured call, plus at most one repair or retry.
- **The contract is defined once:** `contract.py` (Pydantic). `wire.py` builds the LLM response shapes from the contract's field types. `provider_schema()` generates the schema the provider receives. `schema/mindmap.schema.json` is generated too, and drift tests fail if any of them diverge.
- **Agentic design: no agent loop.** The pipeline is a fixed graph of steps. The only "loop" is one repair request, triggered by code validation, never by the model's own judgement.
  - **Why no agent loop:** each user interaction is paid for, the spec caps grow at 2 calls, and every step has a deterministic definition of "done". An agent that decides how often to read, re-check or call tools would make cost and latency unbounded, and is overkill here.
  - **Where one could earn its place:** a self-critique pass on generate, but only if the eval showed it adds quality worth roughly 2× the cost. That hasn't been measured.
  - **Guardrails:**
    - CallBudget raises *before* a third request is sent;
    - SDK retries are off (Anthropic `max_retries=0`, Gemini `HttpRetryOptions(attempts=1)`);
    - schema-constrained output;
    - contract validation on every output;
    - typed errors, and no catch-all that returns canned output.
  - **Observability:** a `UsageRecord` per request (purpose, attempt, model, outcome, latency, prompt characters, provider-reported tokens, estimated cost) in `<out>.report.json`, and one log line per request with `-v`. Document text is never logged.

## 2. Generate and grow
- **Generate:**
  1. Bound the document.
  2. One structured call asks for about 7 nodes, using temporary refs and importance scores.
  3. Code assigns slug ids, drops dangling, self-loop and duplicate edges, collapses duplicate labels, and attaches any orphan to the root (logged).
  4. More than 9 nodes: code trims the least important. Fewer than 5: one repair request; if that fails, an error. **It never pads.**
- **Grow:**
  1. Bound the document, favouring sentences not already covered by the map.
  2. One structured call. Each candidate states `duplicate_of`, `importance` (1–5), `attach_to` and a relation.
  3. Code drops duplicates: the model's judgement plus a lexical backstop.
  4. Code admits candidates under the 25-node ceiling and appends them.
  5. Post-conditions check that the existing nodes, edges, title and root are **byte-identical**, and that **every proposed candidate is accounted for** as added, duplicate or omitted, with a reason.

## 3. What is deliberately done in code, not by a model
- **Passage selection (the main example).** A model that summarises a long document must either see all of it (cost grows with length) or work chunk by chunk (more calls). Either breaks the spec's grow rules.
  - `select_passages` is extractive and deterministic: IDF-weighted terms, a prose-ratio weight, and novelty against the existing map.
  - It fills a fixed character budget, so **grow's input cost is constant above about 24K characters**.
  - It is named for what it does; it doesn't call itself a summariser.
- **Also code, not model:** ids, graph repair, the lexical duplicate backstop, admission under the ceiling, merging and Mermaid rendering. These steps must be exactly reproducible and testable, and a model adds nothing there that a few lines of code can't do.

## 4. Model, provider and structured output
- **Provider abstraction:** `LLMProvider.complete(request)` sends exactly one request. Two real implementations exist (`anthropic_provider.py`, `gemini_provider.py`), each the only module importing its SDK (a test checks this).
- **Anthropic** (the design target): `claude-sonnet-5-5` by default. Haiku 5.5 is the cheaper comparison and Opus 5.5 the quality benchmark; both are unmeasured.
  - Structured output via `output_config.format`.
  - `effort=medium` (*guessed*; the API default is `high`).
  - **No `temperature`:** current Claude models reject sampling parameters, so run-to-run consistency has to be *measured*, not set. The plan was a consistency metric, which was cut (§13).
- **Gemini:** `gemini-3.6-flash`, chosen because it is stable and free of charge on the free tier (official docs, checked 2026-11-11). It was added because no Anthropic key was available. It receives the same derived schema, with one documented rewrite (nullable `anyOf` → `type: [X, "null"]`). **Any live numbers measure Gemini, not Claude.**
- **What the parameters do:**
  - `max_tokens` = 16,000 caps the worst-case output cost per request. Thinking counts against it.
  - `effort` controls thinking depth, which is the main output-cost driver on Sonnet.
  - The schema removes the free-form JSON failure mode. Limits the schema can't express (string lengths, 1–4 words) are enforced in code.

## 5. Grow's two-request limit
Five layers, any one of which is enough on its own:
1. **No SDK retries.** Both SDKs are configured with retries off.
   - For Gemini I read the SDK source. It has an implicit connection retry, but only in its async aiohttp path. We use the sync path, and the explicit retry setting turns the async one off too.
2. **`CallBudget(2)`.** It is acquired *before* each send, and a third acquire raises `CallBudgetExceeded`.
3. **Every attempt counts:** timeouts, 429s, 5xx errors, refusals and truncations alike.
4. **No hidden requests:** no embeddings, no token-counting calls, no server-side fallback.
5. **Tests:**
   - documents of 1 KB, 100 KB and 1 MB → 1 request, and the prompt stays within the bound;
   - always-garbage, always-refused or always-rate-limited output → exactly 2 requests, then a typed error;
   - the same checks run against the Gemini provider with real SDK error types;
   - **400 fuzzed grow runs: 100% made ≤ 2 requests** (pipeline bench).

A server-requested retry delay over 10 s is not retried. Retrying that soon would only burn the second request on another 429.

## 6. Duplicates, ranking and overflow
- **Duplicates come in two layers:**
  - the model judges semantic coverage and marks `duplicate_of`;
  - code backs that up with an exact match on a normalised label (case, accents, punctuation, a leading article, regular plurals).
- **Why no fuzzy matching:** a fuzzy threshold would wrongly merge "Machine Learning" with "Machine Learning Ethics". The backstop is high-precision on purpose: 0 false merges on 7 near-miss pairs; known misses are "Buses" and "Analyses". Paraphrases the model misses do leak. That is measured as *duplicate leakage* in the live eval (pending).
- **Value** is the model's importance score, 1–5.
- **Admission** is greedy by parent chain. It repeatedly admits the most important candidate whose chain (itself plus any new parents not yet admitted) fits the remaining room, parents first.
  - This replaced a first version that let a high-importance child starve.
  - Pipeline bench, 400 fuzzed runs: worst case **62.5% → 100%** of the exact optimum (the oracle is an independent tree-knapsack).
  - Greedy is not guaranteed optimal in general.
- **Overflow:** everything not added is listed in `<out>.report.json` and on stderr with a reason: `ceiling`, `invalid` or `over_candidate_limit`. A map that is already full still makes one call, so that what was left out can be reported.

## 7. Cost per operation
**Measured:** prompt sizes (offline, exact characters sent; reproduce with `python -m mindmap.evals.prompt_sizes`), plus **one live Gemini generate**: 563 input / 1,659 output tokens, about $0.0066 paid-equivalent. That shows the input estimate below is about 2.8× too high for Gemini; output (about 94% of the cost) matched expectations. **Not measured:** grow, anything on Anthropic, and variance. The table below is the original estimate, kept as written.

| | Prompt chars (measured) | Input tokens (est., 2.5 chars/token) | Output tokens (est.: JSON + 0–2K thinking) | Sonnet 5.5 (est.) | Gemini 3.6 Flash paid-equivalent (est.) |
|---|---|---|---|---|---|
| generate | 2.1–2.5K + 1.5K schema | ~1.6K | 0.4–2.4K | **$0.007–0.027** | $0.003–0.010 (free tier: $0) |
| grow, typical | 3.2–5.2K + 1.4K schema | ~1.9–2.6K | 0.8–2.8K | **$0.012–0.033** | $0.004–0.012 |
| grow, ~24K-char excerpt (the bound) | 25.6K + 1.4K | ~10.8K | 0.8–2.8K | $0.030–0.050 | $0.011–0.019 |
| hard worst case per operation | 2 requests × (40K in + 16K out) | | | $0.48 | $0.18 |

- **The cheapest change that roughly halves cost (not measured):** with these estimates, output is about 55–90% of Sonnet's cost, and most of it is thinking. Setting `MINDMAP_EFFORT=low`, or turning thinking off (`between_tools` on Sonnet 5.5), is a one-line config change.
- **Bigger lever:** Haiku 5.5 at $0.10/$0.50 is about 20× cheaper, but its quality is unmeasured.
- **Caching:** the system prompt is marked cacheable, but it is only about 1K tokens of each request, so caching saves well under half.

## 8. Untrusted input
- **Size and encoding:** `MAX_INPUT_BYTES` (5 MB), strict UTF-8, control characters stripped, an empty document rejected before any call.
- **Delimiting:** the document and the existing map are untrusted data inside `<document>` and `<existing_map>`. Any tag-like text in them is escaped *before* selection, so the input bound still holds. The system prompt says embedded instructions are content, not commands.
  - Phase 4 found and fixed a bypass: `< /document`, with a space before the slash.
  - Bench: 100% delimiter integrity on hostile documents.
- **No tools; schema-constrained output.** At worst, an injection produces a misleading node. That node is still capped by length, word count and the one-sentence rule.
  - Whether the model actually *ignores* an injection is a live metric (`injection_followed`, pending).
- **Rendering:** Mermaid output uses generated aliases and entity-escapes all text. Bench: 300 hostile maps, 100% of lines match an allow-list.
- **Keys:** read only from the environment or a gitignored `.env`; never logged; the history secret scan is clean. Gemini's free tier lets Google use the content, so it isn't suitable for confidential documents.

## 9. Every number and the failure it prevents
| Number | Where | Prevents | Status |
|---|---|---|---|
| 5–9 nodes, 25 max, 2 grow calls | config | spec violations | spec |
| 2 generate calls | config | unbounded repairs | reasoned (same discipline as grow) |
| 24,000 excerpt chars | config | input cost growing with document length | guessed; bench shows 30/30 topics kept on a 107K report |
| 600 segment chars | config | a punctuation-free document becoming one giant "sentence" | guessed |
| 0.5 novelty weight | config | grow re-reading what the map already covers, without deleting mixed sentences | guessed, untested |
| prose ratio (multiplier) | textprep | reference lists and tables winning on rare tokens | measured: appendix share 49.8% → 0.5% |
| 15 candidates | config | unbounded output; fewer than the 20 a nearly empty map could take | guessed |
| importance 1–5 | config | noisy fine-grained scores | guessed, untested |
| 16,000 max output tokens | config | runaway cost; room for thinking | guessed |
| 180 s timeout, 10 s retry-after cap, 1 s default wait | config | hung requests; blocking users for minutes on a long quota | guessed |
| 4 words / 40 chars per label, 250-char summary, 4 words / 30 chars per relation, 80-char title | config | unreadable nodes; one "word" that is really 300 characters | spec (4 words), otherwise guessed |
| 40K worst-case input tokens | pricing | an under-estimated spending ceiling | reasoned (largest measured prompt: 25.6K chars + 1.4K schema ≈ 11K tokens *estimated*; the one live Gemini count was far lower) |
| 2.5 chars per token | pricing | wrong token estimates | Anthropic's documented ratio; used only for estimates |

## 10. Evaluation
- **Two kinds of measurement, kept separate:**
  1. **Pipeline bench** (`eval --mode pipeline`, offline, seeded). It measures the code around the model, with scripted model output, and is a regression gate in `make test`. Results are in `evals/results/pipeline-bench-{before,after}-phase4.json`. **It says nothing about model quality.**
  2. **Live / replay eval** (`eval --mode record|replay`). 10 cases: 4 generate and 6 grow, covering overlap, an identical document, the ceiling, a 63K report with new material at the end, injection, and an empty document. Metrics:
     - concept recall and new-concept recall (lexical alias matching, which undercounts paraphrase);
     - duplicate leakage;
     - validity, first-pass success and repairs;
     - requests, tokens, cost and latency;
     - injection marker.
     
     Recordings replay offline, so code-only changes can be re-scored for free. A prompt or model change misses the recordings by design.
- **Findings so far are pipeline-only:** the five bugs fixed in Phase 4 (see TECHNICAL_DECISIONS, P4-1 to P4-6).
- **Live findings so far** (Gemini smoke test, n = 1): a valid 6-node map, 1 request, 0 repairs, lexical recall 7/7 (some concepts matched only inside summaries). The full suite is pending.
- **Weaknesses:** small n (10 cases); AI-written fixtures and expectations; lexical matching; no LLM judge (cost and circularity); no human labels.

## 11. Built, changed or thrown away
- **Thrown away:**
  - the "rank then admit in passes" grow admission (priority inversion);
  - the `parent_omitted` reason;
  - a long-document eval case that repeated one document (deduplication collapsed it to 3.5K characters);
  - a "-ses" plural rule I added and reverted after it broke "Leases";
  - a 10% cache-read price that is wrong for Sonnet and Opus (5%).
- **Changed:**
  - the Anthropic-only live plan became a Gemini free-tier plan (no key);
  - "accept a map with more than 25 nodes, flagged" became "reject on load";
  - "retry once on any retryable error" became "not when the server asks for more than 10 s".
- **Considered and rejected:**
  - two working calls in grow (extract, then dedup): about 2× the tokens and no recovery request;
  - embeddings: cost per chunk, or a heavy local dependency;
  - fuzzy label thresholds: false merges;
  - an LLM-as-judge;
  - an agent loop.
- **Designed but not built:** `--trace`, `--debug-prompts`, `eval compare`.
- **Bugs found and fixed.** Each was demonstrated by a failing test or a measurement first; details in TECHNICAL_DECISIONS (Phase 4 table):
  - pricing used a 10% cache-read rate (5% is correct on Sonnet and Opus 5.5);
  - the excerpt ratio was missing from the JSON report;
  - the SDK's missing-credential `TypeError` surfaced as a traceback;
  - passage selection spent about half the budget on references and tables;
  - delimiter escaping after selection broke the input bound;
  - a priority inversion in grow admission;
  - the duplicate backstop missed "The X" and plural variants (my first fix broke "Leases", and was corrected before committing);
  - a `< /document` neutraliser bypass;
  - a usage-totals function was named `summarize`, which read like a model call; renamed `summarize_usage`;
  - the APPROACH §7 prompt sizes came from a scratch script; now reproducible via `mindmap.evals.prompt_sizes`.

## 12. Known bugs and limitations (not fixed)
1. Greedy admission is not optimal in general.
2. Duplicates use up candidate slots (15 in total), so a mostly-covered document can crowd out new concepts.
3. The duplicate backstop misses "-ses" and irregular plurals, and all paraphrases. Paraphrase leakage depends on the model.
4. The one-sentence check and sentence splitting are regex heuristics. Unlisted abbreviations split falsely.
5. Text dropped by the excerpt is reported only as `sent_ratio`, not concept by concept.
6. A refusal retry resends the identical request, so it probably wastes the second call.
7. A map that is already full still costs one call (by design, so omissions can be reported).
8. A failed request has no usage. If a provider bills a timeout, the spending ceiling can't see it.
9. Gemini's cached-token price is unverified (charged at the full input price). Gemini thinking is left at its default, and `effort` is ignored there.
10. The Anthropic credential pre-check treats an existing `~/.config/anthropic` directory as "credentials present".
11. Loaded maps are whitespace-normalised, and maps with more than 25 nodes are rejected.
12. In generate, an orphan node gets an invented "relates to" edge to the root (logged).
13. No streaming: the worst-case wait is 2 × 180 s.
14. Mermaid labels are truncated to 60 characters for display only.

## 13. Cut for time / what another month would buy
- **Cut:**
  - live evaluation (no key so far);
  - Haiku and Opus comparisons;
  - an effort sweep;
  - consistency runs (k=3);
  - `eval compare`;
  - human-labelled expectations;
  - a larger dataset.
- **A month would buy:**
  - 50–100 real documents with human concept labels, a train/test split, and prompt tuning against it;
  - an LLM judge calibrated against those human labels;
  - effort and model sweeps priced from real usage;
  - optional local embeddings for duplicate detection, evaluated for precision;
  - a concept-level report of what the excerpt dropped;
  - streaming;
  - batching for the eval.

## 14. AI tools and personal contribution
**What the AI tool did (factual, from the session):**
- **Claude Code** (model: Claude Opus 5.5) generated essentially all of the code, tests, fixtures, evaluation scripts and documents, across ten supervised phases.
- It also ran the tests, the benchmarks, the single live smoke test and the security checks.

**What the author did (factual, from the session):**
- Wrote the phase instructions and approved every phase.
- Made the key decisions: Python stack; Sonnet as the Anthropic default; no PDF in the repo; no refusal fallback; switching the live evaluation to the Gemini free tier; approving the single smoke test; not running the full live suite.
- Rotated the leaked key.

**Personal contribution: to be completed by the author. Nothing below has been assumed.**
| Category | Author's answer |
|---|---|
| Code generated by AI tools | Essentially all of it (see above) |
| Code personally **inspected and understood** (files, or rough %) | **[Author: fill in]** |
| Code personally **modified or debugged** (files and what changed, or "none") | **[Author: fill in]** |
| Tests and reports personally **reviewed** (which ones) | **[Author: fill in]** |

## 15. Time note, commit history and process disclosure
| Time category | Value | Source |
|---|---|---|
| **Author's hands-on time** (reading, reviewing, testing, deciding; excluding waiting) | **[Author: fill in]** | author |
| **Claude's execution time** (the agent working autonomously within phases) | not separately measured | the agent cannot reliably separate its own working time from approval pauses |
| **Whole session, wall-clock** (agent work **plus** the author's approval pauses) | about 07:52 → 09:50 on 2026-11-11, then later short phases (Phases 8–10.1) | file and commit timestamps |

- **Commits:** 17 commits on 2026-11-11, 08:16–09:22 (`git log`), **agent-paced bursts, often minutes apart**. Each is a tested milestone. Phases 8–10.1 (the live smoke test, the offline audit, the final fixes) are **not yet committed**; they will become separate, phase-labelled commits after the author's review. **Attribution:** the first 17 commits originally carried a `Co-Authored-By` trailer naming the AI tool. **At the author's request, those trailers were removed from the commit messages by a history rewrite on 2026-11-11.** Code, authors and dates were unchanged; every commit hash changed (see HISTORY_REWRITE.md). Later commits use only the author's Git identity and neutral messages. Removing the trailers does not change who wrote the code: AI assistance is disclosed in this document (§14), and nothing about it is hidden.
- **Credential incident (disclosed):**
  - A Gemini API key was put into the *tracked* template `.env.example`, and a `git add -A` **committed it in local Git history**.
  - The affected commit was **never pushed**: the repository had no remote at any point.
  - It was caught in the same session by inspecting the commit's diff with values masked, and the commit was amended.
  - The author **revoked the key and replaced it**.
  - After checking that nothing else would be lost, the leaked commit and all unreachable objects were **purged** (`git reflog expire --expire=now --all && git gc --prune=now`).
  - **Later scans found no credential** in Git storage (every object) or in the files intended for submission.
  - `tests/test_repo_hygiene.py` now fails if `.env.example` ever holds a secret value, or if `.env` becomes tracked.
- **Rough because of time:**
  - live evidence is a single Gemini generate (n = 1); no live grow; no Anthropic run;
  - a small, AI-written eval set with lexical matching;
  - the heuristics and known bugs in §12.
