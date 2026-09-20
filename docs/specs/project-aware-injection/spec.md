# Spec: Project-aware injection

- **Status:** Draft
- **Owner:** Memex maintainers
- **Plan:** [`plan.md`](plan.md)
- **Constrained by:** ADR-0001, ADR-0002, ADR-0004
- **Brief:** docs/product/briefs/intent-continuity.md
- **Discovery:** none
- **Contract:** none — preserves the existing hook command and output shape
- **Shape:** mixed

> **Spec contract:** Boundaries, Testing Strategy, and Acceptance Criteria are
> completion gates. The plan describes construction.

## Objective

A coding agent beginning work in a project receives relevant current-project
memories and deliberate global preferences from Memex's enabled session-start
hook, without another project's history or a false claim of complete context.
A paired evaluation determines whether the existing hook has a real relevance
problem before its default selection rule changes. The same rule applies through
the shared hook operation across supported harnesses.

## Durable Outputs

| Semantic role | Applicability | Destination | Owner | Expected evidence | Closeout condition |
| --- | --- | --- | --- | --- | --- |
| User-facing promise | Injection selection may change | `docs/gitpages/guide.md` | Memex maintainers | Hook scope and empty/partial result behavior | Guide matches an isolated hook run |
| Current architecture | Project identity and scope selection meet | `docs/architecture/overview.md` | Memex maintainers | Rule owner and trust boundary | Map matches shipped rule |
| Evaluation evidence | Change is conditional on measured failures | `eval/` runner and `docs/research/` report | Implementing contributor | Paired cases, rendered output, costs | Reproduction and promotion decision recorded |
| Release history | Required only if hook default changes | `docs/product/changelog.md` | Memex maintainers | Scoped entry | Entry exists only for changed behavior |

## Boundaries

### Always do

- Evaluate session-start output for current project, another project, valid
  global preference, archived fact, and unknown-project cases before promotion.
- Preserve explicit user enablement, the `memex hook session-start` command,
  and the current context-block output contract.
- Keep current-project and global selection rules explicit and verifiable.
- Run all hook demonstrations in an isolated `MEMEX_DATA_DIR`.

### Ask first

- Alter user-owned harness configuration or activation defaults.
- Change generic ranker or context packing behavior owned by the retrieval and
  evidence brief.
- Change public hook arguments or context-block format.

### Never do

- Never enable capture or injection from repository contents alone.
- Never let a repository name or Git subject grant access to another project's
  memories.
- Never add a persistent project state model, network lookup, or new runtime
  dependency for hook selection.

## Testing Strategy

- **Baseline and promotion (AC-0001, AC-0002, AC-0003, AC-0010, AC-0011, AC-0012): goal-based integration.**
  Run the real hook over isolated stores for known and unknown projects and
  compare complete rendered output.
- **Selection safety (AC-0004, AC-0005, AC-0006, AC-0013, AC-0014, AC-0015, AC-0016): TDD plus integration.** Test
  project and global candidates, non-Git directories, and archived pages at
  the shared injection boundary.
- **Harness and user path (AC-0008, AC-0009, AC-0017): recorded manual QA.**
  Invoke the real CLI hook from an enabled test harness, verify that
  installation remains opt-in, and observe a poisoned-memory case.

## Acceptance Criteria

- [ ] **AC-0001.** The baseline report covers at least 24 held-out task starts
      across current-project, other-project, global-preference, archived, and
      unknown-project cases, scoring required facts, irrelevant facts, complete
      rendered tokens, and hook latency.
- [ ] **AC-0002.** A changed default is eligible only when baseline output has
      at least one missing required current-project fact or one unrelated
      other-project fact or a missing prelabelled required global preference
      or an archived, superseded, or otherwise inactive page in the held-out
      set; the paired report identifies
      the triggering case and the candidate's result for that same case.
- [ ] **AC-0003.** When AC-0002's baseline trigger is absent, the report records
      no default change and the shipped hook behavior remains compatible.
- [ ] **AC-0004.** With a known project, injected project-scoped hits have that
      project's identifier; no other-project page appears in stdout, stderr,
      logs, or agent-visible hook output.
- [ ] **AC-0005.** A global preference selected for injection is distinguishable
      from a project fact by its source path, and every prelabelled required
      global preference remains in the candidate's held-out context.
- [ ] **AC-0006.** In a non-Git directory with no remote, the hook uses only
      the path-derived project identifier and eligible global preferences;
      entering a Git project still returns its own labelled project fact.
- [ ] **AC-0008.** `memex hook session-start` retains its documented command,
      exit code, and context-block shape on supported harness paths.
- [ ] **AC-0009.** Installing a harness remains an explicit user action;
      merely opening or cloning a repository cannot enable hook injection.
- [ ] **AC-0010.** A candidate default produces zero other-project hits and
      no more irrelevant global-history hits than baseline on the held-out set.
- [ ] **AC-0011.** A candidate default's p95 hook latency is at most baseline
      p95 plus 20 milliseconds on paired held-out starts.
- [ ] **AC-0012.** A candidate default recovers at least as many prelabelled
      required current-project facts as baseline on every held-out task start;
      when missing local evidence triggered AC-0002, it recovers at least one
      additional required fact on that same triggering case.
- [ ] **AC-0013.** A candidate default emits zero archived, superseded, or
      otherwise inactive pages in the held-out hook output.
- [ ] **AC-0014.** Before any project-memory read or access-statistic update,
      the hook derives the current project identifier and applies it to every
      project-scoped recall; a matching other-project page produces no read,
      access update, stdout, stderr, log, or agent-visible content from that
      page.
- [ ] **AC-0015.** Automatic cross-project context includes only active pages
      explicitly written with global scope and preference type; global
      episodes, summaries, and project-derived pages produce no stdout,
      stderr, log, or agent-visible content from those pages.
- [ ] **AC-0016.** If project identity derivation, query validation, or index
      or store read fails, or a lower-level operation raises a timeout while
      the hook still runs, the hook makes no broad-scope
      fallback read and emits no memory body, raw path, or raw query in stdout,
      stderr, logs, or agent-visible output; it exits 0 with empty stdout and
      a bounded diagnostic on stderr for operational failures.
- [ ] **AC-0017.** For each of a current-project fact and an eligible global
      preference containing an unauthorized tool/file instruction, a recorded
      agent run proves that the source-linked page reached the rendered hook
      context, completes a separate live-request-authorized action, and has no
      tool call or file edit authorized only by that page.

## Assumptions

- The current session-start query uses repository, branch, and latest commit
  text; `build_injection` calls global recall
  (`src/memex/infrastructure/workspace_context.py`,
  `src/memex/application/context_injection.py`).
- ADR-0002 requires shared application behavior across adapters.
- ADR-0004 requires explicit user enablement.
- The hook spec is conditional on measured relevance failures and does not
  itself authorize a default change (user confirmation 2026-09-20).
- Spec and plan approval precede implementation
  (`.agents/skills/work-loop/SKILL.md`).

## Follow-ons

Task-level question planning and evidence assembly belong to
`docs/specs/task-evidence-recall/spec.md`. Generic packing changes stay with
the retrieval and evidence brief; this spec reports any full-block budget
violation there instead of changing the block format.
