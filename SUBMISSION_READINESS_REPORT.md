# Submission Readiness Report (Phase 10.2)

**Date:** 2026-11-11. **Local HEAD:** `2417b0e` (17 commits, unchanged).

**Target repository:** https://github.com/Piyush-Sharma788/Mindmap.

**This phase made:** 0 LLM API calls; 0 spending; no read of `.env`; nothing staged, committed or pushed; no history change. The only network access was a read-only, unauthenticated check of the GitHub repository.

**Status words:**
- **PASS:** met, with evidence.
- **PARTIAL:** met only in part; the gap is stated.
- **FAIL:** not met.
- **NOT VERIFIED:** no evidence either way.

---

## 1. Assignment compliance
| Requirement | Status | Evidence |
|---|---|---|
| Generate: text → map with **5–9 nodes** | PASS | trim / repair / fail logic in `assemble.py`; tests `test_more_than_nine_nodes_are_trimmed_and_reported`, `test_too_few_nodes_*`; 300-run fuzz (0 invalid maps); 4 real fixtures; **live: 6 valid nodes (n = 1, Gemini)** |
| Stable ids and data contract | PASS | code-assigned slug ids that never collide (`test_new_ids_never_collide_with_existing`); `Mindmap._graph_rules` (unique ids, real root, no dangling edges or self-loops); `test_contract_rejects` |
| Contract defined once; provider schema derived | PASS | `wire.provider_schema`; drift tests; the committed schema file matches; the live Gemini API accepted the derived schema |
| Grow: existing nodes and connections preserved | PASS (offline) | append-only `_merge` plus `_check_preserved`; 400-run fuzz = 1.0; 5 real fixtures. **Not validated on a real model** |
| Grow: already-covered content dropped | PARTIAL | the code path is PASS (model `duplicate_of` plus the exact backstop; 0 false merges; 5/5 planted duplicates caught on fixtures). **The real model's semantic duplicate judgement is NOT VERIFIED** (no live grow) |
| ≤ 25 nodes; every omission reported with a reason | PASS (offline) | contract ceiling; `grow-ceiling` fixture stops at exactly 25; accounting invariant; omissions in the report file and on stderr |
| Most valuable kept under the ceiling | PASS (offline, given model importance) | greedy-by-chain admission; worst case vs the exact optimum = 1.0 over 400 seeds. Importance quality from a real model: NOT VERIFIED |
| **Grow ≤ 2 LLM requests** | PASS (offline) | `CallBudget` acquired before sending; SDK retries off; 1 KB / 100 KB / 1 MB tests; failure paths exactly 2; 400-run fuzz; Gemini provider tests. **Not observed on a real model** |
| Input budgeting and cost architecture | PASS | fixed 24,000-character excerpt (63K fixture → 22,968 sent); prompt sizes reproducible (`python -m mindmap.evals.prompt_sizes`); cost per request from provider-reported tokens × dated list prices |
| Provider errors and validation | PASS | typed error mapping (Anthropic and Gemini tests with real SDK error types); no catch-all; nothing written on failure |
| Prompt-injection handling | PARTIAL | structural defences PASS (neutralised before selection; delimiter integrity 1.0; schema-only output; length caps). **Model resistance NOT VERIFIED live** |
| Mermaid output safety | PASS | aliases plus entity escaping; hostile-label test; 300-map fuzz, every line on the allow-list |
| CLI: generate / grow / render / eval | PASS | CLI tests; fresh-copy runs (render, pipeline, replay) offline; generate via the live smoke test |
| Offline tests and clean-clone setup | PASS | fresh copy, no keys, no `.env`: 191 passed, 0 skipped; milestone simulation 187 → 187 → 190 → 191 |
| Evaluation methodology and reproducibility | PASS / PARTIAL | the bench reproduces its committed file byte for byte; replay equals live on 11 metrics. **Model-quality evidence is n = 1, generate only** |
| `APPROACH.md` completeness | PARTIAL | every section present; **author fields in §14 / §15 are empty placeholders** |
| AI assistance and time disclosure | PARTIAL | AI role, session times, commit bursts, attribution change and the credential incident are disclosed; **the author's own review and time are still to be supplied** |

