"""The Memex facade: the single public API surface (spec §7 Utility core)."""

from __future__ import annotations

import time
from pathlib import Path

from memex.application.decay import RecencyDecay
from memex.application.ports import LLMClient
from memex.domain.errors import LLMError
from memex.domain.models import (
    FORGET_MODES,
    BackupReport,
    ConsolidateInput,
    ConsolidationReport,
    ForgetResult,
    IngestTranscriptInput,
    ProvenanceReport,
    RebuildIndexReport,
    RecallResult,
    RestoreReport,
    SessionSummary,
    TranscriptLinkReport,
    WikiNode,
    WriteInput,
    utc_now_iso,
)
from memex.infrastructure.backup import BackupRestore
from memex.infrastructure.bm25_retriever import BM25Retriever
from memex.infrastructure.config import ConfigLoader, MemexConfig
from memex.infrastructure.consolidator import WikiConsolidator
from memex.infrastructure.import_export import ImportExport
from memex.infrastructure.index_manager import IndexManager
from memex.infrastructure.link_manager import LinkManager
from memex.infrastructure.llm_clients import client_from_config
from memex.infrastructure.logging import setup_logging
from memex.infrastructure.transcript_hook import TranscriptHook
from memex.infrastructure.wiki_store import WikiStore, hash_body


