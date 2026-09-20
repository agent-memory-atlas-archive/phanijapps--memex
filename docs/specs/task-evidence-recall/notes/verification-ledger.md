# Task evidence recall verification ledger

## T1 benchmark

- 2026-09-20: The first 24-task fixture met the size gate but its active
  cards cited a generated evaluation source file. Independent review rejected
  that traceability claim. The initial scores are superseded and must not be
  used for a promotion decision.
- The original focused-query ceiling is also superseded because its questions
  appeared beside answer labels. The replacement query and summary fixtures
  were authored from task goals and eligible pages without those labels.
- 2026-09-20: The repaired corpus has 24 natural coding goals, 99 active
  source-backed cards, and 24 excluded distractors. An independent contributor
  authored 24 linked summaries and 72 focused questions from the label-free
  projection. Review found that the first linked-summary comparator credited
  links from multiple pages per task. The corrected comparator retrieves one
  page. Two isolated reruns matched on task, corpus, call, token, and recall
  counts: current injection completed 5/24 evidence sets, broad recall 7/24,
  linked summary 11/24, and human-focused questions 12/24. These are evidence
  retrieval scores, not completed coding tasks. After fixture and report
  integrity repairs, 684 tests passed, one was skipped, and coverage was
  90.24%; Ruff, mypy, and strict MkDocs passed. Adversarial and quality
  rechecks returned clean.

## T2 execution limit

- On 2026-09-20, the delivery owner approved a five-minute wall-time ceiling
  and $5 maximum model spend for one model-backed comparison run. Stop the run
  at either ceiling; extending either limit requires another explicit decision.
- Keep the comparison runner reusable across coding-agent harnesses, including
  pi, without changing the existing Memex recall operation.

## T2 comparison

- 2026-09-20: A capped pi comparison completed 24 task plans after one
  format-related interruption. Total observed model-run time was about 170.06
  seconds and observed catalog-equivalent use was about $0.00165; the first
  malformed response lacked retained usage, so that cost is a lower bound.
  The model candidate completed 7/24 evidence sets, tied broad recall, and
  trailed the linked-summary baseline's 11/24. The candidate stayed
  unpromoted. The exact scores, accounting limits, and per-task model usage
  are in `docs/research/2026-09-20-task-evidence-focused-candidate.md`.
- The approved plan requested three variable model runs. Only one full run fit
  the owner's five-minute ceiling after formatting recovery. The required
  uncertainty estimate is therefore unavailable, and this result cannot
  authorize promotion. Repeating it on pi or another harness requires a new
  model-run budget; the accepted promotion criteria remain open.
- A pre-run security review of the pi subprocess and untrusted output boundary
  found that plan-credit mode could start without catalog rates or a maximum
  output bound. T2 was changed to require both before launch, reserve the
  worst-case catalog equivalent before every call, count observed usage, and
  disable tools, extensions, skills, context files, prompt templates,
  project-local approvals, and session storage. The reviewer found no blocker
  for the explicitly bounded pi configuration after that correction.
- Final security review found that negative or non-finite harness usage could
  reduce tracked spend. The parser now stops before the next model call on
  invalid token or cost telemetry; regression tests cover negative tokens,
  negative or non-finite cost, and boolean token fields.
- Final quality review found that the run retained per-task model usage but
  discarded per-task hits and missing links. The runner now exposes a
  sanitized per-task evidence export for future runs. The prior run cannot be
  reconstructed without another model call, so AC-0003 remains incomplete.
- 2026-09-20: After both review fixes, the full suite passed with 700 tests,
  one skip, and 90.24% coverage in 237.05 seconds. Ruff, mypy, format, and
  strict MkDocs passed. Adversarial, security, and quality re-reviews returned
  clean.
- 2026-09-20: Full suite: 695 passed, one skipped, 90.24% coverage in 236.27
  seconds. The additional retry regression test passed. Ruff, mypy, and strict
  MkDocs passed.

## T3 documentation check

- 2026-09-20: With `MEMEX_DATA_DIR` set to a fresh `/tmp/memex-guide-*`
  directory, `uv run memex write --scope global --type entity --title "Ruff
  linter" --body "Fast Python linter written in Rust." --tags tool,lint
  --importance 0.8` wrote `ruff-linter`. `uv run memex recall "Ruff linter"
  --top-k 5` returned that active page as its only hit. Strict MkDocs built
  successfully after the guide and architecture updates.
