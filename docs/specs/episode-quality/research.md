# Desk research: episode page quality

**Date:** 2026-09-16 · **Scope:** `~/.memex/docs/episodes/` · **Trigger:** owner concern — "episodes logged are not holding good"

## Diagnosis

### What episode bodies look like today

Every episode body is a single deterministic template line:

```
Session {session_id} with 18 turns (5 user, 13 agent, 0 tool). Opened with: "# AGENTS.md instructions for /home/videogamer/projects/agentzero
<INSTRUCTIONS>
# AgentZero — Workspace Root
z-Bot is a multipurpose AI agent..."
```

Four problems, in severity order:

1. **The "Opened with" excerpt is system noise, not user intent.** The first
   user turn in a Codex/pi session is almost always AGENTS.md instructions,
   environment context, or plugin-list markup — not what the human asked for.
   Every episode body therefore opens with the same wall of system text.

2. **No statement of what the session accomplished.** The body records the
   session existed (turn counts) but not what was discussed, decided, built,
   or discovered. An agent reading the episode learns nothing actionable.

3. **No signal about the session's role in the memory graph.** The episode
   is the provenance anchor for every distilled page created from it, but
   carries no summary of what knowledge was extracted — so `get_provenance`
   answers "which transcript?" without answering "what happened?"

4. **Two of four episodes in the live store are test artifacts** (`live-e2e`,
   `rich-e2e`) from the developer's own E2E verification runs, polluting the
   store with non-memory data.

### What the raw transcripts actually contain (verified)

The signal for a good summary is present in the JSONL — the template just
ignores it:

| Session | Real user intent (first non-system turn) | Tools used | Last agent outcome |
|---|---|---|---|
| `01a0a79a…` | "memorize zbot architecture using memex" | — | Gave the agent a brief to fix memex's Codex capture |
| `01a0aab5…` | "Use engram mcp and list areas for improvement for zbot" | exec | "Memex recall is working. Two active indexed memories…" |
| `rich-e2e` | "Create an AGENTS.md and initialize this workspace…" | exec, send_message | "14 focused offline boundary tests… 115 pass" |

Filtering system noise (AGENTS.md, `<environment_context>`, `<recommended_plugins>`)
and extracting the first *real* user turn plus the last agent outcome yields a
body that answers "what was this session about?" in one or two sentences.

### What the reference systems do

- **Hindsight** (server-based): episode-level knowledge lives in LLM-extracted
  facts and consolidated observations, not in the session record itself. The
  session record is metadata (timestamps, counts); meaning lives downstream.
- **Letta**: raw session transcripts are stored verbatim (the "filesystem
  result"); the *distilled* pages are where the meaning lives. Session
  summaries exist only as LLM consolidation output.
- **memex today**: has the Letta model's separation (raw transcripts +
  distilled pages) but the episode page — the bridge between them — is a
  turn-count stub.

## Proposal

Two changes, ordered by impact and cost:

### 1. Deterministic summary upgrade (no LLM, ship now)

Replace the template with a filtered extraction that uses signal already
present in the parsed turns:

```python
def _summary(self, input, counts):
    real_user = first turn where role=user and content doesn't start
                with #, <, or system markers
    last_agent = last agent turn, truncated to 200 chars
    tools = unique tool_name set, up to 5
    body = f"Intent: {real_user[:150]}\n\nOutcome: {last_agent}\n\nTools: {tools}"
```

Example output for `01a0a79a…`:

> **Intent:** memorize zbot architecture using memex
>
> **Outcome:** Gave your agent this brief: "Fix memex's Codex transcript
> capture." The installed notify wrapper ingests only on agent-turn-complete…
>
> **Tools:** — · 18 turns (5 user, 13 agent, 0 tool)

This is deterministic (CI-testable), offline (no LLM), and extracts the
signal the transcripts already carry. Every future capture improves
automatically — idempotent re-captures rewrite the episode body.

### 2. LLM-enriched summary (optional, per-session)

When `[consolidation]` is configured, a `memex consolidate --episodes-only`
pass can *replace* the deterministic body with a 2-3 sentence LLM summary
(distill the session into: what was asked, what was decided, what was built,
what was learned). This rides the existing consolidation infrastructure and
the harness-as-LLM provider — no new mechanism.

**Sequencing:** ship (1) now as the default; (2) as an opt-in enrichment
that runs on the next turn-complete or post-consolidation.

### Cleanup (immediate)

`memex forget live-e2e --mode hard` and `memex forget rich-e2e --mode hard`
remove the two test-artifact episodes from the live store.