class Memex:
    """Composes storage, index, retrieval, transcripts, and maintenance.

    The wiki filesystem is the source of truth; every index mutation is
    paired with the file write that justifies it.
    """

    def __init__(self, config: MemexConfig | None = None) -> None:
        self.config = config if config is not None else ConfigLoader().load()
        self.data_dir = self.config.data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logger = setup_logging(self.config.logging)
        self._llm: LLMClient | None = None
        self._consolidator: WikiConsolidator | None = None
        self._open_storage()

    def _open_storage(self) -> None:
        self.wiki_store = WikiStore(self.data_dir, slug_algo=self.config.wiki.slug_algo)
        self.index_manager = IndexManager(self.config.db_path)
        self.link_manager = LinkManager(self.index_manager.connection, self.wiki_store.wiki_dir)
        self.retriever = BM25Retriever(
            self.config.db_path,
            k1=self.config.bm25.k1,
            b=self.config.bm25.b,
            default_top_k=self.config.bm25.default_top_k,
        )
        self.transcript_hook = TranscriptHook(
            self.data_dir, self.wiki_store, self.index_manager, self.link_manager
        )
        self.backup_restore = BackupRestore(self.data_dir, self.config.db_path)
        self.import_export = ImportExport(self.wiki_store, self.index_manager, self.link_manager)

    def close(self) -> None:
        self.retriever.close()
        self.index_manager.close()

    def write(self, input: WriteInput) -> WikiNode:
        """Persist a memory node and update the index and link graph.

        A new node gets a derived, collision-suffixed slug (``ruff-linter``,
        ``ruff-linter-2``); writing an existing slug updates it, preserving
        ``id``, ``created``, ``access_count``, and ``last_access`` from the
        stored page. The Markdown file is written atomically (temp + rename).

        Side effects: writes ``wiki/{type}/{slug}.md``, upserts the row in
        ``mem.db``, and replaces the node's outgoing ``wiki_links`` entries.

        Args:
            input: Node fields; ``type`` must be one of the five node types
                and ``session_id`` is required for episodes.

        Returns:
            The stored node with ``id``, ``slug``, ``file_path``, timestamps,
            and ``content_hash`` assigned.

        Raises:
            ValueError: Body exceeds ``wiki.max_body_chars``, or ``input``
                fails field validation.
            WikiStoreError: The wiki directory is not writable.
        """
        if len(input.body) > self.config.wiki.max_body_chars:
            raise ValueError(
                f"body exceeds wiki.max_body_chars ({self.config.wiki.max_body_chars})"
            )
        node = WikiNode(
            type=input.type,
            title=input.title,
            body=input.body,
            id="",
            tags=input.tags,
            importance=input.importance,
            links=input.links,
            session_id=input.session_id,
            transcript_ref=input.transcript_ref,
            expires_at=input.expires_at,
            valid_from=input.valid_from,
            valid_to=input.valid_to,
        )
        stored = self.wiki_store.write(node)
        self.index_manager.update_record(stored)
        self.link_manager.sync_node(stored)
        self.logger.info("operation=write slug=%s type=%s", stored.slug, stored.type)
        return stored

    def recall(
        self,
        query: str,
        *,
        top_k: int | None = None,
        node_type: str | None = None,
        time_range: tuple[str, str] | None = None,
        tags: list[str] | None = None,
        include_expired: bool = False,
    ) -> RecallResult:
        """BM25 search over the index; each hit records access statistics.

        The query is reduced to alphanumeric tokens joined by OR, so
        untrusted input never reaches the FTS5 MATCH parser. Hits are ordered
        by ascending BM25 score (lower is better, per SQLite FTS5). Nodes
        past ``expires_at`` or ``valid_to`` are invisible unless the caller
        opts in; this is how soft-forgetting and decay hide memories.

        Side effects: every returned hit gets ``access_count += 1`` and a
        refreshed ``last_access`` in the index. Reads never touch the files.

        Args:
            query: Free-text terms; must contain one alphanumeric token.
            top_k: Maximum hits, in [1, 100]; defaults to the configured
                ``bm25.default_top_k``.
            node_type: Restrict hits to one type, e.g. ``"preference"``.
            time_range: ``(from, to)`` ISO8601 bounds on ``updated``.
            tags: All listed tags must be present (AND semantics).
            include_expired: Also return soft-forgotten and decayed nodes.

        Returns:
            RecallResult with 1-based ranks, best first. Empty ``hits`` is a
            normal result, not an error.

        Raises:
            ValueError: Query has no searchable terms, or ``top_k`` outside
                [1, 100].
        """
        result = self.retriever.retrieve(
            query,
            top_k=top_k,
            node_type=node_type,
            time_range=time_range,
            tags=tags,
            include_expired=include_expired,
        )
        self.logger.info(
            "operation=recall hits=%d total_indexed=%d", len(result.hits), result.total_indexed
        )
        return result

    def consolidate(self, input: ConsolidateInput) -> ConsolidationReport:
        """LLM-driven consolidation of episode nodes (spec §11 prompt).

        The only operation that calls an LLM, and only when explicitly
        invoked. Episodes are selected by ``episode_ids`` or the most recent
        ``max_episodes``. LLM output is parsed as a JSON array of nodes;
        entries that fail validation are skipped, not fatal.

        In ``dry-run`` mode nothing is written; the report carries the nodes
        that would be created. On LLM API failure the operation does not
        raise: a partial report with empty ``nodes_created`` is returned and
        the error is logged.

        Side effects (``full`` mode only): writes each produced node, syncs
        its ``wiki_links``, and upserts its index row.

        Raises:
            LLMError: No API key configured for a remote provider.
            ValueError: An ``episode_ids`` entry is not an episode node.
        """
        if self._consolidator is None:
            self._consolidator = WikiConsolidator(
                self.wiki_store,
                self.index_manager,
                self.link_manager,
                self._llm_client(),
                self.config,
            )
        report = self._consolidator.consolidate(input)
        self.logger.info(
            "operation=consolidate mode=%s episodes=%d nodes=%d",
            report.mode,
            report.episodes_processed,
            len(report.nodes_created),
        )
        return report

    def forget(
        self,
        slug: str,
        *,
        mode: str = "hard",
        valid_to: str | None = None,
    ) -> ForgetResult:
        """Remove a memory: delete the page, or retire it temporally.

        ``hard`` deletes the file and purges its index row and wiki_links
        entries in both directions — irreversible. ``soft`` sets ``valid_to``
        and ``decay`` sets ``expires_at``; both keep the file and default the
        timestamp to now, and both hide the node from recall unless the
        caller passes ``include_expired=True``.

        Args:
            slug: Wiki page slug.
            mode: One of ``hard``, ``soft``, ``decay``.
            valid_to: ISO8601 UTC timestamp for soft/decay; defaults to now.

        Raises:
            FileNotFoundError: No page exists for ``slug``.
            ValueError: ``mode`` is invalid.
        """
        if mode not in FORGET_MODES:
            raise ValueError(f"mode must be one of {FORGET_MODES}, got {mode!r}")
        node = self.wiki_store.read(slug)
        if node is None:
            raise FileNotFoundError(f"no wiki page for slug: {slug!r}")

        if mode == "hard":
            self.wiki_store.delete(slug)
            self.index_manager.remove_record(slug)
            self.link_manager.remove_slug(slug)
            self.logger.info("operation=forget mode=hard slug=%s", slug)
            return ForgetResult(slug=slug, forgotten=True, mode=mode, file_path=None)

        timestamp = valid_to or utc_now_iso()
        field = "valid_to" if mode == "soft" else "expires_at"
        setattr(node, field, timestamp)
        stored = self.wiki_store.write(node)
        self.index_manager.update_record(stored)
        self.logger.info("operation=forget mode=%s slug=%s", mode, slug)
        return ForgetResult(slug=slug, forgotten=True, mode=mode, file_path=stored.file_path)

    def ingest_transcript(
        self, input: IngestTranscriptInput, *, overwrite: bool = False
    ) -> TranscriptLinkReport:
        """Store a raw transcript and link it to an episode node.

        Turn contents are stored verbatim and never logged. Side effects:
        writes ``transcripts/{session_id}.jsonl`` and ``.meta.json``, creates
        ``wiki/episodes/{session_id}.md`` with ``transcript_ref`` front
        matter, and indexes the episode.

        Args:
            input: Session turns and optional metadata; ``session_id`` is
                restricted to ``[A-Za-z0-9._-]`` (it becomes a filename).
            overwrite: Replace an existing transcript for this session.

        Raises:
            FileExistsError: A transcript for ``session_id`` already exists
                and ``overwrite`` is False.
            ValueError: ``session_id`` or a turn entry is invalid.
        """
        report = self.transcript_hook.ingest(input, overwrite=overwrite)
        self.logger.info(
            "operation=ingest_transcript session=%s turns=%d",
            input.session_id,
            report.turn_count,
        )
        return report

    def rebuild_index(self, *, force: bool = False) -> RebuildIndexReport:
        """Rescan the wiki and refresh the secondary index and link graph.

        The wiki files are the truth: index rows for deleted pages are
        removed, every node's links are re-synced, and pages whose
        front-matter ``content_hash`` went stale through external editing
        are rewritten with a fresh hash. Without ``force``, nodes whose
        stored hash matches the index are skipped; with ``force`` every
        node is re-indexed. Malformed pages are skipped and reported in
        ``errors`` — one bad hand-edit never blocks a rebuild.

        Side effects: updates ``last_index_rebuild`` and ``wiki_file_count``
        in ``index_meta``.
        """
        started = time.perf_counter()
        errors: list[str] = []
        nodes = self.wiki_store.scan_all(errors)
        known_hashes: dict[str, str] = {}
        if not force:
            for slug in self.index_manager.get_all_slugs():
                row = self.index_manager.get(slug)
                if row is not None:
                    known_hashes[str(row["slug"])] = str(row["content_hash"])

        wiki_slugs = {node.slug for node in nodes}
        for stale in set(self.index_manager.get_all_slugs()) - wiki_slugs:
            self.index_manager.remove_record(stale)

        skipped = 0
        for node in nodes:
            self.link_manager.sync_node(node)
            if node.content_hash != hash_body(node.body):
                # Externally edited page: refresh the stale front-matter hash.
                node = self.wiki_store.write(node)
            if not force and known_hashes.get(node.slug) == node.content_hash:
                skipped += 1
                continue
            self.index_manager.update_record(node)

        now = utc_now_iso()
        self.index_manager.set_meta("last_index_rebuild", now)
        self.index_manager.set_meta("wiki_file_count", str(len(nodes)))
        duration_ms = (time.perf_counter() - started) * 1000
        self.logger.info(
            "operation=rebuild_index nodes=%d skipped=%d errors=%d",
            len(nodes),
            skipped,
            len(errors),
        )
        return RebuildIndexReport(
            nodes_indexed=len(nodes) - skipped,
            nodes_skipped=skipped,
            nodes_errored=len(errors),
            duration_ms=round(duration_ms, 3),
            errors=errors,
        )

    def backup(self, output_path: Path, *, include_mem_db: bool = True) -> BackupReport:
        return self.backup_restore.backup(output_path, include_mem_db=include_mem_db)

    def restore(self, input_path: Path) -> RestoreReport:
        """Restore from an archive, then rebuild the index from the wiki.

        Existing data is never deleted: it is moved to
        ``pre-restore-{timestamp}/`` first. Archive members are validated
        (no absolute paths, traversal, or links) before extraction. Storage
        connections are closed and reopened around the swap, and the index
        is force-rebuilt, so ``index_rebuilt`` is always True on success.

        Raises:
            BackupError: Archive missing, fails verification, or contains
                unsafe members.
        """
        self.retriever.close()
        self.index_manager.close()
        report = self.backup_restore.restore(input_path)
        self._open_storage()
        self.rebuild_index(force=True)
        report.index_rebuilt = True
        self.logger.info("operation=restore warnings=%d", len(report.warnings))
        return report

    def get_provenance(self, slug: str) -> ProvenanceReport | None:
        return self.transcript_hook.get_provenance(slug)

    def list_sessions(self) -> list[SessionSummary]:
        return self.transcript_hook.list_sessions()

    def apply_decay(self, *, dry_run: bool = False) -> list[tuple[str, float, float]]:
        """Recompute importance for every node via half-life decay.

        Explicit maintenance call — decay is never applied on access.
        Returns ``(slug, old, new)`` for each node that would change; with
        ``dry_run`` the wiki files and index are left untouched.
        """
        decay = RecencyDecay(
            half_life_days=self.config.recency_decay.half_life_days,
            enabled=self.config.recency_decay.enabled,
        )
        return decay.apply_decay(self.wiki_store, self.index_manager, dry_run=dry_run)

    def _llm_client(self) -> LLMClient:
        """The consolidation client: [consolidation] overrides over [llm].

        Lets distillation run on a cheaper low-effort model than the main
        configuration without duplicating credentials.
        """
        if self._llm is None:
            llm = self.config.consolidation_llm()
            if not llm.api_key and llm.provider in ("openai", "openrouter"):
                raise LLMError("llm.api_key is required (set MEMEX_API_KEY or [llm].api_key)")
            self._llm = client_from_config(llm)
        return self._llm


__all__ = ["Memex"]
