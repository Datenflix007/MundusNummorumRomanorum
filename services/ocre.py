"""OCRE NUDS/XML adapter and idempotent import service.

Only documented OCRE endpoints are used: the Atom feed for a bounded list of
current records and ``apis/getNuds`` for aggregated NUDS/XML retrieval.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import sleep
from typing import Callable, Iterable
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree

import requests

from database.repository import CoinRepository, CoinTypeInput


ATOM_NAMESPACE = "http://www.w3.org/2005/Atom"
NUDS_NAMESPACE = "http://nomisma.org/nuds"
XLINK_NAMESPACE = "http://www.w3.org/1999/xlink"
NAMESPACES = {"atom": ATOM_NAMESPACE, "nuds": NUDS_NAMESPACE}
OCRE_FEED_URL = "https://numismatics.org/ocre/feed/"
OCRE_NUDS_URL = "https://numismatics.org/ocre/apis/getNuds"
OCRE_CANONICAL_URI_PREFIX = "http://numismatics.org/ocre/id/"
OCRE_SOURCE_NAME = "Online Coins of the Roman Empire (OCRE)"
OCRE_USER_AGENT = "RomanCoinAtlas/0.1 (local research tool)"


class OcreError(RuntimeError):
    """Base error for an OCRE transport or source-format failure."""


class OcreNetworkError(OcreError):
    """Raised when a documented OCRE endpoint cannot be retrieved safely."""


class OcreParseError(OcreError):
    """Raised when an OCRE response is not valid expected NUDS/XML or Atom."""


@dataclass(frozen=True)
class OcreCoinTypeRecord:
    """Canonical source fields retained from one OCRE NUDS conceptual record."""

    record_id: str
    canonical_uri: str
    original_reference: str
    authority: str | None
    mint: str | None
    denomination: str | None
    material: str | None
    date_start: int | None
    date_end: int | None
    obverse_legend: str | None
    reverse_legend: str | None
    obverse_description: str | None
    reverse_description: str | None
    source_attribution: str | None
    source_license: str | None

    def to_coin_type_input(self) -> CoinTypeInput:
        """Map source data into the local schema without deriving absent fields."""
        return CoinTypeInput(
            external_id=self.record_id,
            reference_label=self.original_reference,
            authority=self.authority,
            mint=self.mint,
            denomination=self.denomination,
            material=self.material,
            date_start=self.date_start,
            date_end=self.date_end,
            obverse_legend=self.obverse_legend,
            reverse_legend=self.reverse_legend,
            obverse_description=self.obverse_description,
            reverse_description=self.reverse_description,
            source_url=self.canonical_uri,
            source_name=OCRE_SOURCE_NAME,
            original_reference=self.original_reference,
            source_attribution=self.source_attribution,
            source_license=self.source_license,
            # Remote images are deliberately not imported or redistributed.
            obverse_image_url=None,
            reverse_image_url=None,
        )


@dataclass(frozen=True)
class OcreImportReport:
    """Counts from one bounded import request."""

    discovered: int
    parsed: int
    imported: int
    duplicates: int


class OcreSourceAdapter:
    """Fetch and parse OCRE data via its documented Atom and NUDS endpoints."""

    def __init__(
        self,
        session: requests.Session | None = None,
        *,
        timeout_seconds: float = 20.0,
        request_delay_seconds: float = 0.3,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds
        self.request_delay_seconds = request_delay_seconds
        self.sleeper = sleeper
        self._requests_made = 0

    def discover_record_ids(self, limit: int) -> list[str]:
        """Return up to ``limit`` RIC IDs from OCRE's documented Atom feed."""
        if not 1 <= limit <= 200:
            raise ValueError("OCRE pilot imports must request between 1 and 200 records.")

        response = self._get(OCRE_FEED_URL)
        try:
            root = ElementTree.fromstring(response.content)
        except ElementTree.ParseError as error:
            raise OcreParseError("OCRE Atom feed was not well-formed XML.") from error

        record_ids: list[str] = []
        seen: set[str] = set()
        for entry in root.findall("atom:entry", NAMESPACES):
            for link in entry.findall("atom:link", NAMESPACES):
                record_id = _record_id_from_uri(link.get("href"))
                if record_id is None or not record_id.startswith("ric.") or record_id in seen:
                    continue
                seen.add(record_id)
                record_ids.append(record_id)
                break
            if len(record_ids) == limit:
                break

        if not record_ids:
            raise OcreParseError("OCRE Atom feed contained no usable RIC identifiers.")
        return record_ids

    def fetch_records(self, record_ids: Iterable[str]) -> list[OcreCoinTypeRecord]:
        """Retrieve and parse documented NUDS/XML records in modest batches of 25."""
        unique_ids = list(dict.fromkeys(record_ids))
        records: list[OcreCoinTypeRecord] = []
        for offset in range(0, len(unique_ids), 25):
            batch = unique_ids[offset : offset + 25]
            response = self._get(OCRE_NUDS_URL, params={"identifiers": "|".join(batch)})
            records.extend(parse_nuds_xml(response.content))
        return records

    def fetch_pilot(self, limit: int = 100) -> tuple[list[str], list[OcreCoinTypeRecord]]:
        """Discover then fetch a bounded pilot of real OCRE types."""
        record_ids = self.discover_record_ids(limit)
        return record_ids, self.fetch_records(record_ids)

    def _get(self, url: str, **kwargs: object) -> requests.Response:
        if self._requests_made:
            self.sleeper(self.request_delay_seconds)
        self._requests_made += 1
        try:
            response = self.session.get(
                url,
                headers={"User-Agent": OCRE_USER_AGENT, "Accept": "application/xml, application/atom+xml"},
                timeout=self.timeout_seconds,
                **kwargs,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            raise OcreNetworkError(f"Could not retrieve OCRE data from {url}: {error}") from error
        return response


class OcreImportService:
    """Persist parsed OCRE types once, leaving existing reference rows unchanged."""

    def __init__(self, repository: CoinRepository) -> None:
        self.repository = repository

    def import_records(
        self, discovered_ids: Iterable[str], records: Iterable[OcreCoinTypeRecord]
    ) -> OcreImportReport:
        """Import unique parsed records and report idempotent duplicate skips."""
        imported = 0
        duplicates = 0
        parsed_records = list(records)
        for record in parsed_records:
            _, created = self.repository.insert_coin_type_if_new(record.to_coin_type_input())
            if created:
                imported += 1
            else:
                duplicates += 1
        return OcreImportReport(
            discovered=len(list(discovered_ids)),
            parsed=len(parsed_records),
            imported=imported,
            duplicates=duplicates,
        )


def parse_nuds_xml(xml_data: bytes | str) -> list[OcreCoinTypeRecord]:
    """Parse individual or aggregated OCRE NUDS/XML without fabricating fields."""
    try:
        root = ElementTree.fromstring(xml_data)
    except ElementTree.ParseError as error:
        raise OcreParseError("OCRE NUDS response was not well-formed XML.") from error

    nuds_records = [root] if _local_name(root.tag) == "nuds" else root.findall("nuds:nuds", NAMESPACES)
    if not nuds_records:
        raise OcreParseError("OCRE NUDS response contained no conceptual records.")
    return [_parse_nuds_record(record) for record in nuds_records]


def _parse_nuds_record(record: ElementTree.Element) -> OcreCoinTypeRecord:
    record_id = _element_text(record, "nuds:control/nuds:recordId")
    if not record_id:
        raise OcreParseError("OCRE NUDS record is missing its canonical recordId.")

    type_description = record.find("nuds:descMeta/nuds:typeDesc", NAMESPACES)
    if type_description is None:
        raise OcreParseError(f"OCRE record {record_id} is missing typeDesc.")

    date_start, date_end = _dates_from_type_description(type_description)
    title = _element_text(record, "nuds:descMeta/nuds:title") or record_id
    return OcreCoinTypeRecord(
        record_id=record_id,
        canonical_uri=f"{OCRE_CANONICAL_URI_PREFIX}{record_id}",
        original_reference=title,
        authority=_element_text(type_description, "nuds:authority/nuds:persname"),
        mint=_element_text(type_description, "nuds:geographic/nuds:geogname"),
        denomination=_element_text(type_description, "nuds:denomination"),
        material=_canonical_material(_element_text(type_description, "nuds:material")),
        date_start=date_start,
        date_end=date_end,
        obverse_legend=_element_text(type_description, "nuds:obverse/nuds:legend"),
        reverse_legend=_element_text(type_description, "nuds:reverse/nuds:legend"),
        obverse_description=_element_text(type_description, "nuds:obverse/nuds:type/nuds:description"),
        reverse_description=_element_text(type_description, "nuds:reverse/nuds:type/nuds:description"),
        source_attribution=_element_text(record, "nuds:control/nuds:maintenanceAgency/nuds:agencyName"),
        source_license=_attribute_value(record, "nuds:control/nuds:rightsStmt/nuds:license", f"{{{XLINK_NAMESPACE}}}href"),
    )


def _dates_from_type_description(type_description: ElementTree.Element) -> tuple[int | None, int | None]:
    from_date = type_description.find("nuds:dateRange/nuds:fromDate", NAMESPACES)
    to_date = type_description.find("nuds:dateRange/nuds:toDate", NAMESPACES)
    if from_date is not None or to_date is not None:
        return _year_from_standard_date(from_date), _year_from_standard_date(to_date)

    single_date = type_description.find("nuds:date", NAMESPACES)
    year = _year_from_standard_date(single_date)
    return year, year


def _year_from_standard_date(element: ElementTree.Element | None) -> int | None:
    if element is None:
        return None
    value = element.get("standardDate")
    if value is None or not value.lstrip("-").isdigit():
        return None
    year = int(value)
    return year if year != 0 else None


def _element_text(element: ElementTree.Element, path: str) -> str | None:
    child = element.find(path, NAMESPACES)
    if child is None or child.text is None:
        return None
    value = child.text.strip()
    return value or None


def _attribute_value(element: ElementTree.Element, path: str, attribute: str) -> str | None:
    child = element.find(path, NAMESPACES)
    return child.get(attribute) if child is not None else None


def _canonical_material(material: str | None) -> str | None:
    if material is None:
        return None
    aliases = {"ae": "bronze", "ar": "silver", "av": "gold"}
    normalized = " ".join(material.split()).casefold()
    return aliases.get(normalized, normalized)


def _record_id_from_uri(uri: str | None) -> str | None:
    if not uri:
        return None
    path = urlparse(uri).path
    marker = "/ocre/id/"
    if marker not in path:
        return None
    record_id = unquote(path.split(marker, maxsplit=1)[1]).removesuffix(".xml")
    return record_id or None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", maxsplit=1)[-1]
