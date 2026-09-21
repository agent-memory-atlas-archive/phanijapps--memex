# Task evidence recovery comparison

- **Date:** 2026-09-20
- **Decision:** Keep revised task questions experimental. Do not change Memex
  recall, the task-start hook, or installed harness guidance.
- **Model:** pi 0.85.1, `zai-coding-cn/glm-5.3-flash`, low thinking on the
  completed continuation
- **Approved ceiling:** one comparison, 300 seconds and $5 total model spend

## Result

The revised question procedure asks for current behavior, prerequisites or
scope constraints, and verification or recovery needs before a coding task.
It used the existing project-scoped recall operation at most three times per
task. The prompt was frozen before the new task labels were scored; its SHA-256
is `0ccde0b6f6d61223cd45bbcadcd9e7c93d0d0264ad1efa932af820e32f93b233`.

| Corpus and strategy | Complete evidence sets | Required facts | Recall calls | Rendered tokens |
| --- | ---: | ---: | ---: | ---: |
| Prior 24 tasks: current hook | 5/24 | 28/64 | 24 | 14,988 |
| Prior 24 tasks: one broad query | 7/24 | 35/64 | 24 | 16,362 |
| Prior 24 tasks: linked summary | 11/24 | 45/64 | 24 | 4,485 |
| Prior 24 tasks: revised questions | 8/24 | 31/64 | 72 | 15,947 |
| Fresh 8 tasks: current hook | 3/8 | 25/32 | 8 | 4,456 |
| Fresh 8 tasks: one broad query | 6/8 | 29/32 | 8 | 4,281 |
| Fresh 8 tasks: linked summary | 8/8 | 32/32 | 8 | 1,457 |
| Fresh 8 tasks: revised questions | 5/8 | 28/32 | 24 | 3,608 |

The revised candidate beat one broad query by only one complete task on the
prior corpus, while finishing three fewer tasks overall than the linked
summaries: it missed five tasks the summaries completed and completed two
different tasks. On the
fresh corpus it trailed both baselines. It returned zero archived or
other-project hits in both cohorts. The fresh linked-summary baseline found
all required pages, so this small cohort cannot support the spec's required
ten-point improvement over that comparator. The result is a failed promotion
gate, not proof that all task-directed methods are ineffective.

The prior 24-task set had already been scored in an earlier experiment. The
fresh eight-task set was independently authored from pinned repository source
files before the revised candidate ran. A separate contributor wrote its
linked summaries from a view containing task goals and eligible pages but no
required-page labels. The new corpus has 44 active project cards, two archived
cards, and two other-project cards. Its fixture and summary SHA-256 hashes are
`7a6a273925343520901ddf5d2e9b4e40224fe3aee21422e40db4b736f3116ea5`
and `7bbe37875791504e8ac63165335b4c734953928f2a1840098534e23a9ce99a32`.

## Spend and audit trail

The first attempt stopped after three plans because two responses did not
yield valid question JSON. It used 56.29 seconds and a conservative
$0.00065995 catalog estimate. One format-only diagnostic call used 7.47 seconds
and a conservative $0.000113475 local token estimate; it returned valid JSON.
The completed continuation used 110.53 seconds and $0.001768925 in catalog
equivalent accounting. **Combined observed time was 174.29 seconds and the
conservative catalog estimate was $0.00254235**, below the approved ceilings.
The continuation was capped at 230 seconds and $4.9992 after the earlier
attempts. The Coding Plan did not expose an invoice-dollar charge, and the
two process launches did not share a durable budget counter.

The completed continuation made 32 model plans: 24 prior tasks and eight fresh
tasks under one runner limit. It used 18,349 input tokens, including cache
tokens, and 1,571 output tokens. The scorer wrote sanitized per-task
[prior-task evidence](task-evidence-recovery-2026-09-20/previous-tasks.json)
and [fresh-task evidence](task-evidence-recovery-2026-09-20/fresh-tasks.json).
Those files contain task names, hit and missing page slugs, calls, rendered
tokens, latency, scope-leak counts, and model usage. They contain no raw task
goals, prompts, generated questions, or memory bodies. An incomplete run
replaces both files with an empty result, so the files reflect the completed
continuation only.

The paired comparator traces are retained separately for the
[prior tasks](task-evidence-recovery-2026-09-20/previous-baselines.json) and
[fresh tasks](task-evidence-recovery-2026-09-20/fresh-baselines.json). They were
regenerated offline from the frozen fixtures after review and require no model
call. They include each strategy's task-level hits, misses, calls, tokens,
latency, and scope-leak counts without raw goals or memory text. The runner now
writes a cumulative budget ledger before model work, deducts known usage on a
retry, and blocks a retry after an interrupted or unmetered attempt. This
protection was added **after** the comparison above; the earlier launches were
accounted for manually and did not use that ledger. The
[closed historical ledger](task-evidence-recovery-2026-09-20/budget.json)
records those observed totals retrospectively so this evidence directory cannot
silently receive another run under the spent approval.

## What remains

The current test scores retrieval of required pages, not completed coding
behavior. The spec still needs repeated model runs for uncertainty, a completed
code-task comparison, a poisoned-memory agent trace, and a defensible model
token comparator before any automatic guidance change. Another model-backed
comparison needs a fresh approved ceiling. The next candidate should change
how distinct facts are gathered and assembled, then be tested on a larger
fresh set; another wording-only prompt revision is not supported by these
results. The filesystem search diagnostic found only one additional complete
task over broad FTS5 and does not justify a default `rg` tool.
