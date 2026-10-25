"""On-demand, attributed previews of representative specimens linked by OCRE.

The adapter never downloads or stores image files. It reads only an individual
OCRE record page after a user requests previews, then returns source-provided
HTTPS thumbnail URLs and the credit text exposed by OCRE.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import urlparse

import requests


OCRE_IMAGE_USER_AGENT = "RomanCoinAtlas/0.1 (local research tool)"
OCRE_RECORD_HOST = "numismatics.org"


class OcreImageError(RuntimeError):
    """An OCRE representative-image request could not be completed safely."""


@dataclass(frozen=True)
class OcreImagePreview:
    """One remote image preview and the source credit visible in OCRE."""

    thumbnail_url: str
    record_url: str | None
    side: str | None
    attribution: str

    def as_dict(self) -> dict[str, str | None]:
        """Return a JSON-safe representation for the browser."""
        return {
            "thumbnail_url": self.thumbnail_url,
            "record_url": self.record_url,
            "side": self.side,
            "attribution": self.attribution,
        }


class _Session(Protocol):
    def get(self, url: str, **kwargs: object) -> requests.Response: ...


class OcreImageAdapter:
    """Read a single trusted OCRE record page on demand."""

    def __init__(self, session: _Session | None = None, *, timeout_seconds: float = 10.0) -> None:
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds

    def fetch_previews(self, source_url: str) -> list[OcreImagePreview]:
        """Return OCRE-linked specimen previews without fetching any image bytes."""
        record_url = _trusted_ocre_record_url(source_url)
        try:
            response = self.session.get(
                record_url,
                headers={"User-Agent": OCRE_IMAGE_USER_AGENT, "Accept": "text/html"},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            raise OcreImageError("OCRE representative images could not be retrieved.") from error

        parser = _OcreImageHtmlParser()
        try:
            parser.feed(response.text)
            parser.close()
        except ValueError as error:
            raise OcreImageError("OCRE returned an unreadable image-preview page.") from error
        return parser.previews


def _trusted_ocre_record_url(source_url: str) -> str:
    """Permit only individual OCRE record pages; never request arbitrary URLs."""
    parsed = urlparse(source_url)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.netloc != OCRE_RECORD_HOST
        or not parsed.path.startswith("/ocre/id/")
    ):
        raise OcreImageError("Representative previews are available only for OCRE reference records.")
    return source_url.replace("http://", "https://", 1)


class _OcreImageHtmlParser(HTMLParser):
    """Extract image links and OCRE's visible per-image credit from HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.previews: list[OcreImagePreview] = []
        self._anchor: dict[str, str] | None = None
        self._seen_urls: set[str] = set()

    def handle_starttag(self, tag: str, attributes: list[tuple[str, str | None]]) -> None:
        attribute_map = {name: value or "" for name, value in attributes}
        if tag == "a":
            self._anchor = attribute_map
            return
        if tag != "img" or self._anchor is None:
            return

        classes = set(attribute_map.get("class", "").split())
        thumbnail_url = attribute_map.get("src", "")
        title = self._anchor.get("title", "")
        if "side-thumbnail" not in classes or not _is_https_url(thumbnail_url) or not title:
            return
        if thumbnail_url in self._seen_urls:
            return
        self._seen_urls.add(thumbnail_url)
        self.previews.append(
            OcreImagePreview(
                thumbnail_url=thumbnail_url,
                record_url=_trusted_external_url(self._anchor.get("id"))
                or _trusted_external_url(self._anchor.get("href")),
                side=_side_from_title(title),
                attribution=title,
            )
        )

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._anchor = None


def _is_https_url(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.scheme == "https" and bool(parsed.netloc)


def _trusted_external_url(url: str | None) -> str | None:
    """Keep external specimen links HTTPS-only; image hosts stay remote."""
    return url if _is_https_url(url) else None


def _side_from_title(title: str) -> str | None:
    normalized = title.casefold()
    if normalized.startswith("obverse"):
        return "obverse"
    if normalized.startswith("reverse"):
        return "reverse"
    return None
