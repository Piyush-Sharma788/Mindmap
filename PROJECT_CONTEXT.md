# PROJECT_CONTEXT — Visualli AI Challenge: Mini Mindmap Engine

> **Status:** Phase 0 (analysis only). This file is the source of truth for the requirements. Read it before every phase.
> **Source:** `Visualli-AI-Challenge.pdf` (4 pages). It was attached in chat and is **not** in the repo directory.
> **Convention:** **[SPEC]** = stated explicitly in the PDF. **[INTERP]** = our reading of something the PDF leaves open (each one is listed in `TECHNICAL_DECISIONS.md`). Anything unmarked is a summary of [SPEC].

---

## 0. Repository state at Phase 0

- The project folder was **empty**: no files, no dependencies, no config.
- *(Phase 0 snapshot. Git was initialised in Phase 2.)* It is **not a git repository** yet. The PDF requires commits at each logical milestone, so `git init` must happen before or at the first code phase.
- Nothing existing had to be preserved or reused.

---

## 1. Overview

Visualli turns documents into interactive visuals using a multi-step LLM pipeline. The pipeline:
- runs on **documents Visualli has never seen**, and
- serves **users who pay per interaction**.

This challenge is a scaled-down version of that engine. [SPEC]

**Scope [SPEC]:** *the engine only*: **a library and a thin CLI.** No UI, no server, no deployment.
**Time budget [SPEC]:** **5–6 hours.**
**Language [SPEC]:** Python or Node, our choice.
**Guiding principle [SPEC]:** *"We care much more about the approach you can defend than about surface area. A small engine with a sharp write-up beats a large one without."* and *"Build something you can defend. That is the whole test."*

---

## 2. Problem statement

```
generate : text                              -> Mindmap
grow     : existing Mindmap + a new document -> a larger Mindmap
```

- **generate** turns a block of prose into a mindmap.
- **grow** takes an existing mindmap and a **second, different** document, and merges the new material into the map.

---

## 3. Functional requirements

### 3.1 Generate
- Input: a block of prose (text). Output: a `Mindmap` that satisfies the data contract (§5).
- The first generation must have **5 to 9 nodes**. [SPEC]
- The PDF sets **no** LLM-call limit for generate. [SPEC: silent] It still has to keep cost under control (see §6, cost architecture).

### 3.2 Grow — four hard constraints [SPEC]
1. **Existing nodes survive.** Do not regenerate the map.
2. **Material the map already covers must be dropped**, not added again (duplicate detection).
3. **The map has a ceiling of 25 nodes.** When the ceiling binds:
   - keep the **most valuable** material, and
   - **report what you left out.** *"Silently discarding the rest is a failure."*
4. **At most 2 LLM calls for the whole grow operation, however long the input document is.** *"Not two per chunk. This one is hard and we will test it."*

Also from the failure list: *"A `grow` whose cost grows with the length of the input document"* sinks the submission. So grow's **LLM cost** has to be bounded as well as its **call count**.

### 3.3 Duplicate detection
- Material the existing map already covers must not reappear as new nodes. [SPEC]
- How "covers" is defined (exact label match, semantic equivalence, or subsumption) is **not specified**. [INTERP → TD]

### 3.4 Node preservation
- Every existing node must still be present after grow. [SPEC]
- Whether "survive" also means the id, label and summary stay **byte-identical**, and whether existing connections must also survive, is not stated. [INTERP → TD; the conservative reading is: nodes unchanged, existing edges kept]

### 3.5 Prioritisation and the node ceiling
- The total must stay **≤ 25 nodes**. [SPEC]
- When candidates exceed the remaining capacity, choose by "most valuable". The PDF does not define value. [INTERP → TD]

### 3.6 Overflow reporting
- Anything left out because of the ceiling must be **reported**. [SPEC]
- The format and location of that report are not specified. [INTERP → TD] The `Mindmap` contract has no field for it, so it probably belongs in a wrapper result or a side channel.

### 3.7 Mermaid rendering
- `render` converts a map into **Mermaid** so a person can eyeball the output. [SPEC]

### 3.8 CLI [SPEC: names and flags are ours]
```
mindmap generate --in doc.txt --out map.json
mindmap grow     --map map.json --in doc2.txt --out map2.json
mindmap render   --map map.json --out map.mmd     # mermaid, so output is eyeballable
mindmap eval     --suite evals/
```

---

## 4. Technical constraints (critical)

| # | Constraint | Source |
|---|---|---|
| C1 | Generate produces **5–9 nodes** | SPEC |
| C2 | Grow never exceeds **25 nodes** | SPEC |
| C3 | Existing nodes **survive** grow; the map is not regenerated | SPEC |
| C4 | Covered material is **dropped**, not duplicated | SPEC |
| C5 | Overflow is **reported**, never silently discarded | SPEC |
| C6 | **≤ 2 LLM calls per grow**, independent of document length (tested by Visualli) | SPEC |
| C7 | Grow **cost** does not grow with input length | SPEC (failure list) |
| C8 | The data contract is defined in **one place**. Everything derives from it, **including the provider schema** ("we will look for the drift") | SPEC |
| C9 | **Code enforces the contract**, because the model will not | SPEC |
| C10 | Tests pass on a **clean clone with no API key** and not only on the author's machine | SPEC |
| C11 | **No credentials committed at any point**, including in a file that is later deleted | SPEC |
| C12 | Documents are **untrusted user input** | SPEC |
| C13 | Provider errors are **never** swallowed and replaced with canned output reported as success | SPEC (failure list) |
| C14 | A function name that implies a model call **must actually call a model** | SPEC (failure list) |
| C15 | Commit at each logical milestone. A one-commit project or an undisclosed burst minutes apart fails | SPEC |

