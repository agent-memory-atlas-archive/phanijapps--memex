"""Paired measurement of the production ranker on one realistic store.

Run once per source tree (a clean checkout, then the same checkout with
candidate.patch applied) with that tree first on PYTHONPATH and MEMEX_DATA_DIR
pointing at an empty guard directory outside every store:

    PYTHONPATH=<tree>/src:<tree> python grid.py --root <empty dir>

The two lines it prints feed AC-0008 and AC-0009 in spec.md. The store is
generated inside --root, so both trees measure identical pages and queries.
"""

import argparse
from pathlib import Path

from eval.realistic import RealisticCorpusGenerator
from eval.selection import _quality_metrics, _run_candidate_pair
from memex.infrastructure.search.bm25_retriever import BM25Retriever


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="empty directory for the store")
    parser.add_argument("--size", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--top-k", type=int, default=10)
    args = parser.parse_args()

    snapshot = args.root / "snapshot"
    snapshot.mkdir(parents=True)
    corpus = RealisticCorpusGenerator(snapshot, seed=args.seed).generate(args.size)

    # One FTS5 query per recall means strict AND matched; a second one is the OR fallback.
    ranked_queries = 0
    execute = BM25Retriever._execute_ranked_query

    def counting_execute(self: BM25Retriever, *args: object, **kwargs: object) -> object:
        nonlocal ranked_queries
        ranked_queries += 1
        return execute(self, *args, **kwargs)

    BM25Retriever._execute_ranked_query = counting_execute  # type: ignore[method-assign, assignment]
    measured = _run_candidate_pair(
        name="semantic-and-fallback-fts5",
        snapshot_dir=snapshot,
        data_dir=args.root / "data",
        corpus=corpus,
        top_k=args.top_k,
    )
    metrics = _quality_metrics(measured, {args.size: measured.summary.p99_ms})
    positives = sum(1 for query in corpus.queries if not query.negative)
    recall = metrics.recall_at_10
    print(
        f"queries={len(corpus.queries)} positive={positives} "
        f"R@10 all={recall['overall']:.4f} easy={recall['easy']:.4f} "
        f"medium={recall['medium']:.4f} hard={metrics.hard_recall_at_10:.4f} "
        f"hardMRR={metrics.hard_mrr:.4f}"
    )
    print(
        f"tokens_per_correct_hard={metrics.tokens_per_correct_hard_query:.2f} "
        f"p99_ms={measured.summary.p99_ms:.2f} "
        f"or_fallbacks={ranked_queries - len(corpus.queries)}"
    )


if __name__ == "__main__":
    main()
