# Task evidence recall recovery plan

The first model-written questions recovered complete evidence for 7/24 tasks,
below the 11/24 linked-summary baseline. The missing pages often describe
prerequisites or constraints absent from the broad goal. The current hook
therefore stays in place while this plan tests question choice on fresh tasks.

## Phase 1: Freeze and measure

An independent contributor writes eight new source-backed coding tasks with
required pages hidden from the question planner and one ordinary linked summary
per task. Validate source hashes, labels, archived cards, and project scope.
Measure the current hook, one broad recall, and linked summaries before reading
candidate scores. Retain task-level hits and misses without goals or page text.

## Phase 2: Test one task-directed candidate

Freeze a revised prompt that asks for distinct current-behavior, prerequisite,
and verification information needs. Ask at most three questions through the
existing scoped recall operation. Run the prior and fresh tasks under one
shared five-minute, $5 model ceiling approved on 2026-09-20. Compare complete
evidence sets, fact recall, calls, rendered tokens, latency, and scope leaks.
Use no required labels to form questions or adjust the prompt after scoring.

## Phase 3: Decide what can ship

Keep the prompt experimental unless it beats both broad recall and linked
summaries by at least ten percentage points on the held-out comparison, has no
inactive or wrong-project hits, and passes the spec's cost, latency, completed
coding, and poisoned-memory checks. Build a shared bounded evidence assembler
only if the candidate needs one to meet the source and omission criteria. Add a
file-text fallback only if a fresh comparison shows a material gain beyond
scoped recall. If the ceiling ends before all checks finish, record the exact
unfinished checks and leave installed guidance unchanged.

The main spec and approved plan still own completion. This note is the next
in-intent execution sequence after the first unpromoted comparison.
