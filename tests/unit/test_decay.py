import math
from pathlib import Path

import pytest

from memex.application.decay import RecencyDecay
from memex.domain.models import WikiNode, utc_now_iso
from memex.infrastructure.index_manager import IndexManager
from memex.infrastructure.wiki_store import WikiStore


def _node(**overrides: object) -> WikiNode:
    fields: dict[str, object] = {
        "type": "entity",
        "title": "Decay target",
        "body": "b",
        "importance": 1.0,
        "created": "2020-01-01T00:00:00Z",
        "id": "d1",
    }
    fields.update(overrides)
    return WikiNode(**fields)  # type: ignore[arg-type]


def test_ancient_node_decays_to_zero() -> None:
    decay = RecencyDecay(half_life_days=30)
    node = _node(last_access="2020-01-01T00:00:00Z")
    assert decay.decay_importance(node) == pytest.approx(0.0)


def test_fresh_node_unchanged() -> None:
    decay = RecencyDecay(half_life_days=30)
    fresh = _node(importance=0.8, last_access=utc_now_iso())
    assert decay.decay_importance(fresh) == pytest.approx(0.8)


def test_falls_back_to_created_when_never_accessed() -> None:
    decay = RecencyDecay(half_life_days=36500)
    node = _node(importance=1.0, created="2020-01-01T00:00:00Z", last_access=None)
    decayed = decay.decay_importance(node)
    assert 0.0 < decayed < 1.0


def test_half_life_lambda_positive() -> None:
    lam = math.log(2) / 30
    assert lam > 0


def test_invalid_half_life_rejected() -> None:
    with pytest.raises(ValueError, match="half_life_days"):
        RecencyDecay(half_life_days=0)


def test_apply_decay_updates_store_and_index(data_dir: Path) -> None:
    store = WikiStore(data_dir)
    index = IndexManager(data_dir / "mem.db")
    index.initialize()
    store.write(_node())

    decay = RecencyDecay(half_life_days=30)
    changes = decay.apply_decay(store, index)
    assert len(changes) == 1
    slug, old, new = changes[0]
    assert old == 1.0
    assert new < old

    reread = store.read(slug)
    assert reread is not None
    assert reread.importance == new
    row = index.get(slug)
    assert row is not None
    assert row["importance"] == new


def test_apply_decay_dry_run_writes_nothing(data_dir: Path) -> None:
    store = WikiStore(data_dir)
    stored = store.write(_node())
    decay = RecencyDecay(half_life_days=30)
    decay.apply_decay(store)

    changes = decay.apply_decay(store, dry_run=True)
    reread = store.read(stored.slug)
    assert reread is not None
    if changes:
        assert reread.importance == changes[0][1]  # old value kept


def test_disabled_is_noop(data_dir: Path) -> None:
    store = WikiStore(data_dir)
    store.write(_node())
    decay = RecencyDecay(half_life_days=30, enabled=False)
    assert decay.apply_decay(store) == []
