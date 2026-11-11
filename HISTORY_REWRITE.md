# History Rewrite (2026-11-11)

**What changed:** at the author's request, the commit history was rewritten to remove one line from the messages of the first 17 commits: a `Co-Authored-By` trailer naming the AI tool used. `main` was then force-pushed, with a lease on the expected previous head.

**What did not change** (verified for all 21 commits before pushing):
- every commit's file tree (code and documents) is identical;
- author names and emails, committer names and emails, and author and commit dates are identical;
- each message equals the original with only that trailer line removed.

**Why the hashes differ:** a commit's hash covers its message, so every commit and its descendants received a new hash. Hashes quoted in documents written before the rewrite (phase reports, the readiness report, the walkthrough) refer to the **old** hashes. Use this table to translate them.

**Disclosure:** removing the trailers does not change authorship. The code, tests and documents were written with Claude Code, as stated in APPROACH.md §14, and that disclosure is unchanged.

| # | Old hash | New hash | Subject |
|---|---|---|---|
| 1 | `515e9c1` | `ec7c356` | Add planning docs (Phase 0-1) and gitignore |
| 2 | `ca45d66` | `c05cb77` | Milestone 1: project foundation |
| 3 | `44f5385` | `33d2112` | Milestone 2: data contract and derived provider schema |
| 4 | `1a2d289` | `4a3f4a6` | Milestone 3: generate pipeline and Anthropic provider |
| 5 | `d56bdce` | `2ef5eb2` | Milestone 4: grow pipeline within a hard 2-request budget |
| 6 | `383a921` | `abd9479` | Milestone 5: Mermaid rendering with escaping |
| 7 | `5b4639c` | `07cdfc6` | Milestone 6: CLI and eval runner with record/replay |
| 8 | `4621fb3` | `f5dfb66` | Fix report fields and credential error; add README |
| 9 | `cfb9f85` | `e4c4018` | Update checklist, decisions and architecture status after Phase 2 |
| 10 | `4e7fa9a` | `a74e1a0` | Phase 3 pre-spend: correct prices, spending ceiling, case filter |
| 11 | `3ddba30` | `d68b0f9` | Phase 3: add Gemini provider for free-tier live evaluation |
| 12 | `4021ba9` | `22f3808` | Phase 4 fixes: selection junk, input bound, admission, dedup, neutraliser |
| 13 | `03a6896` | `9bcead3` | Add deterministic pipeline bench (eval --mode pipeline) and CLI hints |
| 14 | `986d535` | `8595bc0` | Phase 4: realistic long-document eval case and documentation |
| 15 | `4b3c16a` | `40e5930` | Phase 5: APPROACH.md, live evaluation report (not run), readiness docs |
| 16 | `6cba432` | `af40451` | Phase 6: code walkthrough and interview preparation (docs only) |
| 17 | `2417b0e` | `0d5b799` | Phase 7: final requirements audit, submission checklist, doc consistency |
| 18 | `150327d` | `aec959d` | test: add recorded Gemini smoke evaluation |
| 19 | `4785915` | `b97264b` | test: strengthen offline evaluation and guarantees |
| 20 | `93bbfad` | `80e16ce` | docs: finalize submission readiness and engineering audit |
| 21 | `871af50` | `a7919ef` | test: ignore wall-clock latency in record/replay equality check |

The rewrite-recording commit that adds this file comes after #21.
