"""Filesystem wiki memory harness.

The wiki is the filesystem: Markdown pages under ``~/.memex/wiki/`` are the
source of truth, and SQLite (``mem.db``) is a rebuildable secondary index for
BM25 retrieval and freshness tracking.
"""

from memex.application.memory import Memex
from memex.domain.errors import (
    BackupError,
    ConfigError,
    IndexManagerError,
    LLMError,
    MemexError,
    WikiStoreError,
)
from memex.domain.models import (
    BackupReport,
    ConsolidateInput,
    ConsolidationReport,
    ForgetResult,
    IngestTranscriptInput,
    ProvenanceReport,
    RebuildIndexReport,
    RecallHit,
    RecallResult,
    RestoreReport,
    SessionSummary,
    TranscriptLinkReport,
    TurnStreamEntry,
    WikiNode,
    WriteInput,
)
from memex.infrastructure.config import MemexConfig

__version__ = "0.4.0"

__all__ = [
    "BackupError",
    "BackupReport",
    "ConfigError",
    "ConsolidateInput",
    "ConsolidationReport",
    "ForgetResult",
    "IndexManagerError",
    "IngestTranscriptInput",
    "LLMError",
    "Memex",
    "MemexConfig",
    "MemexError",
    "ProvenanceReport",
    "RebuildIndexReport",
    "RecallHit",
    "RecallResult",
    "RestoreReport",
    "SessionSummary",
    "TranscriptLinkReport",
    "TurnStreamEntry",
    "WikiNode",
    "WikiStoreError",
    "WriteInput",
]
