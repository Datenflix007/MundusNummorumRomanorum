"""Offline tests for the documented OCRE NUDS/XML import pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest

from database.repository import CoinRepository
from services.ocre import (
    OCRE_FEED_URL,
    OCRE_NUDS_URL,
    OcreImportService,
    OcreParseError,
    OcreSourceAdapter,
    parse_nuds_xml,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ocre" / "ric.3.ant.1284A_as.xml"


class FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    def __init__(self, responses: dict[str, bytes]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append((url, kwargs))
        return FakeResponse(self.responses[url])


def test_parse_captured_ocre_record_preserves_canonical_fields() -> None:
    record = parse_nuds_xml(FIXTURE_PATH.read_bytes())[0]

    assert record.record_id == "ric.3.ant.1284A_as"
    assert record.canonical_uri == "http://numismatics.org/ocre/id/ric.3.ant.1284A_as"
    assert record.original_reference == "RIC III Antoninus Pius 1284A (as)"
    assert record.authority == "Antoninus Pius"
    assert record.mint == "Rome"
    assert record.date_start == 148
    assert record.date_end == 149
    assert record.obverse_legend == "AVRELIVS CAESAR ANTONINI AVG PII F"
    assert record.reverse_description == "Minerva, standing right, holding spear and leaning on shield"
    assert record.source_attribution == "American Numismatic Society"
    assert record.source_license == "http://opendatacommons.org/licenses/odbl/"
    assert record.to_coin_type_input().obverse_image_url is None


def test_parser_keeps_missing_optional_source_fields_as_none() -> None:
    minimal_record = b'''<nuds xmlns="http://nomisma.org/nuds"><control><recordId>ric.test.1</recordId></control><descMeta><typeDesc/></descMeta></nuds>'''

    record = parse_nuds_xml(minimal_record)[0]

    assert record.original_reference == "ric.test.1"
    assert record.date_start is None
    assert record.mint is None
    assert record.obverse_legend is None


def test_import_is_idempotent_and_preserves_source_metadata(tmp_path: Path) -> None:
    repository = CoinRepository(tmp_path / "catalog.sqlite")
    repository.initialize()
    records = parse_nuds_xml(FIXTURE_PATH.read_bytes())
    importer = OcreImportService(repository)

    first_report = importer.import_records([records[0].record_id], records)
    second_report = importer.import_records([records[0].record_id], records)
    stored = repository.get_coin_type_by_external_id(records[0].record_id)

    assert (first_report.imported, first_report.duplicates) == (1, 0)
    assert (second_report.imported, second_report.duplicates) == (0, 1)
    assert stored is not None
    assert stored.source_name == "Online Coins of the Roman Empire (OCRE)"
    assert stored.original_reference == records[0].original_reference


def test_adapter_fetches_only_documented_feed_and_nuds_endpoints() -> None:
    feed = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><link href="http://numismatics.org/ocre/id/ric.3.ant.1284A_as"/></entry></feed>'''
    nuds_group = (
        b'<nudsGroup xmlns="http://nomisma.org/nuds">'
        + FIXTURE_PATH.read_bytes().split(b"?>", maxsplit=1)[1]
        + b"</nudsGroup>"
    )
    session = FakeSession({OCRE_FEED_URL: feed, OCRE_NUDS_URL: nuds_group})
    adapter = OcreSourceAdapter(session=session, request_delay_seconds=0, sleeper=lambda _: None)  # type: ignore[arg-type]

    identifiers, records = adapter.fetch_pilot(limit=1)

    assert identifiers == ["ric.3.ant.1284A_as"]
    assert [record.record_id for record in records] == identifiers
    assert [call[0] for call in session.calls] == [OCRE_FEED_URL, OCRE_NUDS_URL]
    assert session.calls[1][1]["params"] == {"identifiers": "ric.3.ant.1284A_as"}


def test_parser_rejects_non_nuds_xml() -> None:
    with pytest.raises(OcreParseError):
        parse_nuds_xml(b"<not-nuds/>")
