"""OCRE NUDS/XML adapter and idempotent import service.

Only documented OCRE endpoints are used: the Atom feed for a bounded pilot,
the VoID document for the complete published identifier dump, and
``apis/getNuds`` for canonical NUDS/XML retrieval.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import sleep
from typing import Callable, Iterable, Iterator
from urllib.parse import unquote, urljoin, urlparse
from xml.etree import ElementTree

import requests

from database.repository import CoinRepository, CoinTypeInput


ATOM_NAMESPACE = "http://www.w3.org/2005/Atom"
NUDS_NAMESPACE = "http://nomisma.org/nuds"
XLINK_NAMESPACE = "http://www.w3.org/1999/xlink"
NAMESPACES = {"atom": ATOM_NAMESPACE, "nuds": NUDS_NAMESPACE}
OCRE_FEED_URL = "https://numismatics.org/ocre/feed/"
OCRE_VOID_URL = "https://numismatics.org/ocre/nomisma.void.rdf"
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
    """Fetch OCRE data through its documented discovery and NUDS endpoints."""

    def __init__(
        self,
        session: requests.Session | None = None,
        *,
        timeout_seconds: float = 60.0,
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

    def fetch_records(self, record_ids: Iterable[str], batch_size: int = 25) -> list[OcreCoinTypeRecord]:
        """Retrieve and parse documented NUDS/XML records in bounded batches."""
        if batch_size < 1:
            raise ValueError("OCRE NUDS batches must contain at least one record.")
        unique_ids = list(dict.fromkeys(record_ids))
        records: list[OcreCoinTypeRecord] = []
        for offset in range(0, len(unique_ids), batch_size):
            batch = unique_ids[offset : offset + batch_size]
            response = self._get(OCRE_NUDS_URL, params={"identifiers": "|".join(batch)})
            records.extend(parse_nuds_xml(response.content))
        return records

    def fetch_pilot(self, limit: int = 100) -> tuple[list[str], list[OcreCoinTypeRecord]]:
        """Discover then fetch a bounded pilot of real OCRE types."""
        record_ids = self.discover_record_ids(limit)
        return record_ids, self.fetch_records(record_ids)

    def iter_full_record_id_batches(self, batch_size: int = 25) -> Iterator[list[str]]:
        """Yield every canonical RIC identifier from OCRE's complete catalog.

        The documented Atom feed supplies pagination links. The published RDF
        dump is used only as a complete-source network fallback. Identifiers
        are streamed so the complete catalog does not have to fit in memory.
        """
        if batch_size < 1:
            raise ValueError("OCRE import batches must contain at least one record.")

        try:
            # OCRE documents Atom as a programmatic harvesting interface. Its
            # own pagination links avoid inventing search parameters.
            yield from self._iter_atom_record_id_batches(batch_size)
        except OcreNetworkError:
            # The official RDF dump remains a complete-source fallback when
            # the feed is temporarily unavailable.
            yield from self._iter_rdf_record_id_batches(batch_size)

    def _iter_rdf_record_id_batches(self, batch_size: int) -> Iterator[list[str]]:
        void_response = self._get(OCRE_VOID_URL)
        dump_url = parse_void_data_dump_url(void_response.content)
        dump_response = self._get(dump_url, stream=True)
        try:
            batch: list[str] = []
            for record_id in iter_rdf_record_ids(dump_response.iter_content(chunk_size=64 * 1024)):
                batch.append(record_id)
                if len(batch) == batch_size:
                    yield batch
                    batch = []
            if batch:
                yield batch
        finally:
            dump_response.close()

    def _iter_atom_record_id_batches(self, batch_size: int) -> Iterator[list[str]]:
        """Follow OCRE-provided Atom ``next`` links until the catalog ends."""
        page_url: str | None = OCRE_FEED_URL
        seen_page_urls: set[str] = set()
        seen_ids: set[str] = set()
        batch: list[str] = []
        while page_url:
            if page_url in seen_page_urls:
                raise OcreParseError("OCRE Atom feed repeated a pagination link.")
            seen_page_urls.add(page_url)
            response = self._get(page_url)
            record_ids, next_url = parse_atom_feed_page(response.content, page_url)
            for record_id in record_ids:
                if record_id in seen_ids:
                    continue
                seen_ids.add(record_id)
                batch.append(record_id)
                if len(batch) == batch_size:
                    yield batch
                    batch = []
            page_url = next_url
        if not seen_ids:
            raise OcreParseError("OCRE Atom feed contained no usable RIC identifiers.")
        if batch:
            yield batch

    def _get(self, url: str, **kwargs: object) -> requests.Response:
        if self._requests_made:
            self.sleeper(self.request_delay_seconds)
        self._requests_made += 1
        try:
            response = self.session.get(
                url,
                headers={
                    "User-Agent": OCRE_USER_AGENT,
                    "Accept": "application/xml, application/atom+xml, application/rdf+xml",
                },
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
        parsed_records = list(records)
        imported, duplicates = self.repository.insert_coin_types_if_new(
            record.to_coin_type_input() for record in parsed_records
        )
        return OcreImportReport(
            discovered=len(list(discovered_ids)),
            parsed=len(parsed_records),
            imported=imported,
            duplicates=duplicates,
        )

    def import_batches(
        self, batches: Iterable[tuple[Iterable[str], Iterable[OcreCoinTypeRecord]]]
    ) -> OcreImportReport:
        """Import source batches incrementally, allowing a full import to resume.

        A network interruption can leave earlier batches committed. Re-running
        the same command is safe because canonical external IDs are unique.
        """
        total_discovered = total_parsed = total_imported = total_duplicates = 0
        for discovered_ids, records in batches:
            report = self.import_records(discovered_ids, records)
            total_discovered += report.discovered
            total_parsed += report.parsed
            total_imported += report.imported
            total_duplicates += report.duplicates
        return OcreImportReport(
            discovered=total_discovered,
            parsed=total_parsed,
            imported=total_imported,
            duplicates=total_duplicates,
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


def parse_void_data_dump_url(xml_data: bytes | str) -> str:
    """Return OCRE's HTTPS RDF dump URL from its published VoID metadata."""
    try:
        root = ElementTree.fromstring(xml_data)
    except ElementTree.ParseError as error:
        raise OcreParseError("OCRE VoID metadata was not well-formed XML.") from error

    for element in root.iter():
        if _local_name(element.tag) != "dataDump":
            continue
        url = element.get(f"{{{XLINK_NAMESPACE}}}href") or element.get(
            "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}resource"
        )
        if _is_ocre_data_url(url):
            return _prefer_https(url)
    raise OcreParseError("OCRE VoID metadata did not provide a trusted RDF data-dump URL.")


