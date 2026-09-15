"""Optional stdio MCP server exposing memex tools (spec §7 Utility 11).

The official MCP Python SDK owns transport, framing, and schema handling.
The docstrings on the tool functions are pyguide maintainer docs; the
agent-facing wire descriptions and datatypes live in
memex.domain.operations and are passed at registration, so every
adapter (CLI, MCP, future API) shares one contract surface.

No tool raises: schema violations are rejected by the SDK with an
is_error result naming the field, and domain rejections return
``{"error": "..."}`` data with a sanitized, generic message. No memory
contents, paths, or provider details ever cross the stdio boundary.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Annotated, Any, cast

from mcp.types import ToolAnnotations
from pydantic import Field

from memex.application.dto import to_jsonable
from memex.application.memory import Memex
from memex.domain.errors import MemexError
from memex.domain.models import (
    ConsolidateInput,
    ConsolidateMode,
    ForgetMode,
    IngestTranscriptInput,
    NodeType,
    TurnStreamEntry,
    WriteInput,
)
from memex.domain.operations import (
    OPERATION_DESCRIPTIONS,
    ConsolidateResultDict,
    ExportDict,
    ForgetResultDict,
    ImportReportDict,
    ProvenanceDict,
    RecallResultDict,
    TranscriptReportDict,
    TurnDict,
    WriteResultDict,
)

logger = logging.getLogger("memex")

_lock = threading.Lock()
_memex: Memex | None = None


def _get_memex() -> Memex:
    global _memex
    with _lock:
        if _memex is None:
            _memex = Memex()
        return _memex


def _reset() -> None:
    """Close and drop the shared instance (test isolation)."""
    global _memex
    if _memex is not None:
        _memex.close()
    _memex = None


def _sanitize(exc: Exception) -> str:
    """Map failures to a safe, generic message by error type."""
    if isinstance(exc, FileNotFoundError):
        return "memory node not found"
    if isinstance(exc, ValueError | TypeError):
        return "invalid arguments for this operation"
    if isinstance(exc, FileExistsError):
        return "resource already exists"
    return "operation failed"


def _caught(tool: str, exc: Exception) -> dict[str, str]:
    """Sanitize any failure; unexpected crashes are logged for operators."""
    if not isinstance(exc, (MemexError, ValueError, TypeError, FileNotFoundError, FileExistsError)):
        logger.error("operation=%s status=unexpected-error error_type=%s", tool, type(exc).__name__)
    return {"error": _sanitize(exc)}


def memex_write(
    type: NodeType,
    title: str,
    body: str,
    tags: list[str] | None = None,
    importance: Annotated[float, Field(ge=0, le=1)] = 0.5,
    links: list[str] | None = None,
) -> WriteResultDict:
    """Persist one memory node and update the index and link graph.

    New nodes get a derived, collision-suffixed slug; writing an existing
    slug updates it, preserving id, created, and access counters.

    Args:
        type: Episode is not creatable here — episodes require a session,
            so use memex_ingest_transcript for those.
        title: Human-readable; the slug derives from it.
        body: Markdown; ``[[slug]]`` references become wiki links, merged
            with ``links``.
        tags: Lowercased and deduplicated on write.
        importance: Schema-enforced bounds [0, 1].
        links: Explicit outgoing slugs in addition to body links.

    Returns:
        ``{"slug", "file_path"}`` on success; ``{"error": str}`` on
        domain rejection (sanitized — see module docstring).
    """
    try:
        node = _get_memex().write(
            WriteInput(
                type=type,
                title=title,
                body=body,
                tags=tags or [],
                importance=importance,
                links=links or [],
            )
        )
        return {"slug": node.slug, "file_path": node.file_path}
    except Exception as exc:
        return cast(WriteResultDict, _caught("memex_write", exc))


def memex_recall(
    query: str,
    top_k: Annotated[int, Field(ge=1, le=100)] = 10,
    node_type: NodeType | None = None,
) -> RecallResultDict:
    """Search the index with BM25 and return ranked hits.

    The query is reduced to alphanumeric tokens joined by OR, so
    untrusted input never reaches the FTS5 MATCH parser. Expired and
    soft-forgotten nodes are hidden by default.

    Args:
        query: Free text; must contain one alphanumeric token.
        top_k: Default 10; schema bounds [1, 100].
        node_type: Optional equality filter on node type.

    Returns:
        RecallResult as JSON — hits ranked best-first (slug, title,
        snippet, importance, file_path), total_indexed, search_time_ms.
        Empty hits is a normal outcome, not an error. Recall bumps
        access_count and last_access for returned hits (read telemetry
        only; memory files are untouched).
    """
    try:
        result = _get_memex().recall(query, top_k=top_k, node_type=node_type)
        return cast(RecallResultDict, to_jsonable(result))
    except Exception as exc:
        return cast(RecallResultDict, _caught("memex_recall", exc))


def memex_consolidate(
    mode: ConsolidateMode | None = None,
    max_episodes: Annotated[int, Field(ge=1)] = 10,
) -> ConsolidateResultDict:
    """Distill recent episodes into durable nodes via one LLM call.

    The only LLM-calling operation, and only on explicit request. In
    "dry-run" nothing is written; on LLM API failure the report returns
    with no created nodes instead of an error.

    Args:
        mode: "full" (write) or "dry-run" (preview); default "full".
        max_episodes: How many most-recent episodes to process;
            default 10. Distillation can use a dedicated low-effort
            model via [consolidation] config.

    Returns:
        ConsolidationReport as JSON — mode, episodes_processed,
        nodes_created, nodes_updated, links_added, token usage, dry_run.
    """
    try:
        report = _get_memex().consolidate(
            ConsolidateInput(mode=mode or "full", max_episodes=max_episodes)
        )
        return cast(ConsolidateResultDict, to_jsonable(report))
    except Exception as exc:
        return cast(ConsolidateResultDict, _caught("memex_consolidate", exc))


def memex_forget(slug: str, mode: ForgetMode | None = None) -> ForgetResultDict:
    """Remove a memory: delete the page, or retire it temporally.

    "hard" deletes the file and purges its index row and wiki_links in
    both directions (irreversible). "soft" and "decay" keep the file,
    set valid_to / expires_at respectively (default now), and hide the
    node from recall unless include_expired is passed.

    Args:
        slug: Wiki page slug.
        mode: One of "hard", "soft", "decay"; default "hard".

    Returns:
        ForgetResult as JSON — slug, forgotten, mode, file_path (null
        after a hard delete).
    """
    try:
        result = _get_memex().forget(slug, mode=mode or "hard")
        return cast(ForgetResultDict, to_jsonable(result))
    except Exception as exc:
        return cast(ForgetResultDict, _caught("memex_forget", exc))


def memex_ingest_transcript(session_id: str, turns: list[TurnDict]) -> TranscriptReportDict:
    """Store a transcript verbatim and create its episode node.

    Creates three artifacts — transcripts/{session_id}.jsonl,
    .meta.json, and wiki/episodes/{session_id}.md with transcript_ref —
    and indexes the episode. Turn contents are never logged. Re-ingest
    fails unless overwrite semantics are added; session_id becomes a
    filename (validated charset).

    Args:
        session_id: [A-Za-z0-9._-] only.
        turns: TurnStreamEntry-shaped dicts; ts optional (empty means
            unknown and is omitted from the JSONL).

    Returns:
        TranscriptLinkReport as JSON — episode_node slug, file paths,
        turn counts by role.
    """
    try:
        parsed = [TurnStreamEntry.from_dict(turn) for turn in turns]
        report = _get_memex().ingest_transcript(
            IngestTranscriptInput(session_id=session_id, turns=parsed)
        )
        return cast(TranscriptReportDict, to_jsonable(report))
    except Exception as exc:
        return cast(TranscriptReportDict, _caught("memex_ingest_transcript", exc))


def memex_provenance(slug: str) -> ProvenanceDict:
    """Trace a node back to its originating transcript(s).

    Pure query, no side effects.

    Args:
        slug: Wiki page slug.

    Returns:
        ProvenanceReport as JSON — confidence "direct" (node carries a
        transcript_ref), "inferred" (an episode links to the node), or
        "none"; transcript and metadata file paths.
    """
    try:
        report = _get_memex().get_provenance(slug)
        if report is None:
            return {"error": "memory node not found"}
        return cast(ProvenanceDict, to_jsonable(report))
    except Exception as exc:
        return cast(ProvenanceDict, _caught("memex_provenance", exc))


def memex_export() -> ExportDict:
    """Export every node as an import-ready JSON document.

    Pure read: nothing is written and no memory state changes.

    Returns:
        Export document as JSON — version, exported_at, nodes (each
        with slug, type, title, body, tags, importance, timestamps,
        links, transcript_ref).
    """
    try:
        return cast(ExportDict, to_jsonable(_get_memex().import_export.export()))
    except Exception as exc:
        return cast(ExportDict, _caught("memex_export", exc))


def memex_import(nodes: list[dict[str, Any]]) -> ImportReportDict:
    """Import nodes from a memex_export document.

    Invalid entries are reported and skipped, not fatal. Importing an
    existing slug updates that node.

    Args:
        nodes: Objects as emitted by memex_export; each needs a valid
            type and a non-empty title.

    Returns:
        {"imported": int, "skipped": list, "errors": list}.
    """
    try:
        return cast(
            ImportReportDict, to_jsonable(_get_memex().import_export.import_data({"nodes": nodes}))
        )
    except Exception as exc:
        return cast(ImportReportDict, _caught("memex_import", exc))


@dataclass(frozen=True)
class ToolSpec:
    fn: Any
    title: str
    annotations: ToolAnnotations


_TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        memex_write,
        "Memex: write memory",
        ToolAnnotations(
            title="Memex: write memory",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
    ),
    ToolSpec(
        memex_recall,
        "Memex: recall memory",
        ToolAnnotations(
            title="Memex: recall memory",
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=False,
        ),
    ),
    ToolSpec(
        memex_consolidate,
        "Memex: consolidate episodes",
        ToolAnnotations(
            title="Memex: consolidate episodes",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=False,
        ),
    ),
    ToolSpec(
        memex_forget,
        "Memex: forget memory",
        ToolAnnotations(
            title="Memex: forget memory",
            read_only_hint=False,
            destructive_hint=True,
            idempotent_hint=False,
            open_world_hint=False,
        ),
    ),
    ToolSpec(
        memex_ingest_transcript,
        "Memex: ingest transcript",
        ToolAnnotations(
            title="Memex: ingest transcript",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=False,
        ),
    ),
    ToolSpec(
        memex_provenance,
        "Memex: trace provenance",
        ToolAnnotations(
            title="Memex: trace provenance",
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
    ),
    ToolSpec(
        memex_export,
        "Memex: export memories",
        ToolAnnotations(
            title="Memex: export memories",
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
    ),
    ToolSpec(
        memex_import,
        "Memex: import memories",
        ToolAnnotations(
            title="Memex: import memories",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
    ),
)


def build_server() -> Any:
    """Construct the MCP server with all eight memex tools.

    Descriptions come from OPERATION_DESCRIPTIONS in the domain (the
    shared operation contract); a KeyError here means a tool is missing
    its registry entry — tests pin the registry to the tool set. The SDK owns stdio,
    framing, and argument validation.
    """
    from mcp.server.mcpserver import MCPServer

    server = MCPServer(name="memex")
    for spec in _TOOL_SPECS:
        server.add_tool(
            spec.fn,
            name=spec.fn.__name__,
            title=spec.title,
            description=OPERATION_DESCRIPTIONS[spec.fn.__name__],
            annotations=spec.annotations,
        )
    return server


def run_server() -> None:
    build_server().run("stdio")
