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
