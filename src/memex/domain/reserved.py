"""Reserved structural filenames shared by every memory surface.

OKF v0.2 reserves ``index.md`` (generated navigation) and ``log.md``
(optional scoped history) at every directory level. Neither is a memory
page: scans, FTS, links, export, consolidation, task recall, and the
watcher must exclude both. A pre-existing valid Memex page at either name
stays a legacy memory and blocks structural generation at that path.
"""

from __future__ import annotations

from pathlib import Path

from memex.domain.errors import FrontMatterError
from memex.domain.frontmatter import parse_front_matter

RESERVED_FILENAMES: tuple[str, ...] = ("index.md", "log.md")
RESERVED_SLUGS: tuple[str, ...] = ("index", "log")

# The generator-owned root index format: front matter limited to okf_version.
# The generator and this classifier share one definition so a version bump
# can never make fresh roots classify as legacy collisions.
OKF_VERSION = "0.2"
_OKF_ROOT_KEYS = {"okf_version"}


def _is_okf_root_shape(text: str) -> bool:
    try:
        data, _body = parse_front_matter(text)
    except FrontMatterError:
        return False
    return set(data) == _OKF_ROOT_KEYS and data.get("okf_version") == OKF_VERSION


def classify_reserved(path: Path) -> str:
    """Classify a reserved-named file for memory scans and generation.

    Returns one of:

    - ``"structural"``: generator-owned navigation or an optional OKF log
      (body-only, or the root index's ``okf_version`` front matter). Never a
      memory page and never overwritten by anything but the generator.
    - ``"legacy"``: a valid Memex page shape at a reserved name. Kept as a
      normal memory; structural generation must skip this path.
    - ``"not_reserved"``: every other case, including unparsable page-shaped
      files, which callers report through the ordinary malformed-page path.
    """
    if path.name not in RESERVED_FILENAMES:
        return "not_reserved"
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        # Undecodable reserved files stay "not_reserved" so every consumer
        # treats them as untouchable collisions, never generator-owned.
        return "not_reserved"
    if not text.startswith("---\n"):
        return "structural"
    if _is_okf_root_shape(text):
        return "structural"
    try:
        parse_front_matter(text)
    except FrontMatterError:
        return "not_reserved"
    return "legacy"


def is_structural(path: Path) -> bool:
    """True when ``path`` is a reserved-named structural file."""
    return classify_reserved(path) == "structural"
