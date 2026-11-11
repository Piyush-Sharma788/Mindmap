# Final Requirements Audit

**Audit date:** 2026-11-11 (Phase 7).

**Sources checked:** the assignment PDF (as summarised in PROJECT_CONTEXT.md), the source code, and the offline test suite (187 tests, `make test`).

**Status key:**
- **VERIFIED:** an automated offline test, or a recorded command run on a fresh clone, proves it.
- **VERIFIED (scripted):** proven with scripted model output. Real-model behaviour is not yet observed.
- **IMPLEMENTED:** the code or document exists, but nothing automated checks it.
- **BLOCKED:** needs a live run, the author or publishing.

> No live model request has been made, so every row is backed by offline evidence only. Real-model quality, real token counts and real cost are **BLOCKED** until an approved live run.

## Functional requirements
| # | Requirement (PDF) | Evidence in code | Test(s) | Status |
|---|---|---|---|---|
| F1 | `generate`: text → Mindmap | `generate()` [generate.py:33](src/mindmap/generate.py#L33) | `test_generate.py::test_happy_path_one_request`; `test_cli.py::test_generate_writes_contract_map_and_separate_report` | VERIFIED (scripted) |
| F2 | 5–9 nodes on first generation | trim if above 9 [assemble.py:183](src/mindmap/assemble.py#L183); below 5 → repair, then error [assemble.py:193](src/mindmap/assemble.py#L193); `check_generate_size` [contract.py:191](src/mindmap/contract.py#L191) | `test_more_than_nine_nodes_are_trimmed_and_reported`, `test_too_few_nodes_triggers_one_repair_then_succeeds`, `test_too_few_nodes_twice_fails_without_fabricating`, `test_generate_size_rule`; bench generate fuzz (300 runs, 0 invalid maps) | VERIFIED |
| F3 | `grow`: existing map + new document | `grow()` [grow.py:54](src/mindmap/grow.py#L54) | `test_grow.py::test_existing_nodes_and_edges_survive_unchanged`; `test_cli.py::test_grow_then_render` | VERIFIED (scripted) |
| F4 | Existing nodes survive; map not regenerated | append-only `_merge` [grow.py:121](src/mindmap/grow.py#L121); `_check_preserved` [grow.py:142](src/mindmap/grow.py#L142) (nodes, edges, title, root byte-identical) | `test_existing_nodes_and_edges_survive_unchanged`, `test_identical_document_adds_nothing`, `test_full_map_adds_nothing_but_reports_everything`; bench `preserved_rate` = 1.0 (400 runs) | VERIFIED |
| F5 | Material already covered is dropped | the model's `duplicate_of`, plus the exact `label_key` backstop, `split_duplicates` [dedup.py:83](src/mindmap/dedup.py#L83) | `test_model_and_lexical_duplicates_are_dropped_and_reported`, `test_backstop_catches_article_case_and_plural_variants`, `test_unknown_duplicate_of_is_ignored_not_trusted`, `test_label_key_precision`; bench: 0 false merges, 100% variant catch | Code VERIFIED; **semantic coverage by the real model BLOCKED** (live `duplicate_leakage`) |
| F6 | Ceiling of 25 nodes | `MAX_NODES` [config.py:19](src/mindmap/config.py#L19); contract [contract.py:165](src/mindmap/contract.py#L165); capacity [grow.py:67](src/mindmap/grow.py#L67) | `test_ceiling_is_enforced_by_contract`, `test_ceiling_keeps_most_important_and_reports_the_rest`, `test_full_map_adds_nothing_but_reports_everything`; bench `within_ceiling_rate` = 1.0 | VERIFIED |
| F7 | When the ceiling binds, keep the most valuable material | `admit`, greedy by parent chain [ranking.py:74](src/mindmap/ranking.py#L74) | `test_ceiling_keeps_most_important_and_reports_the_rest`, `test_important_child_is_not_starved_by_mid_importance_siblings`, `test_child_whose_parent_chain_does_not_fit_is_omitted_with_reason`; bench value vs exact optimum: worst case 1.0 over 400 seeds | VERIFIED (given the model's importance scores; their quality is BLOCKED) |
| F8 | Report what was left out; never discard silently | `Omitted` reasons (`ceiling`, `invalid`, `over_candidate_limit`); accounting check [grow.py:103–105](src/mindmap/grow.py#L103); report file and stderr ([cli.py](src/mindmap/cli.py) `grow_cmd`); excerpt `sent_ratio` | `test_over_candidate_limit_and_invalid_are_accounted`, `test_grow_then_render` (asserts `omitted [ceiling]` on stderr), `test_report_is_json_serialisable_and_discloses_excerpt_ratio`; bench `accounted_rate` = 1.0 | VERIFIED |
| F9 | **At most 2 LLM calls per grow, any document length** | `GROW_MAX_CALLS` [config.py:22](src/mindmap/config.py#L22); `acquire()` before each send [budget.py:47](src/mindmap/llm/budget.py#L47); loop [structured.py:68](src/mindmap/llm/structured.py#L68); SDK retries off ([anthropic_provider.py:57](src/mindmap/llm/anthropic_provider.py#L57), [gemini_provider.py:102](src/mindmap/llm/gemini_provider.py#L102)) | `test_budget_refuses_third_request_before_sending`, `test_call_count_and_prompt_size_bounded_for_any_document_length` (1 KB / 100 KB / 1 MB), `test_unusable_output_stops_at_exactly_two_requests`, `test_persistent_provider_errors_stop_at_exactly_two_requests`, `test_grow_with_gemini_never_exceeds_two_requests`, `test_sdk_retries_disabled_and_timeout_set`, `test_sdk_retries_disabled_and_timeout_in_ms`, `test_each_sdk_is_imported_in_exactly_one_module`, `test_no_embedding_token_count_or_extra_calls`; bench `requests_le_2_rate` = 1.0 | VERIFIED (offline). Not yet observed against a live API |
| F10 | Grow cost doesn't grow with document length | `select_passages` [textprep.py:113](src/mindmap/textprep.py#L113) to a 24,000-character budget; tags neutralised before selection [grow.py:66](src/mindmap/grow.py#L66) | `test_prompt_size_identical_for_100kb_and_1mb`, `test_excerpt_is_bounded_for_any_length`, `test_input_bound_holds_for_documents_full_of_delimiter_tags` | VERIFIED |

## Data contract
| # | Requirement | Evidence | Test(s) | Status |
|---|---|---|---|---|
| C1 | `MindmapNode`, `MindmapConnection` and `Mindmap` exactly as specified (`from` alias) | [contract.py:143–187](src/mindmap/contract.py#L143) | `test_valid_map_round_trips_with_from_alias`; `test_generate_writes_contract_map_and_separate_report` (output has exactly 4 keys) | VERIFIED |
| C2 | Unique ids, real `rootId`, no dangling edges, no self-loops | `_graph_rules` [contract.py:165](src/mindmap/contract.py#L165) | `test_contract_rejects` (parametrised) | VERIFIED |
| C3 | Stable ids | assigned by code (`unique_id`, [assemble.py:134](src/mindmap/assemble.py#L134)); never changed by grow | `test_new_ids_never_collide_with_existing`; preservation tests | VERIFIED |
| C4 | Labels 1–4 words; one-sentence summary | contract validators; `normalize_*` with logged repairs | `test_contract_rejects`, `test_sentence_heuristic`, `test_hyphenated_term_counts_as_one_word`, `test_hostile_model_output_is_contained_by_validation` | VERIFIED (the sentence rule is a heuristic, see Limitations) |
| C5 | Contract defined once; everything (including the provider schema) derived | [wire.py:108](src/mindmap/wire.py#L108) `provider_schema`; `gemini_schema` (nullable rewrite only); generated `schema/mindmap.schema.json` | `test_provider_schema_is_derived_and_supported`, `test_wire_fields_share_contract_descriptions`, `test_committed_schema_file_matches_contract`, `test_request_shape_uses_derived_schema_and_no_sampling_params`, `test_gemini_schema_only_rewrites_nullable_anyof` | VERIFIED |

## CLI, rendering, evaluation
| # | Requirement | Evidence | Test(s) / run | Status |
|---|---|---|---|---|
| L1 | `mindmap generate --in --out` | [cli.py](src/mindmap/cli.py) `generate_cmd` | `test_generate_writes_contract_map_and_separate_report`, `test_model_failure_exits_nonzero_and_writes_nothing`; fresh-clone run without a key → exit 2, no file | VERIFIED (scripted) |
| L2 | `mindmap grow --map --in --out` | `grow_cmd` | `test_grow_then_render`, `test_bad_inputs_exit_3_before_any_request`; fresh-clone Gemini run without a key → exit 2 | VERIFIED (scripted) |
| L3 | `mindmap render --map --out` (Mermaid) | [render.py:36](src/mindmap/render.py#L36) | `test_basic_render`, `test_hostile_text_cannot_break_out_of_quotes`; bench render fuzz 1.0; fresh-clone run (17 lines) | VERIFIED (syntax not checked in a Mermaid renderer) |
| L4 | `mindmap eval --suite evals/` | [runner.py](src/mindmap/evals/runner.py), [pipeline.py](src/mindmap/evals/pipeline.py) | `test_eval_replay_on_shipped_suite_runs_offline`, `test_eval_pipeline_mode_runs_offline`, `test_record_then_replay_gives_identical_metrics`, `test_spending_ceiling_skips_cases_whose_worst_case_would_exceed_it` | VERIFIED. **Live metrics BLOCKED** |

## Process and evaluation criteria
| # | Requirement | Evidence | Status |
|---|---|---|---|
| P1 | Tests pass on a fresh clone with no API key | conftest removes keys, disables `.env`, blocks sockets (`test_network_is_blocked_in_tests`); fresh clone with an empty HOME: 187 passed | VERIFIED |
| P2 | No credentials committed at any point | `.gitignore` (`.env`, `*.pdf`); `.env` exists locally but is ignored and untracked. **Incident (Phase 7):** a filled-in `.env.example` (an edit from outside my changes) was swept into a local, never-pushed commit by `git add -A`. It was removed by amending that commit before any remote existed; no reachable commit contains a key (checked across every reachable commit). Guard added: `tests/test_repo_hygiene.py`. The old commit remains only as an unreachable local object until the reflog is expired | VERIFIED for the publishable history; local purge pending approval |
| P3 | No catch-all returning canned output | typed errors; the CLI writes nothing on failure; no `except Exception` in services | VERIFIED (`test_model_failure_exits_nonzero_and_writes_nothing`, `test_too_few_nodes_twice_fails_without_fabricating`) |
| P4 | No function named as if it calls a model but doing keyword matching | `select_passages`, `match_concepts_lexically`, `label_key`: names describe what they do | IMPLEMENTED (code review) |
| P5 | Commits at milestones; bursts disclosed | `git log`; APPROACH §15 | VERIFIED |
| P6 | Numbers in the write-up producible by the code | pipeline numbers: `eval --mode pipeline` reproduces `evals/results/pipeline-bench-after-phase4.json` byte for byte; costs labelled estimates; no live numbers claimed | VERIFIED |
| P7 | Untrusted input handled | size/encoding limits; neutralisation before selection; delimiters; schema output; render escaping | VERIFIED structurally (bench 100% delimiter integrity). **Live injection resistance BLOCKED** |
| P8 | Evaluation with a real number | pipeline-bench numbers are real; **model-quality numbers BLOCKED** | PARTIAL |
| P9 | README: one setup command, one test command, providers and models | fresh-clone run of `make setup` + `make test` | VERIFIED |
| P10 | APPROACH.md, all required sections | APPROACH §1–15 | IMPLEMENTED; author placeholders §14–15 **BLOCKED (author)** |
| P11 | Time note | APPROACH §15 | IMPLEMENTED; the author's own time **BLOCKED (author)** |
| P12 | Public repository URL | not created | **BLOCKED (approval)** |

## Limitations to keep visible
- All model behaviour is unobserved: quality, real duplicate judgement, importance quality, injection resistance, tokens, cost and latency.
- The rest of the known-bugs list is in APPROACH §12.
