"""Command-line entry for the memory-layer retrieval evaluation.

Runs from the repo root:

    uv run python -m eval.run corpus --realistic --size 10000 --seed 42
    uv run python -m eval.run retrieval --realistic --size 10000 --top-k 10
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from eval.corpus import CorpusResult
from eval.runner import format_report, run_retrieval_eval
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
        "--data-dir", default=None, help="Eval store location (default ~/.memex-eval)"
    )
    retrieval_cmd.add_argument(
        "--realistic", action="store_true", help="Evaluate against the real-world-shaped corpus"
    )
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


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    eval_dir = Path(getattr(args, "data_dir", None) or "~/.memex-eval").expanduser()

    if args.command == "corpus":
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

    corpus = _generate_corpus(eval_dir, size=args.size, seed=args.seed, realistic=args.realistic)
    memex = Memex(MemexConfig(data_dir=eval_dir))
    try:
        report = run_retrieval_eval(memex, corpus, top_k=args.top_k)
    finally:
        memex.close()
    print(format_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
