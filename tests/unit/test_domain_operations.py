"""Parity pins: adapter wire datatypes must mirror their domain twins.

The registry in memex.domain.operations is the single contract surface
for the CLI, MCP, and any future API. These tests make "same
datatypes" a property that cannot silently drift.
"""

import dataclasses
import typing

import pytest

from memex.domain.models import (
    ConsolidationReport,
    ForgetResult,
    ProvenanceReport,
    RecallHit,
    RecallResult,
    TaskRecallResult,
    TranscriptLinkReport,
    TurnStreamEntry,
    WikiNode,
)
from memex.domain.operations import (
    OPERATION_DESCRIPTIONS,
    ConsolidateResultDict,
    ForgetResultDict,
    ProvenanceDict,
    RecallHitDict,
    RecallResultDict,
    TaskRecallResultDict,
    TranscriptReportDict,
    TurnDict,
    WriteResultDict,
    summary,
)

RESULT_TWINS = [
    (RecallResultDict, RecallResult),
    (TaskRecallResultDict, TaskRecallResult),
    (ConsolidateResultDict, ConsolidationReport),
    (ForgetResultDict, ForgetResult),
    (TranscriptReportDict, TranscriptLinkReport),
    (ProvenanceDict, ProvenanceReport),
]


def typed_keys(typed_dict: type) -> set[str]:
    return set(typing.get_type_hints(typed_dict).keys())


def model_fields(model: type) -> set[str]:
    return {field.name for field in dataclasses.fields(model)}


def test_turn_dict_mirrors_turn_stream_entry() -> None:
    assert typed_keys(TurnDict) == model_fields(TurnStreamEntry)


def test_hit_dict_mirrors_recall_hit() -> None:
    """Serialized recall hits carry exactly the domain hit fields."""
    assert typed_keys(RecallHitDict) == model_fields(RecallHit)


@pytest.mark.parametrize(("wire", "twin"), RESULT_TWINS)
def test_result_dicts_mirror_domain_reports(wire: type, twin: type) -> None:
    """Wire keys are exactly the domain fields plus the error channel."""
    assert typed_keys(wire) - {"error"} == model_fields(twin)


def test_write_result_subset_of_wiki_node() -> None:
    assert typed_keys(WriteResultDict) - {"error"} <= model_fields(WikiNode)


def test_summary_returns_first_paragraph() -> None:
    first = summary("memex_write")
    assert first.startswith("Write a memory node")
    assert "\n" not in first


def test_registry_has_all_operations() -> None:
    assert set(OPERATION_DESCRIPTIONS) == {
        "memex_write",
        "memex_recall",
        "memex_consolidate",
        "memex_forget",
        "memex_ingest_transcript",
        "memex_clear_transcripts",
        "memex_provenance",
        "memex_export",
        "memex_import",
    }