def parse_atom_feed_page(xml_data: bytes | str, page_url: str) -> tuple[list[str], str | None]:
    """Parse one OCRE Atom result page and its server-provided next link."""
    try:
        root = ElementTree.fromstring(xml_data)
    except ElementTree.ParseError as error:
        raise OcreParseError("OCRE Atom feed was not well-formed XML.") from error

    record_ids: list[str] = []
    for entry in root.findall("atom:entry", NAMESPACES):
        for link in entry.findall("atom:link", NAMESPACES):
            uri = link.get("href")
            record_id = _record_id_from_uri(uri) if _is_ocre_canonical_uri(uri) else None
            if record_id and record_id.startswith("ric."):
                record_ids.append(record_id)
                break

    next_url: str | None = None
    for link in root.findall("atom:link", NAMESPACES):
        if link.get("rel") != "next":
            continue
        candidate = urljoin(page_url, link.get("href", ""))
        if not _is_ocre_feed_url(candidate):
            raise OcreParseError("OCRE Atom feed supplied an untrusted pagination link.")
        next_url = _prefer_https(candidate)
        break
    return record_ids, next_url


def iter_rdf_record_ids(chunks: Iterable[bytes]) -> Iterator[str]:
    """Stream distinct OCRE RIC identifiers from an RDF/XML data dump."""
    parser = ElementTree.XMLPullParser(events=("end",))
    seen: set[str] = set()
    try:
        for chunk in chunks:
            parser.feed(chunk)
            for _, element in parser.read_events():
                uri = element.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about")
                record_id = _record_id_from_uri(uri) if _is_ocre_canonical_uri(uri) else None
                if record_id and record_id.startswith("ric.") and record_id not in seen:
                    seen.add(record_id)
                    yield record_id
                element.clear()
        parser.close()
    except ElementTree.ParseError as error:
        raise OcreParseError("OCRE RDF data dump was not well-formed XML.") from error


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


def _is_ocre_data_url(url: str | None) -> bool:
    """Accept only OCRE's published legacy or HTTPS data-dump URI."""
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and parsed.netloc == "numismatics.org" and parsed.path.startswith("/ocre/")


def _prefer_https(url: str) -> str:
    """Use encrypted transport when OCRE's legacy metadata uses HTTP URIs."""
    return url.replace("http://", "https://", 1)


def _is_ocre_canonical_uri(url: str | None) -> bool:
    """Recognize OCRE's HTTP canonical record URIs inside its RDF data dump."""
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and parsed.netloc == "numismatics.org" and parsed.path.startswith("/ocre/id/")


def _is_ocre_feed_url(url: str | None) -> bool:
    """Accept OCRE's own feed links, including the legacy HTTP identifiers."""
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and parsed.netloc == "numismatics.org" and parsed.path.startswith("/ocre/feed/")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", maxsplit=1)[-1]
