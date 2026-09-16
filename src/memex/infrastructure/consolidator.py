"""LLM-driven wiki consolidation (spec §7 Utility 5, §11 prompt verbatim)."""

from __future__ import annotations

import json
import logging
import re

from memex.application.ports import LLMClient
from memex.domain.errors import LLMError
from memex.domain.models import (
    NON_EPISODE_TYPES,
    ConsolidateInput,
    ConsolidationReport,
    WikiNode,
    WriteInput,
)
from memex.infrastructure.config import MemexConfig
from memex.infrastructure.index_manager import IndexManager
from memex.infrastructure.link_manager import LinkManager
from memex.infrastructure.wiki_store import WikiStore

logger = logging.getLogger("memex")

SYSTEM_PROMPT = """You are a memory consolidation engine. Your task is to read session episode
records and produce new memory nodes that capture what the agent and user
decided, agreed on, or discovered during the session.

You must output valid JSON matching the schema below. No markdown code fences,
no explanations, no preamble. Just the JSON array."""

USER_PROMPT_TEMPLATE = """## TASK
Analyze the episode nodes below and create new entity, preference, procedure,
and/or summary nodes that should be permanently stored in the wiki memory.

## RULES
1. Create a node ONLY if the episode contains a non-obvious, durable fact,
   preference, procedure, or insight worth remembering across sessions.
2. Do NOT create a node for ephemeral, one-off, or obvious facts.
3. Each node title must be descriptive and kebab-case-friendly (e.g.,
   "user-prefers-ruff-over-flake8", "project-tooling-stack").
4. Use importance 0.8-1.0 for critical facts (preferences, hard rules).
   Use 0.5-0.7 for useful context.
5. Include [[wiki-link]] references to existing nodes where relevant.
   Only link to nodes listed in "Existing nodes in the knowledge base" below.
6. Node bodies should be 2-5 sentences. Be specific.
7. tags should be lowercase, kebab-case: ["preference", "python", "tooling"]

## OUTPUT FORMAT
Return a JSON array of node objects. Each object:
{{
  "type": "entity" | "preference" | "procedure" | "summary",
  "title": "kebab-case-title",
  "body": "2-5 sentence description. May include [[wiki-link]] references.",
  "tags": ["tag1", "tag2"],
  "importance": 0.0-1.0,
  "links": ["existing-node-slug"]
}}

## EXISTING NODES IN THE KNOWLEDGE BASE
{existing_nodes}

## EPISODE NODES TO PROCESS
{episode_nodes}

## OUTPUT"""

_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")
_BODY_EXCERPT = 200


def _format_existing(nodes: list[WikiNode]) -> str:
    lines = []
    for node in nodes:
        excerpt = node.body[:_BODY_EXCERPT].replace("\n", " ")
        lines.append(f"- [{node.type}] {node.slug}: {excerpt}")
    return "\n".join(lines) if lines else "(none)"


def _format_episodes(episodes: list[WikiNode]) -> str:
    blocks = []
    for episode in episodes:
        header = f"### episode {episode.slug} (session_id: {episode.session_id})"
        blocks.append(f"{header}\n\n{episode.body}")
    return "\n\n".join(blocks) if blocks else "(none)"


class WikiConsolidator:
    """Reads episodes, calls the LLM with the §11 prompt, writes nodes."""

    def __init__(
        self,
        wiki_store: WikiStore,
        index_mgr: IndexManager,
        link_mgr: LinkManager,
        llm_client: LLMClient,
        config: MemexConfig,
    ) -> None:
        self._store = wiki_store
        self._index = index_mgr
        self._links = link_mgr
        self._llm = llm_client
        self._config = config
        self._approval = config.governance.approval

    def consolidate(self, input: ConsolidateInput) -> ConsolidationReport:
        episodes = self._select_episodes(input)
        existing = [node for node in self._store.list() if node.type in NON_EPISODE_TYPES]
        prompt = self._build_prompt(existing, episodes)

        report = ConsolidationReport(
            mode=input.mode,
            episodes_processed=len(episodes),
            nodes_created=[],
            nodes_updated=[],
            links_added=0,
            llm_calls=0,
            llm_prompt_tokens=0,
            llm_completion_tokens=0,
            dry_run=input.mode == "dry-run",
        )
        if not episodes:
            return report

        try:
            response = self._llm.complete(
                SYSTEM_PROMPT, prompt, max_tokens=self._config.llm.max_tokens
            )
        except LLMError:
            logger.warning("operation=consolidate status=llm-error episodes=%d", len(episodes))
            return report
        report.llm_calls = 1
        report.llm_prompt_tokens = response.prompt_tokens
        report.llm_completion_tokens = response.completion_tokens

        for candidate in self._parse_nodes(response.text):
            report.nodes_created.append(candidate)
            if report.dry_run:
                continue
            self._store_node(candidate, report)
        return report

    def _select_episodes(self, input: ConsolidateInput) -> list[WikiNode]:
        if input.episode_ids:
            episodes = []
            for slug in input.episode_ids:
                node = self._store.read(slug)
                if node is None or node.type != "episode":
                    raise ValueError(f"not an episode node: {slug!r}")
                episodes.append(node)
            return episodes
        episodes = self._store.list("episode")
        episodes.sort(key=lambda node: node.created, reverse=True)
        return episodes[: input.max_episodes]

    def _build_prompt(self, existing: list[WikiNode], episodes: list[WikiNode]) -> str:
        return USER_PROMPT_TEMPLATE.format(
            existing_nodes=_format_existing(existing),
            episode_nodes=_format_episodes(episodes),
        )

    def _parse_nodes(self, text: str) -> list[WriteInput]:
        cleaned = _FENCE.sub("", text.strip())
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("operation=consolidate status=unparseable-llm-output")
            return []
        if not isinstance(data, list):
            return []
        candidates: list[WriteInput] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                candidates.append(
                    WriteInput(
                        type=str(item.get("type", "")),
                        title=str(item.get("title", "")),
                        body=str(item.get("body", "")),
                        tags=[str(tag) for tag in item.get("tags", [])],
                        importance=float(item.get("importance", 0.5)),
                        links=[str(link) for link in item.get("links", [])],
                    )
                )
            except (ValueError, TypeError):
                logger.warning("operation=consolidate status=invalid-node-skipped")
        return candidates

    def _store_node(self, candidate: WriteInput, report: ConsolidationReport) -> None:
        node = WikiNode(
            type=candidate.type,
            title=candidate.title,
            body=candidate.body,
            id="",
            tags=candidate.tags,
            importance=candidate.importance,
            links=candidate.links,
            status="pending" if self._approval == "manual" else "active",
            source="consolidation",
            harness=self._config.llm.provider,
        )
        updating = bool(node.slug) and self._store.exists(node.slug)
        stored = self._store.write(node)
        self._index.update_record(stored)
        links = self._links.sync_node(stored)
        report.links_added += len(links)
        if updating:
            report.nodes_updated.append(stored.slug)
