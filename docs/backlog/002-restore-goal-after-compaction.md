# Restore the active goal after compaction

## Scenario and outcome

A coding agent works on a multi-turn goal with constraints and a next step. When its harness compacts the conversation to fit the context window, the earlier user request may no longer be present verbatim. The harness may summarize it, but Memex currently has no deterministic way to re-inject the active goal. The agent should resume with the current goal and constraints in the correct project without treating temporary work state as durable project knowledge.

## Current behavior and reproduction

Memex's Claude Code [`SessionStart` hook](../../marketplace/claude/settings-hooks.json) runs `memex hook session-start`, including when the harness emits a post-compaction session start. Without `--query`, that command uses the [workspace query](../../src/memex/infrastructure/workspace_context.py): directory name, Git branch, and latest commit subject. It does not read the original user goal. Claude's `UserPromptSubmit` hook passes a new user prompt to `memex hook prompt`, but compaction itself is not a new user prompt. The [Codex notification adapter](../../marketplace/codex/memex-codex-notify.py) captures transcripts around compaction; transcript capture does not inject the goal. The [pi extension](../../marketplace/pi/extensions/memex.ts) injects first-turn workspace recall or later prompt recall, with no explicit goal-restoration path.

1. In a test repository and isolated `MEMEX_DATA_DIR`, start a harness session with a distinctive goal, one constraint, and an unfinished next step. Keep that goal out of durable memory so a normal memory hit cannot hide the gap.
2. Continue until compaction, or use the harness's manual compact command. Resume without repeating the goal in a new user prompt.
3. Inspect the post-compaction context and Memex hook output. Check separately whether the harness's own summary mentions the goal and whether Memex re-injects it. For Claude Code, compare the post-compaction `SessionStart` output with `memex hook session-start` run in the same directory: the default query contains repo hints, not the earlier intent. Repeat in Codex and pi to establish each adapter's actual event behavior.

This is a missing guarantee in the Memex adapters, not a claim that every harness summary loses the goal. A real harness run is needed to measure the visible failure frequency.

## Potential fix

Keep a small **session-scoped** active-work snapshot: current goal, binding constraints, progress, and next step. Update it when the user changes the task, then inject it at a supported post-compaction boundary for each harness. Use the harness's own compaction summary where it reliably provides these fields; add adapter state only where needed. Key any Memex-owned state by session and project, bound its size, and clear it at session end. Do not write it to global or project durable memory merely to survive compaction.

First verify the available post-compaction events in Claude Code, Codex, and pi; then implement the smallest adapter path that can restore the snapshot. Test a completed goal, a changed goal, a resumed session, and a different project as well as the ordinary compact-and-resume case. Success means the resumed agent sees the current goal and constraints exactly once, without stale intent or cross-project state.
