"""Command-line entry for the memory-layer retrieval evaluation.

Runs from the repo root:

    uv run python -m eval.run corpus --realistic --size 10000 --seed 42
    uv run python -m eval.run retrieval --realistic --size 10000 --top-k 10
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from eval.corpus import CorpusResult
from eval.runner import format_report, run_retrieval_eval
from eval.selection import CANDIDATE_NAMES, EvaluationConfig, run_selection
from memex import Memex
from memex.infrastructure.config import MemexConfig


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eval.run", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    corpus_cmd = sub.add_parser("corpus", help="Generate a synthetic corpus")
    corpus_cmd.add_argument("--size", type=int, default=100)
    corpus_cmd.add_argument("--seed", type=int, default=42)
    corpus_cmd.add_argument(
        "--data-dir", default=None, help="Eval store location (default ~/.memex-eval)"
    )
    corpus_cmd.add_argument(
        "--realistic", action="store_true", help="Use real-world-shaped knowledge domains"
    )

    retrieval_cmd = sub.add_parser("retrieval", help="Run retrieval quality evaluation")
    retrieval_cmd.add_argument("--top-k", type=int, default=10)
    retrieval_cmd.add_argument("--size", type=int, default=100)
    retrieval_cmd.add_argument("--seed", type=int, default=42)
    retrieval_cmd.add_argument(
        "--data-dir",
        default=None,
        help="Empty eval store location (default: a fresh temporary directory)",
    )
    retrieval_cmd.add_argument(
        "--realistic", action="store_true", help="Evaluate against the real-world-shaped corpus"
    )
    retrieval_cmd.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="Write reproducibility metadata and metrics as JSON",
    )

    selection_cmd = sub.add_parser(
        "selection",
        help="Run paired baseline-versus-candidate retrieval selection",
    )
    selection_cmd.add_argument("--top-k", type=int, default=10)
    selection_cmd.add_argument("--size", type=int, default=100)
    selection_cmd.add_argument("--seed", type=int, default=42)
    selection_cmd.add_argument(
        "--promotion",
        action="store_true",
        help="Run the canonical seed-42/top-10 evaluation at 10K and 100K",
    )
    selection_cmd.add_argument(
        "--candidate",
        action="append",
        choices=CANDIDATE_NAMES,
        help="Candidate to evaluate; repeat for multiple (default: all)",
    )
    selection_cmd.add_argument(
        "--evidence-dir",
        type=Path,
        default=None,
        help="Empty directory where the sanitized selection report is written",
    )
    selection_cmd.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Empty root for paired stores (default: a fresh temporary directory)",
    )

    import_cmd = sub.add_parser(
        "import-gutenberg",
        help="Import a local official Project Gutenberg catalog into the committed fixture",
    )
    import_cmd.add_argument("--catalog", type=Path, required=True)
    import_cmd.add_argument("--provenance", type=Path, required=True)
    import_cmd.add_argument("--output", type=Path, required=True)
    return parser


def _generate_corpus(eval_dir: Path, *, size: int, seed: int, realistic: bool) -> CorpusResult:
    """Build the corpus and rebuild the index (same path a fresh store takes)."""
    memex = Memex(MemexConfig(data_dir=eval_dir))
    try:
        if realistic:
            from eval.realistic import RealisticCorpusGenerator

            result = RealisticCorpusGenerator(eval_dir, seed=seed).generate(size)
        else:
            from eval.corpus import CorpusGenerator

            result = CorpusGenerator(memex, seed=seed).generate(size)
        memex.rebuild_index(force=True)
    finally:
        memex.close()
    return result


def _git_state() -> tuple[str, bool | None]:
    """Return the source revision and whether tracked or untracked files differ."""
    repo_root = Path(__file__).resolve().parents[1]
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
        status = subprocess.run(
            ["git", "status", "--porcelain"],  # noqa: S607
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return "unknown", None
    return revision.stdout.strip() or "unknown", bool(status.stdout.strip())


def _assert_fresh_eval_dir(eval_dir: Path) -> None:
    """Reject contaminated stores without deleting caller-owned files."""
    if eval_dir.exists() and any(eval_dir.iterdir()):
        raise ValueError(f"retrieval eval data directory must be empty: {eval_dir}")


def _run_retrieval(args: argparse.Namespace, eval_dir: Path, *, ephemeral: bool) -> int:
    _assert_fresh_eval_dir(eval_dir)
    corpus = _generate_corpus(
        eval_dir,
        size=args.size,
        seed=args.seed,
        realistic=args.realistic,
    )
    memex = Memex(MemexConfig(data_dir=eval_dir))
    try:
        report = run_retrieval_eval(memex, corpus, top_k=args.top_k)
    finally:
        memex.close()

    print(format_report(report))
    if args.json_output is not None:
        git_commit, git_dirty = _git_state()
        payload = {
            "schema_version": 1,
            "run": {
                "created_at": datetime.now(UTC).isoformat(),
                "git_commit": git_commit,
                "git_dirty": git_dirty,
                "seed": args.seed,
                "requested_corpus_size": args.size,
                "top_k": args.top_k,
                "realistic": args.realistic,
                "data_dir": str(eval_dir),
                "ephemeral_data_dir": ephemeral,
                "ranker": {
                    "name": "sqlite-fts5-bm25",
                    "query_strategy": "or",
                    "fields": ["slug", "title", "body", "tags"],
                },
            },
            "metrics": asdict(report),
        }
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "corpus":
        eval_dir = Path(args.data_dir or "~/.memex-eval").expanduser()
        result = _generate_corpus(
            eval_dir, size=args.size, seed=args.seed, realistic=args.realistic
        )
        print(
            json.dumps(
                {
                    "memories_written": result.memories_written,
                    "queries_generated": len(result.queries),
                    "elapsed_ms": result.elapsed_ms,
                    "data_dir": str(eval_dir),
                    "domain_counts": result.domain_counts,
                }
            )
        )
        return 0

    if args.command == "selection":
        report = run_selection(
            EvaluationConfig(
                size=args.size,
                seed=args.seed,
                top_k=args.top_k,
                candidates=tuple(args.candidate) if args.candidate else CANDIDATE_NAMES,
                evidence_dir=args.evidence_dir.expanduser() if args.evidence_dir else None,
                data_root=args.data_dir.expanduser() if args.data_dir else None,
                promotion_mode=args.promotion,
            )
        )
        print(
            json.dumps(
                {
                    "schema_version": report.to_dict()["schema_version"],
                    "requested_corpus_size": report.metadata["requested_corpus_size"],
                    "query_count": report.metadata["query_count"],
                    "selected_candidate": report.selected_candidate,
                    "promotion_eligible": report.metadata["promotion_eligible"],
                    "failures": [failure.to_dict() for failure in report.failures],
                    "report_path": str(report.report_path) if report.report_path else None,
                },
                sort_keys=True,
            )
        )
        return 0

    if args.command == "import-gutenberg":
        from eval.workloads import GutenbergImportError, import_gutenberg_catalog

        try:
            source = import_gutenberg_catalog(
                catalog=args.catalog,
                provenance=args.provenance,
                output=args.output,
            )
        except GutenbergImportError as exc:
            print(json.dumps({"category": exc.category, "reason": str(exc)}), file=sys.stderr)
            return 2
        print(json.dumps(source.to_dict(), sort_keys=True))
        return 0

    if args.data_dir is not None:
        return _run_retrieval(args, Path(args.data_dir).expanduser(), ephemeral=False)
    with tempfile.TemporaryDirectory(prefix="memex-eval-") as temp_dir:
        return _run_retrieval(args, Path(temp_dir), ephemeral=True)


if __name__ == "__main__":
    sys.exit(main())