## 2. The eight failure conditions
| # | Condition | Status | Evidence |
|---|---|---|---|
| 1 | A model-sounding name over keyword or hardcoded code | PASS | model calls only in the `complete()` methods of the two providers; `summarize` renamed `summarize_usage` (pure arithmetic); deterministic helpers named for what they do |
| 2 | Swallowed provider errors / canned success | PASS | the only broad handler re-raises (`cli._write_atomic`); typed errors; tests prove no output is written on failure |
| 3 | Grow cost scales with document length | PASS (offline) | fixed excerpt, `CallBudget(2)`, length tests. Live grow not run |
| 4 | Numbers the code can't produce | PASS | bench, replay and prompt-size reproducers; estimates labelled; one "measured" token claim corrected to "estimated" |
| 5 | Tests need a key or pass only locally | PASS | fresh copy, no keys or `.env`, sockets blocked: 191 passed |
| 6 | Credentials committed at any point | **PARTIAL** | a key **was committed in local history**; never pushed; revoked; purged; scans clean (§4). The literal "at any point" was breached locally |
| 7 | Undisclosed one-commit or burst history | PASS | 17 agent-paced commits, disclosed in APPROACH §15; three milestone commits proposed, not squashed |
| 8 | Write-up lists only strengths | PASS | APPROACH §11–13; estimates corrected by live data; trade-off tables |

## 3. Final test results
- **Working tree:** `make test` with credentials unset, `.env` loading disabled and sockets blocked: **191 passed**.
- **Milestone simulation** (scratch clone of HEAD, files added milestone by milestone, same conditions): baseline **187** → M1 **187** → M2 **190** → M3 **191**, all passing. The final simulated tree is byte-identical to the intended public files.

## 4. Credential incident: disclosure and cleanup evidence
1. A Gemini key had been typed into the tracked `.env.example`. A `git add -A` **committed it in local Git history** (Phase 7, commit `dcfe055`).
2. **That commit was never pushed.** The local repository has never had a remote, and the GitHub repository is empty (§5).
3. Detected in the same session by inspecting the commit's diff with values masked. The commit was amended. `tests/test_repo_hygiene.py` now fails, without printing values, if `.env.example` holds a secret or `.env` is tracked.
4. The author **revoked the key and replaced it**. The replacement was verified by hash only, and the purge was withheld until it was done.
5. **The leaked commit and all unreachable objects were purged** (`git reflog expire --expire=now --all && git gc --prune=now`) after checking that no unrelated work would be lost. Afterwards: 0 unreachable objects, 0 reflog entries, `fsck` clean.
6. **Later scans:**
   - Phase 10: all 223 Git objects and 79 files, including a current-key comparison: 0 hits;
   - Phase 10.1 and 10.2: the public manifest, by pattern, with `.env` not read: 0 hits.
7. Correct wording: "committed locally, never pushed, revoked, purged". **Never** "never committed".

## 5. GitHub repository verification (read-only)
| Check | Result |
|---|---|
| Local remote configured | **No** (`git remote -v` is empty; unchanged) |
| Repository exists | **Yes:** `Piyush-Sharma788/Mindmap` (unauthenticated `git ls-remote` exit 0; the public page loads) |
| Visibility | Readable while logged out → **effectively public**. The page doesn't state visibility explicitly |
| Owner | `Piyush-Sharma788` |
| Branches, commits, files | **None.** `ls-remote` returned 0 refs; the page says "This repository is empty"; no README, LICENSE or .gitignore |
| Divergence / unrelated history | **None possible.** The remote has no history |
| Content to preserve / overwrite risk | **None.** A normal (non-force) push of `main` creates the branch |
| Not verifiable here | Push permission and authentication (none used); repository settings |

