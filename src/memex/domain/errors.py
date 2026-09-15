"""Memex error hierarchy.

All memex-specific failures derive from :class:`MemexError` so callers can
catch the family with one clause. Error messages must stay actionable and
must never embed memory contents or credentials.
"""

from __future__ import annotations


class MemexError(Exception):
    """Base class for all memex failures."""


class ConfigError(MemexError):
    """memex.toml is missing required values or contains invalid ones."""


class WikiStoreError(MemexError):
    """A wiki page could not be read, parsed, or written."""


class FrontMatterError(WikiStoreError):
    """YAML front matter does not match the documented format."""


class IndexManagerError(MemexError):
    """The secondary SQLite index could not be updated or queried."""


class LLMError(MemexError):
    """An LLM API call failed or returned unusable output."""


class BackupError(MemexError):
    """A backup archive could not be created, verified, or restored."""
