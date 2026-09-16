"""Command-line interface for all memex operations (spec §7 Utility 10)."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from memex import Memex, __version__
from memex.application.context_injection import build_injection
from memex.application.dto import to_jsonable
from memex.application.verify import verify as run_verify
from memex.domain.errors import MemexError
from memex.domain.models import (
    ConsolidateInput,
    IngestTranscriptInput,
    TurnStreamEntry,
    WriteInput,
)
from memex.domain.operations import summary
from memex.infrastructure.config import ConfigLoader
from memex.infrastructure.harness_installer import (
    SUPPORTED,
    default_marketplace,
    install_harness,
)
from memex.infrastructure.harness_transcripts import (
    HARNESSES,
    parse_transcript,
    read_transcript_turns,
    suggest_session_id,
)
from memex.infrastructure.workspace_context import session_query

_SESSION_ID_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="memex", description="Filesystem wiki memory harness")
    parser.add_argument("--version", action="version", version=f"memex {__version__}")
    parser.add_argument("--data-dir", type=Path, default=None, help="Override the data directory")
    sub = parser.add_subparsers(dest="command", required=True)

    write = sub.add_parser("write", help=summary("memex_write"))
    write.add_argument(
        "--type", required=True, choices=["entity", "preference", "procedure", "summary", "episode"]
    )
    write.add_argument("--title", required=True)
    write.add_argument("--body", required=True)
    write.add_argument("--tags", default="", help="Comma-separated tags")
    write.add_argument("--importance", type=float, default=0.5)
    write.add_argument("--links", default="", help="Comma-separated slugs")
    write.add_argument("--session-id", default=None)
    write.add_argument("--expires-at", default=None)
    write.add_argument("--valid-from", default=None)
    write.add_argument("--valid-to", default=None)

    recall = sub.add_parser("recall", help=summary("memex_recall"))
    recall.add_argument("query")
    recall.add_argument("--top-k", type=int, default=None)
    recall.add_argument("--type", default=None)
    recall.add_argument("--tag", action="append", default=None)
    recall.add_argument("--include-expired", action="store_true")
    recall.add_argument("--include-inactive", action="store_true")
    recall.add_argument("--max-tokens", type=int, default=None)

    consolidate = sub.add_parser("consolidate", help=summary("memex_consolidate"))
    consolidate.add_argument("--mode", choices=["full", "dry-run"], default="full")
    consolidate.add_argument("--max-episodes", type=int, default=10)

    forget = sub.add_parser("forget", help=summary("memex_forget"))
    forget.add_argument("slug")
    forget.add_argument("--mode", choices=["hard", "soft", "decay", "archive"], default="hard")
    forget.add_argument("--valid-to", default=None)

    ingest = sub.add_parser("ingest-transcript", help=summary("memex_ingest_transcript"))
    ingest.add_argument("--session-id", required=True)
    ingest.add_argument("--turns-file", type=Path, required=True)
    ingest.add_argument("--overwrite", action="store_true")

    rebuild = sub.add_parser("rebuild-index", help="Rebuild the secondary index from the wiki")
    rebuild.add_argument("--force", action="store_true")

    backup = sub.add_parser("backup", help="Archive wiki, transcripts, and index")
    backup.add_argument("--output", type=Path, required=True)
    backup.add_argument("--no-mem-db", action="store_true")

    restore = sub.add_parser("restore", help="Restore from an archive")
    restore.add_argument("--input", type=Path, required=True)

    export = sub.add_parser("export", help=summary("memex_export"))
    export.add_argument("--output", type=Path, default=None)

    import_cmd = sub.add_parser("import", help=summary("memex_import"))
    import_cmd.add_argument("--input", type=Path, required=True)

    approve_cmd = sub.add_parser("approve", help="Approve a pending page (flip status to active)")
    approve_cmd.add_argument("slug")

    merge_cmd = sub.add_parser(
        "merge", help="Merge source page into target; source becomes superseded"
    )
    merge_cmd.add_argument("target")
    merge_cmd.add_argument("source")

    sub.add_parser("info", help="Show data directory and index statistics")

    watch = sub.add_parser("watch", help="Poll for external wiki edits and re-index")
    watch.add_argument("--poll-interval", type=int, default=60)

    sub.add_parser("serve-mcp", help="Run the stdio MCP server")

    verify_cmd = sub.add_parser(
        "verify", help="Deterministic gate: memory health and activity evidence"
    )
    verify_cmd.add_argument("--since", default=None, help="ISO8601 cutoff for activity evidence")
    verify_cmd.add_argument("--require-recall", action="store_true")
    verify_cmd.add_argument("--require-write", action="store_true")

    install = sub.add_parser(
        "install", help="Install a harness adapter (claude, codex, pi, copilot, custom)"
    )  # MCP server registration is included by default; --no-mcp skips it
    install.add_argument("harness", nargs="?", choices=list(SUPPORTED))
    install.add_argument(
        "--from",
        dest="marketplace",
        type=Path,
        default=None,
        help="Marketplace directory (default: bundled, then ./marketplace)",
    )
    install.add_argument(
        "--home", type=Path, default=None, help="Override HOME for install targets (testing)"
    )
    install.add_argument(
        "--no-mcp",
        action="store_true",
        help="Skip MCP server registration (hooks/adapters only)",
    )

    harness = sub.add_parser("harness", help="Harness integration management (alias of install)")
    harness_sub = harness.add_subparsers(dest="harness_command", required=True)
    harness_install = harness_sub.add_parser("install", help="Install a harness adapter")
    harness_install.add_argument("name", choices=list(SUPPORTED))
    harness_install.add_argument(
        "--from",
        dest="marketplace",
        type=Path,
        default=Path("marketplace"),
        help="Marketplace directory (default: ./marketplace)",
    )
    harness_install.add_argument(
        "--home", type=Path, default=None, help="Override HOME for install targets (testing)"
    )

    hook = sub.add_parser(
        "hook", help="Harness lifecycle hooks: context injection and transcript capture"
    )
    hook_sub = hook.add_subparsers(dest="hook_command", required=True)

    hook_start = hook_sub.add_parser(
        "session-start", help="Emit a memory context block for session start"
    )
    hook_start.add_argument("--query", default=None, help="Recall query (default: git context)")
    hook_start.add_argument("--top-k", type=int, default=5)

    hook_prompt = hook_sub.add_parser(
        "prompt", help="Recall on a prompt (stdin: raw text or JSON with a prompt key)"
    )
    hook_prompt.add_argument("--top-k", type=int, default=5)
    hook_prompt.add_argument(
        "--prompt", default=None, help="Prompt text directly (overrides stdin)"
    )

    hook_transcript = hook_sub.add_parser(
        "transcript", help="Ingest a harness-native session file as a transcript"
    )
    hook_transcript.add_argument("--harness", required=True, choices=list(HARNESSES))
    hook_transcript.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Session file; when omitted, read transcript_path from stdin JSON",
    )
    hook_transcript.add_argument("--session-id", default=None)
    hook_transcript.add_argument(
        "--no-overwrite", action="store_true", help="Fail quietly if already ingested"
    )
    hook_transcript.add_argument(
        "--consolidate",
        action="store_true",
        help="Distill the fresh episode via LLM after capture "
        "(also enabled by MEMEX_AUTO_CONSOLIDATE=1)",
    )

    return parser


def _csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _prompt_from_stdin() -> str:
    """Raw prompt text, or the prompt field of a hook JSON payload."""
    import sys

    if sys.stdin is None or sys.stdin.isatty():
        return ""
    raw = sys.stdin.read().strip()
    if not raw:
        return ""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if isinstance(payload, dict) and isinstance(payload.get("prompt"), str):
        prompt: str = payload["prompt"]
        return prompt
    return raw


def _load_turns(path: Path) -> list[TurnStreamEntry]:
    """Turns from a JSONL file; session-header lines are skipped."""
    turns: list[TurnStreamEntry] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path.name}:{line_number}: {exc}") from exc
        if not isinstance(entry, dict) or "role" not in entry:
            continue
        try:
            turns.append(TurnStreamEntry.from_dict(entry))
        except ValueError as exc:
            raise ValueError(f"{path.name}:{line_number}: {exc}") from exc
    return turns


def _make_memex(args: argparse.Namespace) -> Memex:
    data_dir = args.data_dir.expanduser() if args.data_dir is not None else None
    return Memex(ConfigLoader().load(data_dir=data_dir))


def _run_install(args: argparse.Namespace) -> int:
    name = args.harness if args.command == "install" else args.name
    if name is None:
        name = _pick_harness()
        if name is None:
            return 1
    marketplace = (
        None if name == "custom" else default_marketplace(getattr(args, "marketplace", None))
    )
    home = args.home if args.home is not None else Path.home()
    try:
        report = install_harness(name, marketplace or Path("."), home=home, project=Path.cwd())
    except FileNotFoundError as exc:
        print(f"memex: {exc}", file=sys.stderr)
        return 1
    _emit(
        {
            "harness": report.harness,
            "files_written": report.files_written,
            "files_merged": report.files_merged,
            "notes": report.notes,
        }
    )
    return 0


def _pick_harness() -> str | None:
    """Interactive picker when no harness is named."""
    print("Install memex for which harness?")
    for index, option in enumerate(SUPPORTED, start=1):
        label = {"custom": "custom — initialize ~/.memex only (plain LLM config)"}.get(
            option, option
        )
        print(f"  {index}. {label}")
    try:
        choice = input("Choice [1-5]: ").strip()
    except EOFError:
        return None
    if choice.isdigit() and 1 <= int(choice) <= len(SUPPORTED):
        return SUPPORTED[int(choice) - 1]
    print("memex: invalid choice", file=sys.stderr)
    return None


def _load_turn_usage(meta_path: Path) -> dict[int, dict[str, int]]:
    """Per-turn usage from an existing meta.json, keyed by turn number."""
    if not meta_path.exists():
        return {}
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    entries = meta.get("turn_token_usage")
    if not isinstance(entries, list):
        return {}
    usage: dict[int, dict[str, int]] = {}
    for entry in entries:
        if (
            isinstance(entry, dict)
            and isinstance(entry.get("turn"), int)
            and isinstance(entry.get("usage"), dict)
        ):
            usage[entry["turn"]] = {
                str(k): v for k, v in entry["usage"].items() if isinstance(v, int)
            }
    return usage


def _merge_turns(
    old: list[TurnStreamEntry],
    new: list[TurnStreamEntry],
    old_usage: dict[int, dict[str, int]] | None = None,
) -> list[TurnStreamEntry]:
    """Compaction-safe capture merge for repeated checkpoints.

    Normal growth: the new parse extends the old one, so it wins. After
    a compaction boundary (or a fresh rollout for a resumed session) the
    new parse may be shorter or diverge: keep earlier turns and append
    only unseen later ones. Turn numbers are re-assigned sequentially.
    """
    if len(new) >= len(old) and new[: len(old)] == old:
        return new

    def key(turn: TurnStreamEntry) -> tuple[str, str, str]:
        return (turn.role, turn.content, turn.result or "")

    seen = {key(turn) for turn in old}
    merged = list(old) + [turn for turn in new if key(turn) not in seen]
    # Preserve usage from the previous meta sidecar for turns whose new
    # parse carries none (e.g. pre-compaction turns in a fresh rollout);
    # positions are stable, so turn numbers key exactly.
    if old_usage:
        for position, turn in enumerate(merged, start=1):
            if turn.token_usage is None and position in old_usage:
                turn.token_usage = old_usage[position]
    return [
        TurnStreamEntry(
            role=turn.role,
            content=turn.content,
            turn=number,
            ts=turn.ts,
            tool_name=turn.tool_name,
            result=turn.result,
            query=turn.query,
            token_usage=turn.token_usage,
        )
        for number, turn in enumerate(merged, start=1)
    ]


def _transcript_path_from_stdin() -> Path | None:
    """Extract a session file path from a hook JSON payload on stdin."""
    if sys.stdin is None or sys.stdin.isatty():
        return None
    raw = sys.stdin.read().strip()
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    for key in ("transcript_path", "session_transcript", "rollout_path", "rollout-path"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return Path(value)
    return None


def _run_hook(args: argparse.Namespace) -> int:
    """Hook commands are latency-sensitive: recall, print, exit."""
    if args.hook_command == "transcript":
        return _hook_transcript(args)

    memex = _make_memex(args)
    try:
        if args.hook_command == "session-start":
            query = args.query or session_query(Path.cwd())
            block = build_injection(memex, query, top_k=args.top_k)
            if block:
                print(block)
            return 0
        if args.hook_command == "prompt":
            prompt = args.prompt if args.prompt is not None else _prompt_from_stdin()
            if not prompt:
                return 0
            block = build_injection(memex, prompt, top_k=args.top_k)
            if block:
                print(block)
            return 0
        raise ValueError(f"unknown hook command: {args.hook_command}")
    finally:
        memex.close()


def _hook_transcript(args: argparse.Namespace) -> int:
    path = args.path or _transcript_path_from_stdin()
    if path is None:
        print("memex: no transcript path given or found on stdin", file=sys.stderr)
        return 1
    if not path.exists():
        print(f"memex: transcript not found: {path}", file=sys.stderr)
        return 1
    parsed = parse_transcript(args.harness, path)
    turns = parsed.turns
    session_id = args.session_id or (
        parsed.header.session_id if parsed.header else suggest_session_id(args.harness, path)
    )
    # session ids must be filename-safe; codex ids already satisfy the charset
    session_id = _SESSION_ID_CHARS.sub("-", session_id).strip("-.")[:80] or suggest_session_id(
        args.harness, path
    )

    memex = _make_memex(args)
    try:
        existing_path = memex.data_dir / "transcripts" / f"{session_id}.jsonl"
        old_usage = _load_turn_usage(memex.data_dir / "transcripts" / f"{session_id}.meta.json")
        if existing_path.exists():
            turns = _merge_turns(read_transcript_turns(existing_path), turns, old_usage=old_usage)
        report = memex.ingest_transcript(
            IngestTranscriptInput(
                session_id=session_id,
                turns=turns,
                header=parsed.header,
                token_usage=parsed.session_usage,
            ),
            overwrite=not args.no_overwrite,
        )
    except FileExistsError:
        print(f"memex: transcript already ingested: {session_id}", file=sys.stderr)
        return 0

    result: dict[str, object] = {
        "session_id": report.session_id,
        "episode_node": report.episode_node,
        "turn_count": report.turn_count,
        "harness": args.harness,
    }
    auto = os.environ.get("MEMEX_AUTO_CONSOLIDATE") == "1"
    if args.consolidate or auto:
        result["consolidation"] = _consolidate_episode(memex, report.episode_node)
    memex.close()
    _emit(result)
    return 0


def _consolidate_episode(memex: Memex, episode_slug: str) -> dict[str, object]:
    """Best-effort distillation of one fresh episode; never fails the hook."""
    try:
        report = memex.consolidate(ConsolidateInput(episode_ids=[episode_slug]))
        return {
            "llm_calls": report.llm_calls,
            "nodes_created": len(report.nodes_created),
            "nodes_updated": len(report.nodes_updated),
        }
    except (MemexError, ValueError) as exc:
        return {"requested": True, "error": str(exc)}


def _emit(payload: object) -> None:
    print(json.dumps(to_jsonable(payload), indent=2))


def _run(args: argparse.Namespace) -> int:
    if args.command == "serve-mcp":
        from memex.mcp_server import run_server

        run_server()
        return 0

    if args.command == "hook":
        return _run_hook(args)

    if args.command in ("harness", "install"):
        return _run_install(args)

    memex = _make_memex(args)
    try:
        if args.command == "write":
            node = memex.write(
                WriteInput(
                    type=args.type,
                    title=args.title,
                    body=args.body,
                    tags=_csv(args.tags),
                    importance=args.importance,
                    links=_csv(args.links),
                    session_id=args.session_id,
                    expires_at=args.expires_at,
                    valid_from=args.valid_from,
                    valid_to=args.valid_to,
                )
            )
            _emit({"slug": node.slug, "file_path": node.file_path})
        elif args.command == "recall":
            _emit(
                memex.recall(
                    args.query,
                    top_k=args.top_k,
                    node_type=args.type,
                    tags=args.tag,
                    include_expired=args.include_expired,
                    include_inactive=args.include_inactive,
                    max_tokens=args.max_tokens,
                )
            )
        elif args.command == "consolidate":
            _emit(
                memex.consolidate(ConsolidateInput(mode=args.mode, max_episodes=args.max_episodes))
            )
        elif args.command == "forget":
            _emit(memex.forget(args.slug, mode=args.mode, valid_to=args.valid_to))
        elif args.command == "ingest-transcript":
            _emit(
                memex.ingest_transcript(
                    IngestTranscriptInput(
                        session_id=args.session_id, turns=_load_turns(args.turns_file)
                    ),
                    overwrite=args.overwrite,
                )
            )
        elif args.command == "rebuild-index":
            _emit(memex.rebuild_index(force=args.force))
        elif args.command == "backup":
            _emit(memex.backup(args.output, include_mem_db=not args.no_mem_db))
        elif args.command == "restore":
            _emit(memex.restore(args.input))
        elif args.command == "export":
            _emit(memex.import_export.export(args.output))
        elif args.command == "import":
            _emit(memex.import_export.import_file(args.input))
        elif args.command == "verify":
            report = run_verify(
                memex,
                since=args.since,
                require_recall=args.require_recall,
                require_write=args.require_write,
            )
            _emit(report)
            return 0 if report.ok else 1
        elif args.command == "info":
            _emit(_info(memex))
        elif args.command == "watch":
            from memex.infrastructure.watcher import IndexWatcher

            watcher = IndexWatcher(
                memex.wiki_store.wiki_dir,
                memex.index_manager,
                memex.wiki_store,
                poll_interval=args.poll_interval,
            )
            watcher.start_polling()
            print("watching for wiki edits; press Ctrl-C to stop", file=sys.stderr)
            try:
                while True:
                    time.sleep(3600)
            except KeyboardInterrupt:
                watcher.stop_polling()
        return 0
    finally:
        if args.command != "watch":
            memex.close()


def _info(memex: Memex) -> dict[str, object]:
    counts = {
        node_type: len(memex.wiki_store.list(node_type))
        for node_type in ("entity", "preference", "procedure", "summary", "episode")
    }
    return {
        "version": __version__,
        "data_dir": str(memex.data_dir),
        "wiki_file_counts": counts,
        "index_total": memex.index_manager.count(),
        "schema_version": memex.index_manager.get_meta("schema_version"),
        "last_index_rebuild": memex.index_manager.get_meta("last_index_rebuild"),
        "llm_provider": memex.config.llm.provider,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return _run(args)
    except (MemexError, ValueError, TypeError, FileNotFoundError, FileExistsError) as exc:
        print(f"memex: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