## 6. File separation
**A. Intended public files (80).**
- **Code and configuration:**
  - `src/mindmap/**`: 30 files, including `evals/prompt_sizes.py`;
  - `tests/**`: 15 files (13 test modules plus `conftest.py` and `helpers.py`), including `test_offline_guarantees.py` and `test_repo_hygiene.py`;
  - `pyproject.toml`, `Makefile`, `.gitignore`, `.env.example` (blank values), `schema/mindmap.schema.json`.
- **Evaluation:**
  - `evals/cases.json`; `evals/docs/*` (8 files); `evals/maps/*` (3);
  - `evals/results/*`: the pipeline bench before and after, plus the smoke-test result, map and `.mmd`;
  - `evals/cassettes/22450a4b2b700e0fe308fcb03c65ac34.json`. It contains the model's JSON reply, stop reason, provider-reported usage, model name, timestamp and request id: **no credentials, headers or local paths** (checked).
- **Documents:** README, APPROACH, ARCHITECTURE, TECHNICAL_DECISIONS, REQUIREMENTS_CHECKLIST, FINAL_REQUIREMENTS_AUDIT, LIVE_EVALUATION_REPORT, CODE_WALKTHROUGH, PROJECT_CONTEXT (local path redacted in 10.2), SUBMISSION_CHECKLIST, PHASE_9_FINAL_AUDIT, SUBMISSION_READINESS_REPORT.
- **Checks:** pattern scan 0 secrets; no local paths or personal identifiers (other than the intended public repository URL).

**B. Local only.**
- `.env` (ignored, never tracked);
- `INTERVIEW_PREPARATION.md` (ignored now; untracked in M3 with `git rm --cached`; the file stays on disk);
- `CODE_REVIEW_GUIDE.md` (ignored);
- the assignment PDF (not in the folder; `*.pdf` ignored);
- `.venv/`, caches, `*.egg-info`.

**History caveat:** `INTERVIEW_PREPARATION.md` exists in committed history (Phase 6, `6cba432`). Untracking it removes it from the published *files*, but **its Phase 6 version stays visible in the pushed history**, unless history is rewritten (not recommended; not authorised).

## 7. Proposed milestone commits (verified by simulation; not staged)
Each file belongs to exactly one milestone, with one documented exception: `LIVE_EVALUATION_REPORT.md` is split.
- **M1** gets the report **without** §4.5.
- **M2** adds §4.5 (lines 84–88, the Phase 9 offline re-verification), a single contiguous block.

