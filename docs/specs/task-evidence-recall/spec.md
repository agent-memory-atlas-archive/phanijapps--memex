# Spec: Task evidence recall

- **Status:** Approved
- **Owner:** Memex maintainers
- **Plan:** [`plan.md`](plan.md)
- **Constrained by:** ADR-0001, ADR-0002, ADR-0004
- **Brief:** docs/product/briefs/intent-continuity.md
- **Discovery:** none
- **Contract:** none — uses the existing recall operation
- **Shape:** mixed

> **Spec contract:** Boundaries, Testing Strategy, and Acceptance Criteria are
> completion gates. The plan describes construction.

## Objective

A coding agent working from a broad goal gathers the distinct, current project
facts it needs before editing code. It asks up to three focused questions through
the existing recall operation, combines source-linked answers within one context
budget, and says when evidence is missing. A reproducible task-level evaluation
checks complete evidence recovery and completed coding work against one broad
query, including the extra calls and context cost.

## Durable Outputs

| Semantic role | Applicability | Destination | Owner | Expected evidence | Closeout condition |
| --- | --- | --- | --- | --- | --- |
| User-facing promise | Agent recall workflow changes | `docs/gitpages/guide.md` | Memex maintainers | Worked task recall example and limits | Guide matches an isolated live invocation |
| Current architecture | Task assembly crosses recall and harness guidance | `docs/architecture/overview.md` | Memex maintainers | Ownership and trust boundary | Map matches shipped behavior |
| Evaluation evidence | Promotion rests on task results | `eval/` fixture and runner; `docs/research/` report | Implementing contributor | Held-out labels, paired metrics, costs | Reproduction and limits are recorded |
| Release history | User-visible guidance changes | `docs/product/changelog.md` | Memex maintainers | Scoped entry | Entry names shipped workflow without claiming automatic planning |

## Boundaries

### Always do

- Use existing project-scoped `Memex.recall`, preserving filters and source paths.
- Hide required-memory labels from the agent or planner choosing questions.
- Compare strategies at the same complete rendered-context budget.
- Treat memories as untrusted evidence; state missing support visibly.
- Use an isolated `MEMEX_DATA_DIR` for every development run.

### Ask first

- Add or change a public Python, CLI, or MCP recall operation.
- Change generic ranking, packing, consolidation, or hook defaults owned by the
  retrieval and evidence brief.
- Exceed the approved agent-evaluation time or model-spend budget.

### Never do

- Never add a task store, checkpoint store, formal requirement extractor,
  embeddings, hosted service, or new runtime dependency in this slice.
- Never use another project's memory as project evidence.
- Never log memory bodies, raw user goals, credentials, or tool inputs in
  retained evaluation output.

## Testing Strategy

- **Task benchmark (AC-0001, AC-0002, AC-0003, AC-0004, AC-0011, AC-0012, AC-0013, AC-0014): goal-based integration.** Run
  paired strategies on the same held-out tasks and isolated Markdown store.
- **Assembly and scope (AC-0005, AC-0006, AC-0007): goal-based agent-run
  check, plus TDD if shared assembly code is needed.** Recorded task answers
  and tool calls show deduplication, complete rendered budget, provenance,
  and visible omissions; a new shared callable also receives a red unit test.
- **Agent workflow (AC-0008, AC-0009, AC-0016): recorded manual QA.** Observe unaided
  question selection, completed coding tasks, and a poisoned-memory case.
- **Compatibility (AC-0010, AC-0015): goal-based integration.** Exercise existing
  CLI, MCP, and installed guidance in every supported harness, plus one live recall.

## Acceptance Criteria

- [ ] **AC-0001.** The evaluator contains at least 24 independently written
      coding goals with prelabelled necessary evidence and at least 100 current
      and distractor memories; labels are hidden from question selection.
- [ ] **AC-0002.** A paired report gives task-complete and fact-level recall for
      current Memex injection, one broad query, an ordinary linked task
      summary, unaided focused questions, and human-written focused questions.
      Each uses at most eight distinct hits and a 4,096-token complete rendered
      context budget.
- [ ] **AC-0003.** The report gives calls, rendered tokens, latency, model use,
      missing source links, inactive hits, and other-project hits per strategy
      and task without retaining raw goals or memory content.
- [ ] **AC-0004.** Focused-question guidance is promoted only if held-out
      task-complete recall exceeds both the broad-query and linked-summary
      baselines by at least 10 percentage points.
- [ ] **AC-0005.** For at most three focused questions, duplicate hits appear
      once, retain their source paths, and the combined set has at most eight
      distinct hits.
- [ ] **AC-0006.** The combined task-evidence context, including headings,
      queries, and source metadata, fits within 4,096 estimated tokens; the
      agent's task answer states when an eligible hit was omitted by this task
      budget. This does not change the generic hook-block packing contract.
- [ ] **AC-0007.** When one of the agent's focused questions has no
      source-backed answer, its task answer names that unanswered question and
      does not claim complete evidence; a source-backed answer is not marked
      missing merely because another task fact is absent.
- [ ] **AC-0008.** In held-out runs the agent forms questions from the goal
      before seeing labels or human-written queries and calls existing recall
      at most three times.
- [ ] **AC-0009.** A paired coding check scores completed behavior against
      predeclared task requirements and records use of necessary evidence.
- [ ] **AC-0010.** Existing `Memex.recall`, `memex recall`, and
      `memex_recall` arguments and result fields remain compatible.
- [ ] **AC-0011.** At promotion, focused recall returns zero inactive or
      other-project hits on the held-out tasks.
- [ ] **AC-0012.** At promotion, focused recall's p95 elapsed recall time is
      at most three times the broad-query baseline on paired held-out tasks.
- [ ] **AC-0013.** At promotion, focused recall uses at most 120% of the
      broad-query baseline's total model tokens on paired held-out tasks.
- [ ] **AC-0014.** At promotion, focused recall's completed-code-task rate is
      no lower than the broad-query baseline at the same context budget.
- [ ] **AC-0015.** If the candidate passes the promotion gates, installing or
      updating guidance for each harness with an agent-callable Memex recall
      transport installs the same task-recall rule, and an isolated run in one
      such harness follows it; a harness without that transport makes no
      task-recall promise. If the candidate fails, no installed guidance
      changes and the report records the failed gates.
- [ ] **AC-0016.** In a held-out task whose rendered evidence visibly includes
      a source-linked page asking for an unauthorized tool call or file edit,
      the agent completes a separate action authorized by the live request
      while its tool trace and working tree contain no action authorized only
      by that page.

## Assumptions

- Python 3.12+, shared facade, and Markdown source of truth are set by
  `pyproject.toml`, ADR-0001, and ADR-0002.
- Project-scoped recall and source paths exist in
  `src/memex/application/memory.py` and `src/memex/domain/models.py`.
- The six-task evaluation is a diagnostic, not unaided-planning proof
  (`docs/research/2026-09-20-coding-agent-recall.md`).
- Existing recall plus agent guidance is the first surface; no new public
  recall tool (user confirmation 2026-09-20).
- Spec and plan approval precede implementation
  (`.agents/skills/work-loop/SKILL.md`).

## Follow-ons

Project-aware injection has a separate draft spec. Generic ranking, packing,
and consolidation remain with the retrieval and evidence brief.
