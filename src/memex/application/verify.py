"""Deterministic verification gate (integration layer L3).

``memex verify`` converts "should have used memory" into a failing exit
code. Health checks are always run; activity evidence is optional and
only enforced when requested via require flags.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from memex.application.memory import Memex
from memex.infrastructure.wiki_store import hash_body


@dataclass(slots=True)
class VerifyReport:
    """Outcome of a deterministic verification run."""

    ok: bool
    checks: list[dict[str, object]] = field(default_factory=list)
    recall_evidence: bool = False
    write_evidence: bool = False
    warnings: list[str] = field(default_factory=list)


def _check(name: str, passed: bool, detail: str = "") -> dict[str, object]:
    return {"check": name, "ok": passed, "detail": detail}


def verify(
    memex: Memex,
    *,
    since: str | None = None,
    require_recall: bool = False,
    require_write: bool = False,
) -> VerifyReport:
    """Run health checks and optional memory-activity evidence checks."""
    checks: list[dict[str, object]] = []

    scan_errors: list[str] = []
    nodes = memex.wiki_store.scan_all(scan_errors)
    checks.append(_check("wiki-parseable", not scan_errors, f"{len(scan_errors)} malformed pages"))

    stale = 0
    for node in nodes:
        row = memex.index_manager.get(node.slug)
        if row is None or str(row["content_hash"]) != hash_body(node.body):
            stale += 1
    checks.append(_check("index-fresh", stale == 0, f"{stale} stale or missing rows"))

    broken: list[str] = []
    for node in nodes:
        broken.extend(memex.link_manager.validate_links(node.slug))
    checks.append(_check("links-resolve", not broken, f"{len(broken)} broken links"))

    warnings: list[str] = []
    recall_evidence = False
    write_evidence = False
    from memex.infrastructure.run_log import read_runs, zero_yield_streak

    streak = zero_yield_streak(read_runs(memex.data_dir))
    if streak >= 3:
        warnings.append(f"{streak} consecutive zero-yield consolidations")
    if since is not None:
        for slug in memex.index_manager.get_all_slugs():
            row = memex.index_manager.get(slug)
            if row is not None and row["last_access"] and str(row["last_access"]) >= since:
                recall_evidence = True
                break
        write_evidence = any(node.updated >= since for node in nodes)
        if not recall_evidence:
            warnings.append(f"no recall activity recorded since {since}")
        if not write_evidence:
            warnings.append(f"no memory writes since {since}")

    ok = all(check["ok"] for check in checks)
    if require_recall and not recall_evidence:
        ok = False
    if require_write and not write_evidence:
        ok = False
    return VerifyReport(
        ok=ok,
        checks=checks,
        recall_evidence=recall_evidence,
        write_evidence=write_evidence,
        warnings=warnings,
    )