[INTERP] Retries, repair re-prompts and any embedding calls in grow probably count toward the 2-call limit. Treat them conservatively: **every provider request counts.**

---

## 5. Data contract [SPEC, verbatim]

```ts
type MindmapNode = {
  id: string;       // stable, unique within the mindmap
  label: string;    // 1-4 words
  summary: string;  // one sentence
};

type MindmapConnection = {
  from: string;     // node id
  to: string;       // node id
  label: string;    // relationship, e.g. "causes", "part of"
};

type Mindmap = {
  title: string;
  rootId: string;   // must match a real node id
  nodes: MindmapNode[];
  connections: MindmapConnection[];
};
```

### Validation rules the code must enforce [SPEC]
- Node `id`s are **unique** within the mindmap. Ids are **stable**, which matters for grow.
- `rootId` **matches a real node id**.
- **No dangling edges**: every `from` and `to` refers to an existing node.
- **No self-loops**: `from != to`.
- **5–9 nodes on first generation**.
- `label` is **1–4 words**. `summary` is **one sentence**. These come from the field comments, and the PDF does not say whether they are strict validations or soft guidance. [INTERP → TD]
- **≤ 25 nodes** after grow.

### Single source of truth [SPEC]
One definition generates or derives: the runtime validators, the JSON Schema or tool schema sent to the LLM provider, the types used in code, and the fixtures and docs. Hand-written duplicates are a scored defect.

### Open points not covered by the contract [INTERP → TD]
- Must the graph be connected, with every node reachable from the root? Tree or DAG? Are duplicate edges allowed?
- Must `title` be non-empty? Does it relate to the root label?
- Does "1–4 words" count hyphenated terms as one word? What counts as "one sentence"?

---

## 6. Evaluation criteria

### 6.1 Weighting [SPEC]
| Weight | Area |
|---|---|
| **35%** | `APPROACH.md` and the thinking in it |
| **30%** | A working engine, with `grow` inside its call budget |
| **20%** | Evaluation |
| **15%** | Code quality, and tests that pass on a clean clone with no API key |

### 6.2 Scored dimensions [SPEC]. The answers are deliberately not given: "how you address it, how far you take it, and what you decide to skip are all signal."
- 🤖 **Agentic design.** Where an agent loop earns its place in this pipeline and where it is overkill. **Guardrails and observability** are part of this question.
- 🔀 **Model strategy.** Which model for which step, and why. Which parameters are set and **what they actually do to the output**.
- 🧪 **Evaluation.** How we know the output is good, and how we would know a change made it better. Decide what to measure, then build enough to **put a real number on the table**.
- 💰 **Cost architecture.** What one user interaction costs, and what we did about it.
- 🛡 **Untrusted input.** The documents come from users. Work out what that implies and act on it.

### 6.3 What each weight expects (our reading)
- **35% APPROACH.md:** defensible reasoning, honest trade-offs, every number justified or labelled "guessed, untested", listed known bugs.
- **30% Engine:** generate and grow work end to end against a real provider. Grow respects C1–C7 and the budget is **provably** enforced.
- **20% Evaluation:** a runnable `eval` command with a suite that produces real, reproducible numbers, which can be compared before and after a change.
- **15% Code quality:** a clean structure, a single-source contract, and an offline test suite (fake or recorded provider) that passes from a clean clone.

---

## 7. Deliverables [SPEC]

1. **A public repository URL.**
2. **README.md:** one setup command after a clean clone, one command to run the tests with no API key, and the providers and models used.
3. **APPROACH.md** (short; bullets fine; "four honest sentences beat four polished paragraphs"), covering:
   - the **design** as high-level blocks: what talks to what, and where the model calls sit;
   - **every number chosen** and the failure it prevents ("guessed, untested" is respected; a confident number that cannot be defended is not);
   - the **cost** of one `generate` and one `grow`, and the **cheapest change that would roughly halve it** (that change does not need to be made);
   - **one thing deliberately not done with a model**, and why;
   - **what was built and thrown away**;
   - **known bugs not fixed** ("scores positively"; an unlisted bug "costs you much more");
   - **what was cut for time**, and what we would do with another month;
   - **the AI tools used**, and roughly which parts they wrote.
4. **A time note:** the actual time spent, and what is rough because time ran out.

### Ground rules on AI assistance [SPEC]
- AI use is allowed with no penalty, but it **must be disclosed**.
- **"You own every line."** In the interview Visualli will pick a number in the code and ask why it is that number, and will ask for a **live change to the pipeline in under 20 minutes**.

---

## 8. Failure conditions ("What sinks a submission") [SPEC, complete list]

1. A function whose name implies a model call but which is keyword matching or hardcoded strings underneath.
2. A catch-all that swallows a provider error and returns canned output as a success.
3. A `grow` whose cost grows with the length of the input document.
4. Numbers in the write-up that the code cannot produce.
5. Tests that need an API key, or that only pass on your machine.
6. Credentials committed at any point, including in a later-deleted file.
7. The whole project in one commit, or a burst minutes apart, undisclosed.
8. A write-up that lists only strengths.

Further failures stated elsewhere in the PDF:
- Silently discarding material when the 25-node ceiling binds (§3.2).
- Drift between hand-written copies of the contract (§5).
- More than 2 LLM calls in grow, or 2 calls *per chunk* (§3.2).

---

## 9. Standing rules for all future phases
- Read this file and `REQUIREMENTS_CHECKLIST.md` before starting any phase. Check the PDF when in doubt.
- Never silently weaken a [SPEC] constraint. If a constraint has to be relaxed, record it in `TECHNICAL_DECISIONS.md` and in `APPROACH.md`.
- Update the checklist status as work progresses.
- Do not implement until the user has explicitly approved the next phase.