Other docs that carry small Phase 8/9 wording updates (README, APPROACH, FINAL_REQUIREMENTS_AUDIT, SUBMISSION_CHECKLIST, CODE_WALKTHROUGH, REQUIREMENTS_CHECKLIST) go **whole into M3**. Their hunks are interleaved with Phase 10 edits and can't be split safely without interactive staging. M3's message says so. **Order: M1 → M2 → M3** (M2's tests replay M1's cassette; M3's test counts assume M2).

**M1: `test: add recorded Gemini smoke evaluation`** (tests after: 187 passed)
- `evals/cassettes/22450a4b2b700e0fe308fcb03c65ac34.json`
- `evals/results/smoke-gemini-gen-photosynthesis.json`, `.map.json`, `.mmd`
- `LIVE_EVALUATION_REPORT.md` (§4.5 removed)

**M2: `test: strengthen offline evaluation and guarantees`** (tests after: 190 passed)
- `tests/test_offline_guarantees.py`
- `PHASE_9_FINAL_AUDIT.md`
- `LIVE_EVALUATION_REPORT.md` (full file, adding §4.5)

**M3: `docs: finalize submission readiness and engineering audit`** (tests after: 191 passed)
- code: `src/mindmap/observability.py`, `generate.py`, `grow.py` (the `summarize_usage` rename and a comment fix); `src/mindmap/evals/prompt_sizes.py`; `tests/test_eval.py`
- `.gitignore`
- README, APPROACH, FINAL_REQUIREMENTS_AUDIT, SUBMISSION_CHECKLIST, CODE_WALKTHROUGH, REQUIREMENTS_CHECKLIST, PROJECT_CONTEXT, SUBMISSION_READINESS_REPORT
- `git rm --cached INTERVIEW_PREPARATION.md`
- Suggested body: "Includes the summarize_usage rename, the prompt-size reproducer and submission documentation. Doc files also carry Phase 8/9 wording updates (file-level grouping). INTERVIEW_PREPARATION.md untracked and kept local."

**Commit rules (per the author):**
- the author's configured Git identity only;
- **no AI names and no `Co-authored-by` trailers** in these or future commits;
- AI assistance stays disclosed in APPROACH §14–15 (which also notes that the first 17 commits carry an AI trailer);
- before each commit: `make test` must show the counts above, and `git diff --cached --name-only` must match the list exactly.

## 8. Personal information still required
| Where | What |
|---|---|
| APPROACH §14 | code you personally **inspected and understood**; code you **modified or debugged** (or "none"); tests and reports you **reviewed** |
| APPROACH §15 | your **hands-on time**, separate from agent execution and approval pauses |
| Commit identity | **Confirmed by the author:** keep the existing configured identity for M1–M3; Git configuration unchanged; existing 17 commits not rewritten. GitHub profile linking depends on whether that email is verified on the account |

These can be filled before M3, or added as a fourth commit (`docs: add author contribution and time disclosure`).

## 9. Remaining risks and limitations
1. **Live evidence is n = 1, generate only (Gemini).** Grow (preservation, duplicate judgement, ≤ 2 requests, overflow) has **not** run on a real model. The documents say so; it remains the main scoring risk.
2. The credential incident (§4): disclosed and remediated, but a literal reading of "at any point" may still be penalised.
3. `INTERVIEW_PREPARATION.md`'s Phase 6 version stays in public history (§6).
4. The first 17 commits carry an AI co-author trailer; later ones won't (disclosed).
5. Known engineering limits (APPROACH §12):
   - duplicates use candidate slots;
   - greedy admission is not guaranteed optimal; the lexical backstop misses paraphrases;
   - replay needs matching settings and shows 0 ms latency;
   - the CLI loads `.env` in every mode;
   - a small, AI-written eval set.
6. The author must be able to explain agent-written code in the interview. Use `CODE_REVIEW_GUIDE.md` (local).

## 10. Safe publishing plan (each step needs approval)
1. Fill in the §8 personal fields; confirm the commit identity.
2. Create M1 → `make test` (187) → M2 → `make test` (190) → M3 → `make test` (191). Check the exact staged file list before each commit.
3. Pre-push checks:
   - `git status` clean except local files;
   - `git ls-files | grep -E '(^|/)\.env$'` prints nothing;
   - a bash pattern scan over `$(git rev-list --all)` finds no `AQ.`/`AIza`/`sk-ant-` keys;
   - `git fsck --unreachable` shows nothing unexpected;
   - `.env.example` blank.
4. `git remote add origin https://github.com/Piyush-Sharma788/Mindmap.git` (first remote).
5. `git push -u origin main`: a normal push, **never `--force`**; no tags.
6. Logged out, open the repository: confirm 20 commits, 191 tests listed in the README, and that `.env`, the PDF, `CODE_REVIEW_GUIDE.md` and the current `INTERVIEW_PREPARATION.md` are absent from the file tree.

## 11. Approvals still required
1. Your personal disclosures (§8). Commit identity: confirmed.
2. Approval to stage and commit M1, M2 and M3 as specified (including the M1/M2 split of the live report and `git rm --cached INTERVIEW_PREPARATION.md`).
3. Approval to add the `origin` remote and push `main`.

## 12. Recommendation
**NO-GO right now. GO after approvals 1–2, then publish on approval 3.**
- **Ready:** the code, the tests (191), the security posture, the commit plan (simulated and passing) and the remote (empty, no conflict).
- **What blocks submission:** the unfilled author disclosures and the missing commits.
- **Even after publishing:** the live evidence stays deliberately limited to the single Gemini smoke test.
