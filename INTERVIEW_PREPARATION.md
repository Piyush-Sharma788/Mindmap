# Interview Preparation

Grounded in the code as committed. File references point to [CODE_WALKTHROUGH.md](CODE_WALKTHROUGH.md).

> **Honesty notes to keep in mind when answering:**
> - **No live model call has been made.** Every quality and cost figure for a real model is either *pending* or an *estimate*. The measured numbers are offline pipeline measurements on scripted model output.
> - The code was written by Claude Code in supervised phases. **[Author: your own review % and hands-on time go here, in APPROACH §14–15.]**

## The 60-second architecture pitch
"It's a fixed pipeline with no agent loop, and the model is called in exactly one place.
- Deterministic code bounds the document to 24,000 characters. Selection is extractive, IDF-weighted, ignores numbers and URLs, and favours novelty in grow.
- One structured-output request goes out, through a `BudgetedCaller` that takes a budget slot *before* sending. Grow's budget is 2, which leaves room for exactly one retry or repair.
- Everything after that is code: parsing against Pydantic shapes built from the single contract; graph repair; for grow, duplicate detection (the model's judgement plus an exact-match backstop), greedy admission under the 25-node ceiling, and an append-only merge checked byte-for-byte.
- Every candidate the model proposes ends up added, duplicate or omitted, with a reason in the report.
- There are two providers, Anthropic and Gemini, each the only module importing its SDK, with SDK retries turned off."

## 20 likely questions

**1. Why no agent loop?**
- Every step has a code-checkable definition of "done", the spec caps grow at 2 calls, and users pay per interaction.
- An agent would make cost and latency open-ended and harder to test.
- The only loop is one repair request, and it's triggered by a validation failure, not by the model's judgement. That's in `run_with_repair`.
- Where a loop *could* earn its place: a self-critique pass on generate, if the eval showed the quality is worth about 2× the cost. That hasn't been measured.

**2. How do you guarantee grow never makes a 3rd request?**
Five layers:
1. SDK retries are off: `max_retries=0` and `HttpRetryOptions(attempts=1)`. I read the Gemini SDK source: its implicit retry exists only in the async aiohttp path, and we use the sync path.
2. `CallBudget(2).acquire()` runs *before* `complete()`, and a third call raises `CallBudgetExceeded`.
3. Every outcome uses a slot: timeouts, 429s, refusals, truncations, invalid JSON.
4. No embeddings, token-count calls or fallback.
5. Tests:
   - documents of 1 KB, 100 KB and 1 MB;
   - permanent-failure fakes → exactly 2 requests;
   - the Gemini provider with real SDK error types;
   - 400 fuzzed grow runs, all ≤ 2 requests.
- Proof that it's centralised: set `GROW_MAX_CALLS = 1` and exactly 13 tests fail, all of them asserting two-request behaviour.

**3. Why does grow's cost not grow with document length?**
- The only document-dependent part of the prompt is the excerpt, capped at 24,000 characters.
- The map part is bounded by the 25-node ceiling and per-field caps. Output is bounded by `max_tokens` and the 15-candidate limit.
- CPU cost of selection is O(n log n), and input is capped at 5 MB. I read "cost" as LLM spend and say so in APPROACH.
- `test_prompt_size_identical_for_100kb_and_1mb` asserts the two prompts differ by at most 5% of the excerpt budget.

**4. What does "single source of truth" mean in your code?**
- `contract.py` defines the field types and descriptions.
- `wire.py` builds the model's response shapes *from those types*: they're different shapes (temporary refs, importance, `duplicate_of`) but share the definitions.
- `provider_schema()` generates the provider schema and strips keywords the provider doesn't support, which code then enforces.
- `schema/mindmap.schema.json` is generated.
- Drift tests compare descriptions and the committed schema file.

**5. Why not let the model produce the final `Mindmap` directly?**
- Model-chosen ids collide and drift across grow.
- Grow needs per-candidate judgements (`duplicate_of`, `importance`, `attach_to`) that aren't part of the public contract.
- So the model proposes, and code assigns ids, repairs the graph and validates.

**6. How does duplicate detection work, and what does it miss?**
- The model judges semantic coverage (`duplicate_of`).
- A code backstop does an exact match on `label_key`: lowercase, accents, punctuation, a leading article, regular plurals.
- It's deliberately high-precision. A fuzzy threshold would merge "Machine Learning" with "Machine Learning Ethics".
- Misses: "Buses" (the "-ses" ending is ambiguous with "Leases", so I kept precision), irregular plurals, and paraphrases. Paraphrase leakage is a live metric, still pending.
- Bench: 0 false merges on 7 near-miss pairs, and 100% of lexical variants caught in the grow fuzz.

**7. How do you choose what to keep when the ceiling binds?**
- Value is the model's importance score, 1–5.
- `admit` repeatedly takes the most important candidate whose parent chain fits the remaining room, admitting parents first.
- It replaced a rank-then-passes version that starved high-importance children. Its worst case was 62.5% of the optimum.
- Measured against an independent exact tree-knapsack optimum: 100% on 400 seeds. It is greedy, though, so not guaranteed optimal.

**8. How is overflow reported?**
- Every candidate ends up in `added`, `duplicates` or `omitted`, with a reason: `ceiling`, `invalid` or `over_candidate_limit`.
- A post-condition raises `InvariantViolation` if the counts don't add up.
- The CLI writes the report to `<out>.report.json` and lists omissions on stderr.
- A full map still makes one call, so that what was left out can be reported.

**9. How do you keep existing nodes intact?**
- The merge is append-only.
- `_check_preserved` compares the existing nodes, edges, title and root byte-for-byte after the merge.
- Bench: 100% preserved over 400 fuzzed runs.

**10. What about prompt injection?**
- Untrusted text, *including the existing map*, goes inside `<document>` / `<existing_map>`. Tag-like text in it is escaped *before* selection, so the input bound holds.
- Phase 4 fixed a bypass where a space before the slash (`< /document`) escaped the escaping.
- The system prompt says embedded instructions are data. No tools are enabled, and output is schema-constrained.
- Damage is capped: at worst a misleading node, still limited to 4 words, 1 sentence and fixed lengths.
- Bench: 100% delimiter integrity.
- Whether the model actually ignores the instruction is the `injection_followed` live metric, still pending.

**11. Why Sonnet 5.5 by default, and why are you testing Gemini?**
- Sonnet balances quality and price. Haiku 5.5 is about 20× cheaper; Opus 5.5 is the quality ceiling. The choice should come from the eval, which is pending.
- Gemini `gemini-3.6-flash` is there only because no Anthropic key was available and it is free on the free tier.
- **Gemini results don't measure Claude.**

**12. What parameters did you set and what do they do?**
- `max_tokens` = 16,000 caps the worst-case output cost and leaves room for thinking.
- `effort=medium` (Anthropic) trades thinking depth for cost. It's guessed and untested.
- Structured-output schema.
- **No `temperature`:** current Claude models reject sampling parameters. So consistency must be *measured*; it can't be pinned.
- Gemini: default thinking, `candidate_count=1`.

**13. What does one generate / grow cost?**
- **Measured:** prompt sizes. Generate is about 2.1–2.5K characters plus a 1.5K-character schema; a typical grow is 3.2–5.2K plus 1.4K.
- **Estimated (unmeasured):** Sonnet generate about $0.007–0.027 and grow about $0.012–0.033. Gemini paid-equivalent is about $0.003–0.012; on the free tier it's $0.
- Hard worst case for one Sonnet operation: $0.48 (2 × (40K input + 16K output)).

**14. How would you halve cost?**
- With these estimates, output is about 55–90% of Sonnet's cost, and much of it is thinking. Lower `effort` or turning thinking off (`between_tools`) is a one-line config change.
- Haiku 5.5 is the bigger lever, but its quality is unmeasured.
- Caching the system prompt saves much less than half, since it's only about 1K tokens.

**15. Latency?**
- One request on the happy path, two at worst, with a 180 s timeout each and no streaming.
- Worst-case wait is about 6 min plus up to 10 s of retry delay.
- Live latency is pending; the eval records it per request.

**16. How do you know the output is good?**
- Two kinds of measurement, kept separate:
  1. **Pipeline bench** (offline): it shows the code handles model output correctly.
  2. **Live / replay eval:** recall and new-concept recall, duplicate leakage, validity, first-pass rate, repairs, injection, tokens, cost and latency. Recordings replay offline, so code-only changes re-score for free.
- Weaknesses: n = 10, AI-written fixtures, lexical matching, no human labels.

**17. How would you know a change made it better?**
- **A code-only change** (dedup, ranking, selection): re-run replay and the pipeline bench, then compare. That's what Phase 4 did: before/after JSON files on the same seeds.
- **A prompt or model change:** the cassette key changes, so replay reports misses. It needs a live re-record within a spending ceiling.

**18. What happens when the provider fails?**
- Errors are typed and mapped per SDK.
- A retryable error is retried once, within the budget, only if the server's requested delay is ≤ 10 s.
- Otherwise the CLI exits non-zero (4) with a hint and the request count, and writes **nothing**. No canned output, ever.

**19. What did you throw away?**
- The rank-then-passes admission.
- A plural rule that broke "Leases".
- A long-document eval case that deduplicated down to 3.5K characters.
- A wrong 10% cache-read price.
- Rejected outright: two working calls in grow, embeddings, fuzzy matching, an LLM judge, an agent loop.

**20. Biggest known weaknesses?**
- No live evaluation yet.
- Duplicates share the 15-candidate limit.
- Greedy admission.
- Lexical duplicate detection and sentence heuristics.
- Excerpt loss is reported only as a ratio.
- A refusal retry probably wastes the second call.

The full list is in APPROACH §12.

## Trade-offs worth volunteering
| Decision | Alternative | Why this one | Cost of the choice |
|---|---|---|---|
| 1 call + 1 repair in grow | 2 working calls (extract, then dedup) | One context sees map and document together; a request stays free for recovery; about half the tokens | One call carries several jobs |
| Extractive selection in code | LLM map-reduce summary | Constant cost; deterministic; testable | Lexical; can miss paraphrased importance |
| Exact-match backstop | Fuzzy or embedding similarity | Zero false merges; no extra calls | Paraphrase leakage depends on the model |
| Model importance + greedy chain admission | Code-only centrality | Only the model knows what matters semantically | Scores uncalibrated; greedy not optimal |
| Reject maps over 25 nodes | Accept and flag | One invariant everywhere | Can't grow an over-ceiling map from another tool |
| Retry only when server delay ≤ 10 s | Always retry once | Doesn't burn the 2nd request on a long quota | One fewer attempt in that case |

## Five code-change exercises (each under 20 min)
Exercises 1–3 were trial-run on a scratch clone; their test outcomes below are observed, not predicted. Exercises 4–5 were not trial-run.

**Ex 1: Duplicates should not use up the 15-candidate limit** (fixes known limitation #2)
- Where: `prepare_candidates`, [dedup.py:53–62](src/mindmap/dedup.py#L53).
- Change: count only candidates whose `duplicate_of is None` toward `MAX_CANDIDATES`.
- Also update the grow prompt line "Return at most {max_candidates} candidates in total" in `grow_user_message` ([prompts.py:88](src/mindmap/prompts.py#L88)), because output size is now bounded by `max_tokens` rather than by the candidate count.
- Observed: **all 185 tests still pass**, which means no test covers this. Add one: 15 model-marked duplicates plus 3 new candidates → all 3 new ones considered, and accounting still equals 18.

**Ex 2: Fail fast on refusal** (stop wasting the second request)
- Where: [structured.py:95–98](src/mindmap/llm/structured.py#L95). Replace `continue` with `raise ModelOutputError(f"{purpose}: model refused", failures)`.
- Observed: **3 tests fail**, all asserting "refusal uses 2 requests":
  - `test_generate.py::test_refusal_and_truncation_consume_budget`;
  - `test_grow.py::test_unusable_output_stops_at_exactly_two_requests[script1]`;
  - `test_gemini_provider.py::...never_exceeds_two_requests[outcome5...]`.
- Update them to expect 1 request. Discuss the trade-off: a refusal can be transient, but it usually isn't.

**Ex 3: Show the call limit is centralised**
- Set `GROW_MAX_CALLS = 1` in [config.py:22](src/mindmap/config.py#L22) and run `make test`.
- Observed: **13 failed, 172 passed.** Every failure is a test asserting two-request retry or repair behaviour. Nothing else in the code needs to change.
- Revert it afterwards: the spec allows 2, and the second request is the recovery path.

**Ex 4: Minimum importance cut-off** (not trial-run)
- Add `MIN_IMPORTANCE = 2` to config.
- In `grow()`, after `split_duplicates` ([grow.py:93](src/mindmap/grow.py#L93)), move fresh candidates with `importance < MIN_IMPORTANCE` into `omitted` with a new reason, `"low_importance"`. The reason must also be added to `OmitReason` in [dedup.py](src/mindmap/dedup.py).
- The accounting invariant at [grow.py:103](src/mindmap/grow.py#L103) will catch a mistake.
- Test: two candidates with importances 1 and 4 and room for both → only the 4 is added, and the 1 is reported as `low_importance`.

**Ex 5: A new eval metric** (not trial-run)
- In `aggregate`, [runner.py:130](src/mindmap/evals/runner.py#L130), add `grow_mean_added` and `generate_mean_nodes` (using `M.mean` over the `added` / `nodes` fields already in each row).
- Assert them in `test_record_then_replay_gives_identical_metrics` ([tests/test_eval.py](tests/test_eval.py)): 1 added, 6 nodes, given that test's scripted replies.

## Improvement roadmap (with another month)
1. 50–100 real documents with human concept labels and a train/test split; prompt tuning against it.
2. An LLM judge calibrated against those labels.
3. Model × effort sweeps priced from real usage.
4. Optional local embeddings for duplicate detection, evaluated for precision.
5. A concept-level report of what the excerpt dropped.
6. Streaming, plus batch requests for the eval.
