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

## T2 recovery limit and disposition

- On 2026-09-20, the delivery owner approved **one new held-out comparison**
  with a five-minute wall-time ceiling and $5 maximum model spend. This is a
  new allowance after the first run was spent. The runner must enforce both
  limits across the whole comparison, including retries; no additional model
  run is authorized by this entry.
- Resolve here: repair the active spec's stale `workspace.toml` membership,
  freeze a fresh task corpus before question tuning, implement the
  label-blind comparison, and assess whether bounded evidence assembly is
  needed. Surface later only a
  promotion decision whose remaining model or coding checks exceed the
  approved ceiling. No generic ranker or default hook change is justified by
  the one-task gain from the file-text diagnostic.
- The recovery sequence froze eight new goals, 48 cards, and eight linked
  summaries before the model comparison. The revised question prompt was also
  frozen before scoring. The first attempt stopped after three plans on
  malformed question JSON. A format-only diagnostic returned valid JSON. The
  completed continuation made 32 plans under a reduced 230-second and $4.9992
  cap; all attempts together took 174.29 seconds and a conservative $0.00254235
  catalog equivalent. The two launches did not have one durable budget counter.
- The revised candidate completed 8/24 prior tasks and 5/8 fresh tasks. Broad
  recall completed 7/24 and 6/8; linked summaries completed 11/24 and 8/8.
  The candidate failed both promotion margins with no archived or other-project
  hits. The paired scores and sanitized task traces are in
  `docs/research/2026-09-20-task-evidence-recovery.md`. The planned bounded
  evidence assembler is not needed for this failed question candidate and was
  not added. Completed-code and poisoned-memory agent checks remain open; no
  product recall or installed guidance changed.
- Review found that a retry could reset the comparison allowance and that
  candidate-only traces could not substantiate the baseline scores. The
  recovery runner now persists one cumulative wall/spend ledger, reserves the
  remaining allowance before work, and fails closed after an interrupted or
  unmetered attempt. Sanitized task-level comparator traces for both cohorts
  were regenerated offline from the frozen fixtures. These safeguards are
  prospective; the completed comparison used manual cumulative accounting.
- 2026-09-20: The follow-up runner and trace changes passed 737 tests with one
  skip and 90.24% coverage in 324.22 seconds. Ruff, mypy, strict MkDocs, and
  spec-status lint passed. The historical approval is recorded as closed in a
  retrospective budget file; no additional model call was made for these fixes.

## T3 documentation check

- 2026-09-20: With `MEMEX_DATA_DIR` set to a fresh `/tmp/memex-guide-*`
  directory, `uv run memex write --scope global --type entity --title "Ruff
  linter" --body "Fast Python linter written in Rust." --tags tool,lint
  --importance 0.8` wrote `ruff-linter`. `uv run memex recall "Ruff linter"
  --top-k 5` returned that active page as its only hit. Strict MkDocs built
  successfully after the guide and architecture updates.

## Product task recall slice

- 2026-09-20: Added optional project task mode to the existing recall CLI and
  MCP tool. It accepts one to three caller-written questions, interleaves up to
  eight unique active pages, reports questions with no eligible hit and
  questions whose eligible hits were omitted, and limits the complete context
  to 4,096 estimated tokens. One extra search hit per question detects a page
  omitted by the eight-page cap; only returned pages gain access credit.
- Review repairs rejected malformed question containers, aligned CLI and MCP
  page caps, and excluded a page forgotten in the current second. Adversarial,
  security, and quality rechecks returned clean. The full suite passed 756
  tests with one skip and 90.29% coverage in 323.52 seconds. Ruff, mypy,
  formatting, strict MkDocs, and spec-status lint passed. No model comparison
  ran, so the held-out task scores remain unchanged.
