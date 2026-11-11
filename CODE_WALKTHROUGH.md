# Code Walkthrough

A short map of the code for reading it end to end, or for changing it live. Line numbers are as of commit `4b3c16a`+ (Phase 6); search for the function name if they have drifted.

## Files to open, in this order
| # | File | Why |
|---|---|---|
| 1 | [src/mindmap/config.py](src/mindmap/config.py) | Every tunable number, each marked spec / reasoned / guessed |
| 2 | [src/mindmap/contract.py](src/mindmap/contract.py) | The data contract: `Mindmap`, the field rules, `_graph_rules` (L165) |
| 3 | [src/mindmap/wire.py](src/mindmap/wire.py) | The LLM response shapes, built from the contract's field types. `provider_schema` (L108) |
| 4 | [src/mindmap/llm/budget.py](src/mindmap/llm/budget.py) | `CallBudget` and `BudgetedCaller`: **where requests are counted** |
| 5 | [src/mindmap/llm/structured.py](src/mindmap/llm/structured.py) | `run_with_repair` (L52): the only retry and repair logic |
| 6 | [src/mindmap/generate.py](src/mindmap/generate.py), [src/mindmap/assemble.py](src/mindmap/assemble.py) | Generate pipeline and its deterministic assembly |
| 7 | [src/mindmap/grow.py](src/mindmap/grow.py), [src/mindmap/dedup.py](src/mindmap/dedup.py), [src/mindmap/ranking.py](src/mindmap/ranking.py) | Grow pipeline: duplicates, admission, merge |
| 8 | [src/mindmap/textprep.py](src/mindmap/textprep.py), [src/mindmap/prompts.py](src/mindmap/prompts.py) | Input bounding and untrusted-text handling |
| 9 | [src/mindmap/llm/anthropic_provider.py](src/mindmap/llm/anthropic_provider.py), [src/mindmap/llm/gemini_provider.py](src/mindmap/llm/gemini_provider.py) | The only modules that import an SDK |
| 10 | [src/mindmap/cli.py](src/mindmap/cli.py) | Thin I/O layer: exit codes, report file, `.env` |

