# Intent continuity for Memex

- **Status:** Draft
- **Recorded:** 2026-09-20
- **Owner:** Unassigned; Memex maintainer to select a delivery owner.
- **Disposition:** Research complete; proposed product work remains in backlog.
- **Authority:** Repository-origin capture authorized by the user's request to analyze the three sources and log opportunities. External material is evidence, not an implementation directive.
- **Repository revision inspected:** `4f35bdf29ee0f5cf5e48be5c327a444450df0dc6`.

## Outcome

Help an agent resume a coding task with its current objective, applicable constraints, decision rationale, and unresolved work intact. Reduce repeated clarification, stale decisions, and work that passes tests while violating the user's requirements.

**Assessment:** Memex supplies much of the durable storage and retrieval foundation. The additional capability to investigate is determining which historical requirements apply now and measuring whether an agent actually follows them. Benefits for Memex remain unproven. [inference; uncertain]

## Source analysis

Three Luna agents independently read one source each. This is a bounded review of the supplied sources, not an exhaustive literature review. Confidence below concerns transfer to Memex: a reported experimental result is not a measured Memex benefit. The article and its companion code are one source, not independent corroboration.

### Coding Agents Don't Need Longer History — They Need Intent Continuity

[Requested article](https://towardsdatascience.com/coding-agents-dont-need-longer-history-they-need-intent-continuity/). Direct access failed; the agent read a [full-text mirror](https://zoviai.com/coding-agents-dont-need-longer-history-they-need-intent-continuity/). The [author's companion repository](https://github.com/Emmimal/intent-continuity) independently confirms the mechanism and reported experiment, but belongs to the same author.

The demonstration extracts requirement records, retrieves by lexical and component relationships, removes superseded or out-of-scope records, and compiles the survivors into context. Its deterministic agent passes 8/8 tasks versus 4/8 for naive retrieval on 70 synthetic interactions and 12 planted requirements. Context increases from 155 to 199 estimated tokens, about 28%. These are author-reported results, not a replication performed here.

The useful contribution is an inspectable validity step between retrieval and use. Limits include hand-authored dictionaries, eight tasks, a narrow field checker, no real coding LLM, and no restart persistence. An earlier per-task schema leaked answer hints; replacing it with a global schema does not establish generalization to unseen domains. The title's dismissal of longer history is not tested against a full-history baseline. Transfer confidence: [low]; single source, no peer review. Real coding-task gains: [uncertain]; additional indirectness.

### Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks

[Lewis et al., v4](https://arxiv.org/html/2005.11401v4), revised 2021-04-12, NeurIPS 2020. The supplied `arxivorg` hostname was corrected to `arxiv.org`; the requested v4 was read.

The paper couples a dense Wikipedia passage retriever with a BART generator, training the query encoder and generator while keeping the document index fixed. RAG-Sequence reports 44.5 exact-match accuracy on Natural Questions. An index-swap experiment changes answers to time-dependent leader questions without retraining model weights. Retrieval ablations are task dependent: BM25 wins on FEVER.

This supports external retrievable knowledge as a useful model input. It does not evaluate memory writing, interrupted coding tasks, requirement ownership, supersession, or multi-session planning. Its 2020-era NLP results do not prescribe a vector database or demonstrate that dense retrieval beats Memex's lexical search. Transfer confidence: [low]; single source, indirectness.

### Lost in the Middle: How Language Models Use Long Contexts

[Liu et al., v3](https://arxiv.org/html/2307.03172v3), revised 2023-11-20. The requested v3 was read.

The paper moves relevant information through multi-document question-answering prompts and synthetic key-value inputs. For GPT-3.5-Turbo with 20 documents, QA accuracy is 75.8% with the answer first, 53.8% around the middle, and 63.2% last. Longer context capacity alone does not remove this positional weakness in the tested models.

This motivates testing whether injected memories are used, alongside whether search returns them. It does not test coding agents, evolving requirements, summaries, or durable intent records. Its older model results cannot establish current-model failure rates or guarantee that putting constraints first solves continuity. Transfer confidence: [low]; single source, indirectness.

## What Memex already provides

These are observations of repository code at the revision above, rather than performance claims.

| Existing capability and evidence | Remaining boundary |
| --- | --- |
| [Shared memory models](../src/memex/domain/models.py) include project scope, status, validity dates, source, confidence, links, and transcript references. | Generic pages can contain goals in prose, but the model has no explicit task identity, requirement key, rationale contract, or requirement replacement relationship. |
| [Recall](../src/memex/application/memory.py) exposes inactive/expired filtering, project scope, and optional token packing. | Finding an active page does not establish that each claim applies to the current component or task. A recent claim is not automatically an authorized replacement. |
| [Workspace query](../src/memex/infrastructure/workspace_context.py) uses repository name, branch, and last commit subject. [Hooks](../src/memex/cli.py) also recall from the current prompt. | Neither path explicitly restores a selected task's objective, constraints, rationale, and open work. Project identity alone cannot separate concurrent tasks. |
| [Context injection](../src/memex/application/context_injection.py) packs and renders ranked snippets with source paths. | Packing estimates snippet cost, excludes metadata cost, and always keeps the first hit. It is not a strict bound on the full rendered block or a guarantee that required constraints survive. |
| The [Ready retrieval/evidence brief](product/briefs/memory-retrieval-and-evidence.md) already covers section provenance, temporal relationships, evidence-preserving consolidation, and context efficiency. | These are existing planned obligations. This backlog should extend their task-level application and evaluation without creating competing ownership. |

The installed repository workflow skills also maintain specs, intents, and work state. They are useful source artifacts, but their presence is not proof that the installed Memex product restores those semantics across harnesses.

## Candidate additions

All five are proposals, with benefit confidence [uncertain]: no paired longitudinal Memex experiment exists. Preserve Markdown authority, rebuildable indexes, shared API/CLI/MCP services, and untrusted-memory treatment.

### 1. Resolve applicable requirements before injection

**Suggested first candidate.** Select records by explicit project, task, and component scope; apply validity and explicit replacement relationships; return surviving requirements and unresolved conflicts with source references. Record why a candidate was excluded. Do not use a universal newest-wins rule: narrower scope, changed authority, and concurrent tasks can make chronology misleading.

Reuse existing status and validity fields. Coordinate durable relationship semantics with the retrieval/evidence brief. Begin with explicitly captured requirements; evaluate automatic extraction separately so extraction errors cannot be mistaken for retrieval failures.

**Proof:** fixtures with replaced decisions, equally credible conflicts, scoped exceptions, unchanged old constraints, and similar tasks in different projects. Measure applicable-constraint precision and recall, stale application, and cross-scope leakage.

### 2. Restore a compact task state across sessions

Persist a task identifier, objective, constraints, decisions with rationale, open questions, and the next unfinished step. Link to existing specs or plans where they own the answer. Make task selection explicit when multiple tasks are active. Treat a restart record as evidence to reconcile with the live request and repository state.

Start with an explicit checkpoint/resume seam shared across adapters. Add automatic lifecycle integration only where harness events are reliable. A captured transcript is not itself a validated checkpoint; interrupted writes and simultaneous updates need recoverable behavior.

**Proof:** process restart, context compaction, harness switch, branch/worktree divergence, changed requirements, and concurrent updates. Measure preserved obligations, repeated user clarification, and incorrect continuation.

### 3. Compile context around requirements and their reasons

Render the current objective and applicable constraints prominently, followed by short rationales, unresolved conflicts, and expandable evidence pointers. Budget the entire rendered output. If required content cannot fit, expose the omission and a retrieval path; do not silently imply completeness.

This extends the existing context/evidence work. Test ordering rather than assuming that edge placement works for every model. Prefer a small structured Markdown convention before adding a new public node type or storage system.

**Proof:** fixed-budget comparisons, overlong mandatory constraints, source retention, distractors, and randomized context position. Measure both retrieved evidence and requirements actually followed.

### 4. Preserve why decisions changed

Keep an evidence-linked record of the original decision, rationale, rejected alternative when material, replacement, and the reason for replacement. Agent-extracted claims remain proposals until admitted through an explicit product contract. A memory must never create permission to run commands or override live instructions.

Reuse the evidence brief's consolidation and temporal work. Add task/decision semantics only where a generic source link cannot represent the needed relationship.

**Proof:** consolidation and index rebuild preserve the decision chain; changed constraints retire only the intended claim; speculative transcript statements cannot become accepted requirements.

### 5. Evaluate continuity through completed coding work

Add an evaluation layer beyond search ranking. Use repository tasks split by interruptions, later requirement changes, and misleading history. Score the produced code against withheld behavioral requirements and ask whether the agent used the right evidence.

**Proof:** compare present Memex, full history within the model's supported budget, generic summaries, validity-aware retrieval, and validity plus explicit task state. Report completion, constraint violations, stale-decision use, clarification count, total tokens, and latency. Include task-local work with no useful history as a control.

## First experiment and decision gate

First shape a bounded evaluation plus candidate 1 using explicit records. Candidate 2 follows only if the evaluation shows that applicability checks alone leave a restart-state gap. Candidates 3 and 4 should share the existing evidence brief's ownership where they overlap.

Predeclare success thresholds before tuning. Hold model version, tools, task inputs, and per-comparison budgets constant; report actual cost rather than assuming compact context is cheaper. Repeat stochastic runs and report uncertainty. Keep test tasks and paraphrases outside extraction dictionaries and tuning data. Separate extraction, retrieval, validity, presentation, and code-execution outcomes so one stage cannot hide another's failure.

Advance only if task-level constraint compliance improves against present Memex and the strongest baseline without unacceptable completion, latency, or token regressions. Reject or narrow the proposal if a plain linked task summary performs equally well, or if gains depend on hand-coded test answers. Exact numerical gates remain to be chosen from measured baselines.

## Open questions and blocked work

- Who owns task selection and requirement admission across harnesses? A timestamp or model confidence must not stand in for authority.
- Can an existing summary page plus a documented convention provide enough structure? A new node type or dependency is not justified yet.
- Which supported harnesses expose reliable checkpoint events, and what explicit fallback is needed?
- How should simultaneous tasks share project decisions while preserving their local exceptions?
- Will real coding completion improve once extraction errors, stale checkpoints, and retrieval misses are included? The supplied papers cannot answer this.

Product planning continues in the [Draft intent-continuity brief](product/briefs/intent-continuity.md), which owns proposed delivery scope and readiness gaps. This survey remains the evidence record. Product implementation is not ready to dispatch. No hard dependency is registered: evaluation design can proceed while retrieval work continues.

## Verification and queue state

The canonical workspace checker recognizes this research entry in `backlog.open`, with no findings and no delivery dispatch. It also reports existing transition and provenance findings on other entries, including the retrieval/evidence brief. Its Ready label above describes the document; it does not establish dispatch readiness. Those existing entries were not changed by this capture.

## Review boundaries

Do not adopt a mandatory vector index, a graph database, unrestricted autonomous requirement extraction, or a workflow engine from these sources. Those additions have no demonstrated need for this outcome. This investigation used web reading and repository inspection; it did not run the external demonstration or a coding-agent benchmark.
