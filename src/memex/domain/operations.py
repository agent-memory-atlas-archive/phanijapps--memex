"""Operation contracts shared by every adapter (CLI, MCP, future API).

This module is the single source for the product's operation surface:
the canonical descriptions (what each operation is for, its constraints,
its output and failure shape) and the wire datatypes. Adapters must
consume these instead of declaring their own copies; tests pin the
datatypes to their domain-model twins so they cannot drift.

The descriptions deliberately restate constraints that schemas also
carry: not every consumer renders schemas, and the description is the
one guaranteed-read surface.
"""

from __future__ import annotations

from typing import NotRequired, TypedDict

from memex.domain.models import TurnRole

OPERATION_DESCRIPTIONS: dict[str, str] = {
    "memex_write": """Write a memory node to the filesystem wiki.

When to use: the user states a durable fact, preference, rule, or
summary worth recalling in later sessions.

Key constraints: type is one of "entity", "preference", "procedure",
"summary", "episode"; importance within [0, 1]; body is Markdown and
may include [[slug]] links to other memory nodes. Episode nodes belong
to memex_ingest_transcript, not this tool.

Returns {"slug", "file_path"} of the stored node. Writing an existing
slug updates it, preserving creation history and access counts.

Failures arrive on two channels: schema violations (wrong types,
importance out of range) are rejected by the server with an is_error
result naming the field; domain rejections return
{"error": "..."} — check that key before using the result. Side
effects: writes wiki/{type}/{slug}.md and updates the search index
and link graph.""",
    "memex_recall": """Search stored memories with BM25 full-text ranking.

When to use: at the start of a task, or whenever context from earlier
sessions is relevant; also to find a node's slug before updating or
forgetting it.

Key constraints: the query needs at least one alphanumeric token;
top_k within [1, 100] (default 10); optional node_type filter.
Expired or soft-forgotten nodes are hidden by default.

Returns hits ranked best-first, each with slug, title, snippet,
node_type, importance, and file_path. Empty hits is a normal result.

Failures arrive on two channels: schema violations are rejected by
the server with an is_error result naming the field; a query with no
searchable terms returns {"error": "..."} — check that key before
using the result. Side effects: bumps access counters for returned
hits (read telemetry only; memory files are untouched).""",
    "memex_consolidate": """Consolidate recent session episodes into durable memory nodes via LLM.

When to use: after ingesting transcripts, to distill episodes into
entity/preference/procedure/summary nodes. This is the only
LLM-calling operation; pass mode "dry-run" to preview without writing.

Key constraints: processes up to max_episodes most recent episodes
(default 10); requires configured LLM credentials (MEMEX_API_KEY or
memex.toml).

Returns a report with nodes_created (or would-be nodes in dry-run)
and token usage.

Failures arrive on two channels: schema violations are rejected by
the server with an is_error result naming the field; missing LLM
credentials return {"error": "..."} — check that key first. On LLM
failure the report comes back with no created nodes instead of an
error. Side effects (full mode): writes new nodes, links, and index
rows.""",
    "memex_forget": """Forget a memory node.

When to use: the user asks to remove, retire, or expire a memory.

Key constraints: mode "hard" permanently deletes the page and its
index and link entries (irreversible); "soft" sets valid_to and
"decay" sets expires_at — both keep the file and hide the node from
recall by default.

Returns {"slug", "forgotten", "mode", "file_path"}; file_path is null
after a hard delete.

Failures arrive on two channels: an unknown mode is rejected by the
server with an is_error result; an unknown slug returns
{"error": "memory node not found"} — check that key first.""",
    "memex_ingest_transcript": """Ingest a conversation transcript: stores turns verbatim as JSONL,
writes session metadata, and creates an episode memory node linking to it.

When to use: at session end, so later sessions can trace memories back
to this conversation.

Key constraints: session_id uses [A-Za-z0-9._-] only (it becomes a
filename); each turn needs role ("user", "agent", or "tool"),
content, and turn (1-based int); ts is optional ISO8601. Example
turn: {"role": "user", "content": "prefer ruff", "turn": 1,
"ts": "2026-09-15T10:00:00Z"}.

Returns a report with the episode_node slug and turn counts.

Failures arrive on two channels: malformed turn shapes are rejected
by the server with an is_error result naming the field; invalid
values return {"error": "..."} — check that key first. Re-ingesting
an existing session_id fails. Side effects: writes transcript and
episode files and updates the index.""",
    "memex_provenance": """Trace a memory node back to the conversation that produced it.

When to use: the user asks where a memory came from, or you need to
verify a memory before relying on it.

Key constraints: the slug must exist.

Returns confidence ("direct" for nodes created from a transcript,
"inferred" when an episode links to the node, "none" otherwise) plus
the transcript and metadata file paths.

Failures arrive on two channels, but this tool only produces
{"error": "memory node not found"} for an unknown slug — check that
key first. No side effects.""",
    "memex_export": """Export all memory nodes as a JSON document.

When to use: backup, migration, or inspecting the full memory store.

Returns {"version", "exported_at", "nodes"} where each node carries
slug, type, title, body, tags, importance, timestamps, links, and
transcript_ref.

Errors return {"error": "..."} — check that key first. No side
effects: nothing is written and no memory state changes.""",
    "memex_import": """Import memory nodes from a JSON export document.

When to use: restore or migrate memories produced by memex_export.

Key constraints: nodes is a list of objects as emitted by
memex_export; each needs a valid type and a non-empty title; invalid
entries are reported and skipped, not fatal.

Returns {"imported", "skipped", "errors"} counts.

Errors return {"error": "..."} — check that key first. Side effects:
writes wiki pages for imported nodes and updates the index and link
graph; importing an existing slug updates it.""",
}


def summary(operation: str) -> str:
    """First paragraph of an operation description, collapsed to one line."""
    return " ".join(OPERATION_DESCRIPTIONS[operation].split("\n\n")[0].split())


class TurnDict(TypedDict):
    """Wire shape of one transcript turn; pinned to TurnStreamEntry."""

    role: TurnRole
    content: str
    turn: int
    ts: NotRequired[str]
    tool_name: NotRequired[str]
    result: NotRequired[str]
    query: NotRequired[str]


class WriteResultDict(TypedDict, total=False):
    slug: str
    file_path: str | None
    error: str


class RecallResultDict(TypedDict, total=False):
    query: str
    hits: list[dict[str, object]]
    total_indexed: int
    search_engine: str
    search_time_ms: float
    error: str


class ConsolidateResultDict(TypedDict, total=False):
    mode: str
    episodes_processed: int
    nodes_created: list[dict[str, object]]
    nodes_updated: list[str]
    links_added: int
    llm_calls: int
    llm_prompt_tokens: int
    llm_completion_tokens: int
    dry_run: bool
    error: str


class ForgetResultDict(TypedDict, total=False):
    slug: str
    forgotten: bool
    mode: str
    file_path: str | None
    error: str


class TranscriptReportDict(TypedDict, total=False):
    session_id: str
    transcript_file: str
    meta_file: str
    episode_node: str
    episode_file_path: str
    turn_count: int
    user_turns: int
    agent_turns: int
    tool_turns: int
    error: str


class ProvenanceDict(TypedDict, total=False):
    slug: str
    direct_transcript_ref: str | None
    linked_episodes: list[str]
    transcript_files: list[str]
    meta_files: list[str]
    confidence: str
    error: str


class ExportDict(TypedDict, total=False):
    version: str
    exported_at: str
    nodes: list[dict[str, object]]
    error: str


class ImportReportDict(TypedDict, total=False):
    imported: int
    skipped: list[str]
    errors: list[str]
    error: str
