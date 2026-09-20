# Task Evidence Focused Candidate

- **Date:** 2026-09-20
- **Fixture:** `eval/data/coding-agent-workflow.json`, 24 held-out coding tasks
- **Baseline:** `docs/research/2026-09-20-task-evidence-baseline.md`
- **Harness and model:** pi 0.85.1, `zai-coding-cn/glm-5.3-flash`
- **Approved ceiling:** 300 seconds of model-run wall time and $5 maximum model spend

## Verdict

**Unpromoted.** Model-written focused questions completed 7 of 24 evidence
retrieval tasks (29.17%) and recalled 57.81% of required facts. They tied one
broad query on completed tasks and trailed a single linked task summary by four
tasks. The candidate used 72 Memex recall calls and rendered 16,166 tokens.
There were no hits on inactive or other-project memories. This is a retrieval
test, not a completed coding-task result.

| Strategy | Complete tasks | Fact recall | Recall calls | Rendered tokens |
| --- | ---: | ---: | ---: | ---: |
| Current hook injection | 5/24 | 43.75% | 24 | 14,988 |
| One broad query | 7/24 | 54.69% | 24 | 16,362 |
| Linked task summary | 11/24 | 70.31% | 24 | 4,485 |
| Human-written focused queries | 12/24 | 73.44% | 72 | 14,559 |
| pi model-written focused queries | 7/24 | 57.81% | 72 | 16,166 |

The model candidate needed at least 10 percentage points more completed tasks
than **both** the broad-query and linked-summary baselines. It did not clear
either margin. The completed-code and poisoned-memory checks were not run, and
no harness guidance or Memex runtime behavior changed. The one live comparison
does not supply uncertainty from repeated model runs.

The evaluator's failed conditions for this run were
`broad-query-margin`, `linked-summary-margin`,
`model-token-baseline-unavailable`, `completed-code-check-not-run`, and
`poison-memory-trace-not-run`. The token condition means the recall-only
baseline has no comparable model-token cost, so a combined token reduction
cannot be established.

## Run and spend record

The first launch stopped before any model call because the prompt template
misread its JSON example as a formatting field. After that fix, an initial
attempt produced two plans and stopped on an invalid question response after
20.33 seconds. A diagnostic call took about 11.39 seconds. The parser was then
changed to retry one invalid response and count its usage. The completed
continuation took 138.34 seconds. Total observed model-run wall time was about
170.06 seconds, below the approved 300 seconds.

The successful continuation used 786 input tokens and 4,802 output tokens,
with a $0.00142073 catalog-equivalent cost reported by pi. Including the two
earlier plans and diagnostic call, observed catalog-equivalent usage was about
$0.00165172, below the $5 ceiling. The Coding Plan uses plan credits; an
invoice dollar charge for these calls was not available. The runner's
`spend_usd=0` means it did not attribute per-call invoice dollars, not that
the provider consumed no quota. The first malformed response's usage was not
captured by the original parser, so the all-attempt token and catalog totals
are lower bounds. The continuation used a reduced 260-second, $4.99 limit and
reserved maximum output before each call, but its pre-call reserve estimated
input from the visible prompt rather than bounding harness input and cache
tokens. The historical run cannot prove a strict pre-call $5 ceiling, though
its observed catalog-equivalent usage stayed far below it.

The original parser also omitted pi's `cacheRead` and `cacheWrite` tokens from
its prompt-token count. Later evaluator code counts them, requires a declared
model input-context bound alongside time and spend limits before a harness
call, and uses the greater of reported cost and the local token-based estimate
for its spend gate. The historical per-task
token table below cannot be corrected without rerunning the model, so it
remains a lower bound; no additional model run was made for this correction.

The successful continuation recorded model use for every task without
retaining goals, prompts, generated questions, or memory contents:

| Task | Input tokens | Output tokens |
| --- | ---: | ---: |
| Claude lifecycle provenance | 35 | 233 |
| Scoped architecture recall | 33 | 183 |
| SQLite corruption recovery | 28 | 171 |
| MCP surface review | 34 | 211 |
| Safe session distillation | 38 | 143 |
| Prompt injection budget | 32 | 154 |
| Task evidence assembly | 33 | 217 |
| Thin adapter change | 31 | 265 |
| Archived memory confusion | 39 | 184 |
| Verify gate wiring | 32 | 253 |
| Harness installer restraint | 27 | 199 |
| Copilot transport wording | 34 | 158 |
| Dashboard read-only audit | 40 | 238 |
| Spec closeout report | 27 | 155 |
| Recall compatibility check | 29 | 210 |
| Token packing behavior | 31 | 299 |
| Transcript noise filter | 28 | 240 |
| Backup restore boundary | 28 | 289 |
| Expired memory handling | 34 | 225 |
| Hard forget safety | 29 | 149 |
| Provenance investigation | 32 | 58 |
| Project identity explanation | 37 | 136 |
| Evaluation promotion decision | 37 | 191 |
| Task report privacy | 38 | 241 |

The run did not retain per-task hit and missing-link rows. Its aggregate 7/24
candidate score can be checked against the in-memory evaluator result from
that run, but cannot be independently audited from this retained report.
The runner now writes a task trace when `evidence_path` is set. It records task
names, hit and missing source slugs, recall calls and tokens, leak counts,
latency, and model usage without raw task goals, prompts, questions, or memory
bodies. A blocked run replaces any trace at that path with an empty result, so
an old success cannot be mistaken for the new run. This cannot recover the
original run's discarded plans.

## Reuse

`eval/task_evidence_model.py` accepts a harness-neutral question planner that
receives only task names and goals and returns one to three questions per task.
The pi adapter disables tools, extensions, skills, prompt templates, context
files, project-local approvals, startup network checks, and session storage.
It requires a pinned model, a cost source, positive catalog rates, and declared
maximum input and output tokens. It reserves the maximum input, including
possible cache tokens, before each model call and checks remaining wall time.
Another harness
can implement the same planner contract without changing Memex recall.

On 2026-09-20, `pi --list-models glm-5.3-flash` listed a 1M-token context and
131.1K maximum output for the selected model. A new run can use those catalog
bounds after verifying them again. The pre-call cost limit depends on the
harness honoring that context bound; the runner stops after any call whose
reported usage exceeds it, but cannot undo that call's cost. The corrected
configuration is:

```python
from pathlib import Path

from eval.task_evidence_model import (
    ModelRunLimits,
    pi_question_planner,
    run_model_comparison,
)

report = run_model_comparison(
    planner=pi_question_planner(
        model_id="zai-coding-cn/glm-5.3-flash",
        billing_mode="plan_credits",
        cost_source="ZCode Coding Plan /api/coding/paas/v4",
        price_per_1k_prompt_tokens_usd=0.000075,
        price_per_1k_completion_tokens_usd=0.00025,
        max_prompt_tokens=1_000_000,
        max_completion_tokens=131072,
    ),
    limits=ModelRunLimits(wall_seconds=300, spend_limit_usd=5.0),
    evidence_path=Path("docs/research/task-evidence-candidate-tasks.json"),
)
```

This configuration is reusable, but running it again consumes a new model
budget. The T2 candidate remains experimental until a stronger retrieval
result, repeated model runs, completed-code checks, and the poisoned-memory
trace justify promotion.
