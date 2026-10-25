"""Offline tests for the documented OCRE NUDS/XML import pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest
import requests

from database.repository import CoinRepository
from services.ocre import (
    OCRE_FEED_URL,
    OCRE_NUDS_URL,
    OCRE_VOID_URL,
    OcreImportService,
    OcreParseError,
    OcreSourceAdapter,
    iter_rdf_record_ids,
    parse_atom_feed_page,
    parse_nuds_xml,
    parse_void_data_dump_url,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ocre" / "ric.3.ant.1284A_as.xml"


class FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size: int) -> list[bytes]:
        return [self.content[offset : offset + chunk_size] for offset in range(0, len(self.content), chunk_size)]

    def close(self) -> None:
        return None


class FakeSession:
    def __init__(self, responses: dict[str, bytes | Exception]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append((url, kwargs))
        response = self.responses[url]
        if isinstance(response, Exception):
            raise response
        return FakeResponse(response)


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


def test_incremental_import_batches_keep_completed_records_and_skip_repeats(tmp_path: Path) -> None:
    repository = CoinRepository(tmp_path / "catalog.sqlite")
    repository.initialize()
    records = parse_nuds_xml(FIXTURE_PATH.read_bytes())

    report = OcreImportService(repository).import_batches(
        [([records[0].record_id], records), ([records[0].record_id], records)]
    )

    assert (report.discovered, report.parsed, report.imported, report.duplicates) == (2, 2, 1, 1)


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


def test_full_catalog_discovery_follows_the_documented_atom_feed_in_batches() -> None:
    feed = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><link href="http://numismatics.org/ocre/id/ric.2.ves.1" /></entry><entry><link href="http://numismatics.org/ocre/id/ric.2.ves.2" /></entry></feed>'''
    session = FakeSession({OCRE_FEED_URL: feed})
    adapter = OcreSourceAdapter(session=session, request_delay_seconds=0, sleeper=lambda _: None)  # type: ignore[arg-type]

    batches = list(adapter.iter_full_record_id_batches(batch_size=1))

    assert batches == [["ric.2.ves.1"], ["ric.2.ves.2"]]
    assert [call[0] for call in session.calls] == [OCRE_FEED_URL]


def test_full_catalog_falls_back_to_the_published_void_dump() -> None:
    dump_url = "https://numismatics.org/ocre/nomisma.rdf"
    void = f'''<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:void="http://rdfs.org/ns/void#"><void:Dataset><void:dataDump rdf:resource="{dump_url}" /></void:Dataset></rdf:RDF>'''.encode()
    dump = b'''<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description rdf:about="http://numismatics.org/ocre/id/ric.2.ves.1"/></rdf:RDF>'''
    session = FakeSession({OCRE_FEED_URL: requests.Timeout("feed unavailable"), OCRE_VOID_URL: void, dump_url: dump})
    adapter = OcreSourceAdapter(session=session, request_delay_seconds=0, sleeper=lambda _: None)  # type: ignore[arg-type]

    assert list(adapter.iter_full_record_id_batches()) == [["ric.2.ves.1"]]
    assert [call[0] for call in session.calls] == [OCRE_FEED_URL, OCRE_VOID_URL, dump_url]


def test_atom_parser_uses_only_ocre_next_link_supplied_by_the_server() -> None:
    feed = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><link href="http://numismatics.org/ocre/id/ric.2.ves.1" /></entry><link rel="next" href="http://numismatics.org/ocre/feed/?q=*:*&amp;start=100" /></feed>'''

    identifiers, next_url = parse_atom_feed_page(feed, OCRE_FEED_URL)

    assert identifiers == ["ric.2.ves.1"]
    assert next_url == "https://numismatics.org/ocre/feed/?q=*:*&start=100"


def test_void_and_rdf_parsers_reject_untrusted_or_malformed_source_data() -> None:
    untrusted_void = b'''<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:void="http://rdfs.org/ns/void#"><void:dataDump rdf:resource="https://example.invalid/catalog.rdf" /></rdf:RDF>'''

    with pytest.raises(OcreParseError):
        parse_void_data_dump_url(untrusted_void)
    with pytest.raises(OcreParseError):
        list(iter_rdf_record_ids([b"<rdf:RDF>"]))


def test_void_parser_upgrades_ocres_legacy_http_data_dump_uri() -> None:
    void = b'''<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:void="http://rdfs.org/ns/void#"><void:dataDump rdf:resource="http://numismatics.org/ocre/nomisma.rdf" /></rdf:RDF>'''

    assert parse_void_data_dump_url(void) == "https://numismatics.org/ocre/nomisma.rdf"


def test_rdf_parser_deduplicates_canonical_ocre_identifiers() -> None:
    dump = b'''<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description rdf:about="http://numismatics.org/ocre/id/ric.2.ves.1"/><rdf:Description rdf:about="http://numismatics.org/ocre/id/ric.2.ves.1"/></rdf:RDF>'''

    assert list(iter_rdf_record_ids([dump])) == ["ric.2.ves.1"]


def test_parser_rejects_non_nuds_xml() -> None:
    with pytest.raises(OcreParseError):
        parse_nuds_xml(b"<not-nuds/>")