## Generate flow
1. `generate()` at [generate.py:33](src/mindmap/generate.py#L33).
2. `load_document`, at [textprep.py:42](src/mindmap/textprep.py#L42): size, UTF-8 and empty checks; strips control characters. Then `neutralise` at [prompts.py:70](src/mindmap/prompts.py#L70).
3. `select_passages`, at [textprep.py:113](src/mindmap/textprep.py#L113), called from [generate.py:44](src/mindmap/generate.py#L44). A document within 24,000 characters passes through unchanged; a longer one is cut down to that budget.
4. `BudgetedCaller(provider, CallBudget(2))` at [generate.py:45](src/mindmap/generate.py#L45).
5. `run_with_repair` sends request 1 with `GENERATE_SYSTEM` and the delimited document. Then:
   - **Refusal or truncation:** one more request.
   - **Otherwise** it calls `parse`, at [generate.py:48](src/mindmap/generate.py#L48): `parse_json_model` then `assemble_generate`.
6. `assemble_generate`, at [assemble.py:151](src/mindmap/assemble.py#L151):
   - normalises labels and summaries, logging each change;
   - drops duplicate labels;
   - checks the root;
   - trims the excess above 9 ([L183](src/mindmap/assemble.py#L183));
   - fewer than 5 nodes → `OutputRejected` → a repair request ([L193](src/mindmap/assemble.py#L193));
   - assigns slug ids and drops bad edges;
   - attaches orphans to the root ([L229](src/mindmap/assemble.py#L229));
   - calls `check_generate_size` ([L235](src/mindmap/assemble.py#L235)).
7. Returns `GenerateResult(mindmap, repairs, trimmed, excerpt, usage, usage_summary)`.

## Grow flow
1. `grow()` at [grow.py:54](src/mindmap/grow.py#L54). It re-validates the existing map (L63), then loads, neutralises and bounds the document (L66–70), with novelty measured against the map's labels and summaries.
2. `BudgetedCaller(provider, CallBudget(GROW_MAX_CALLS))` at [grow.py:71](src/mindmap/grow.py#L71), then `run_with_repair` (L73) with `grow_user_message`: capacity, a candidate limit, `<existing_map>` rows and the `<document>`.
3. `prepare_candidates`, at [dedup.py:53](src/mindmap/dedup.py#L53):
   - over the 15-candidate limit (L59) → omitted, `over_candidate_limit`;
   - duplicate ref or empty text → omitted, `invalid`.
4. `split_duplicates`, at [dedup.py:83](src/mindmap/dedup.py#L83):
   - the model's valid `duplicate_of` (L94);
   - otherwise an exact `label_key` match against existing labels (L103) or an earlier candidate (L107).
5. `admit`, at [ranking.py:74](src/mindmap/ranking.py#L74):
   - `resolve_parents` ([L32](src/mindmap/ranking.py#L32)): duplicates redirect; unknown targets and cycles go to the root.
   - Greedy loop ([L101](src/mindmap/ranking.py#L101)) with sort key `(-importance, chain length, existing-first, order)` ([L108](src/mindmap/ranking.py#L108)).
   - The rest are omitted, `ceiling` ([L122](src/mindmap/ranking.py#L122)).
6. `_merge` ([grow.py:121](src/mindmap/grow.py#L121)) appends nodes and edges only.
7. `_check_preserved` ([grow.py:142](src/mindmap/grow.py#L142)) and the accounting check ([grow.py:103–105](src/mindmap/grow.py#L103-L105)). A violation raises `InvariantViolation`.

## Where requests are counted
- [budget.py:47](src/mindmap/llm/budget.py#L47): `self.budget.acquire()` is called **before** `provider.complete()`. `acquire` ([L32](src/mindmap/llm/budget.py#L32)) raises `CallBudgetExceeded` once the budget is used.
- The loop in [structured.py:68](src/mindmap/llm/structured.py#L68) stops when the budget is exhausted. Every path (provider error, refusal, truncation, invalid output) goes back through `caller.call`.
- SDK retries are off:
  - [anthropic_provider.py:57](src/mindmap/llm/anthropic_provider.py#L57): `max_retries=0`;
  - [gemini_provider.py:102](src/mindmap/llm/gemini_provider.py#L102): `HttpRetryOptions(attempts=1)`.
- The limits themselves: `GROW_MAX_CALLS` and `GENERATE_MAX_CALLS` in [config.py:22–23](src/mindmap/config.py#L22-L23).

## Where validation happens
| Layer | Where |
|---|---|
| Untrusted document | `load_document` [textprep.py:42](src/mindmap/textprep.py#L42) |
| Untrusted map file | `load_mindmap` [contract.py:214](src/mindmap/contract.py#L214) → `InputError` |
| Provider response shape | provider-side schema (`output_config.format` / `response_json_schema`), then `parse_json_model` [structured.py:37](src/mindmap/llm/structured.py#L37) |
| Field normalisation (every change logged) | `normalize_*` [assemble.py:47–98](src/mindmap/assemble.py#L47) |
| Contract (ids, root, edges, word and sentence rules, ≤ 25) | `Mindmap._graph_rules` [contract.py:165](src/mindmap/contract.py#L165), plus the field validators |
| Generate size 5–9 | `check_generate_size` [contract.py:191](src/mindmap/contract.py#L191) |
| Grow post-conditions | `_check_preserved` [grow.py:142](src/mindmap/grow.py#L142) and the accounting check [grow.py:103](src/mindmap/grow.py#L103) |

## Where overflow is decided and reported
- **Capacity:** `MAX_NODES - len(existing.nodes)` at [grow.py:67](src/mindmap/grow.py#L67).
- **What doesn't fit:** `admit` at [ranking.py:74](src/mindmap/ranking.py#L74). Remaining candidates become `Omitted(reason="ceiling")`.
- **Other reasons:** `over_candidate_limit` and `invalid`, in `prepare_candidates`.
- **Reported in:** `GrowResult.omitted`, which the CLI writes to `<out>.report.json` and prints to stderr ([cli.py `grow_cmd`](src/mindmap/cli.py)).

## Cost and token usage
- **Tokens:** read from the provider response.
  - Anthropic: `response.usage`, in `complete()` ([anthropic_provider.py:77](src/mindmap/llm/anthropic_provider.py#L77)).
  - Gemini: `usage_metadata` ([gemini_provider.py:122](src/mindmap/llm/gemini_provider.py#L122)). Input is the prompt count minus cached tokens; output is candidate tokens plus thinking tokens.
- **Cost:** `estimate_cost_usd` ([pricing.py:56](src/mindmap/pricing.py#L56)) = tokens × the dated list price. It is called once per request in `BudgetedCaller._record` ([budget.py:85](src/mindmap/llm/budget.py#L85)) and summed by `summarize_usage` ([observability.py:48](src/mindmap/observability.py#L48)).
- **Eval spending ceiling:** `case_worst_case_usd` ([runner.py:161](src/mindmap/evals/runner.py#L161)) and the check at [runner.py:197](src/mindmap/evals/runner.py#L197).

## How to add another provider (about 30–60 min, plus tests)
1. Create `src/mindmap/llm/<name>_provider.py` with a class that has `name = "<name>"` and `complete(self, request: LLMRequest) -> LLMResponse`. It must:
   - send **exactly one** request, with the SDK's own retries turned off;
   - send `request.schema` as the structured-output schema, rewriting it only where the provider's docs require (as `gemini_schema` does);
   - read text blocks by type; map finish reasons to `"end_turn"`, `"max_tokens"` or `"refusal"`;
   - map SDK errors to the `ProviderError` subclasses in [errors.py](src/mindmap/errors.py), with `retryable` set correctly and `retry_after_s` when the server gives one;
   - fill `Usage` from **provider-reported** counts only.
2. Add the provider and its default model to `PROVIDER_DEFAULT_MODELS` ([config.py:53](src/mindmap/config.py#L53)) and a branch in `make_provider` ([cli.py:53](src/mindmap/cli.py#L53)). Add its list price to `PRICES` ([pricing.py](src/mindmap/pricing.py)) if the spending ceiling should work.
3. Add the SDK to `pyproject.toml`. Extend `test_each_sdk_is_imported_in_exactly_one_module` and `test_no_embedding_token_count_or_extra_calls` in [tests/test_provider.py](tests/test_provider.py).
4. Copy [tests/test_gemini_provider.py](tests/test_gemini_provider.py) as a template: stub client, request shape, finish reasons, error mapping, and "grow never exceeds two requests".

## Running things
```bash
make setup && make test                         # offline; 191 tests
.venv/bin/mindmap eval --mode pipeline          # deterministic bench, ~1 s
.venv/bin/mindmap -v grow --map evals/maps/photosynthesis_seed.json \
    --in evals/docs/photosynthesis_part2.txt --out /tmp/m2.json   # needs a key; prints one log line per request
```
