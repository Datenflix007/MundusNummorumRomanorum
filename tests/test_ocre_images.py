"""Deterministic tests for on-demand, attributed OCRE image previews."""

from __future__ import annotations

import pytest

from services.ocre_images import OcreImageAdapter, OcreImageError


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    def __init__(self, html: str) -> None:
        self.html = html
        self.urls: list[str] = []

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.urls.append(url)
        return FakeResponse(self.html)


def test_image_adapter_extracts_attributed_https_thumbnails_without_downloading_them() -> None:
    html = '''<div><a title="Obverse of IMP-3020: Bibliothèque nationale de France" id="https://gallica.bnf.fr/ark:/12148/btv1b104488820"><img class="gi side-thumbnail" src="https://gallica.bnf.fr/iiif/ark:/12148/btv1b104488820/f1/full/,120/0/native.jpg"></a><a title="Reverse of IMP-3020: Bibliothèque nationale de France" href="https://gallica.bnf.fr/ark:/12148/btv1b104488820"><img class="gi side-thumbnail" src="https://gallica.bnf.fr/iiif/ark:/12148/btv1b104488820/f2/full/,120/0/native.jpg"></a></div>'''
    session = FakeSession(html)

    previews = OcreImageAdapter(session=session).fetch_previews("http://numismatics.org/ocre/id/ric.2.tr.826")

    assert session.urls == ["https://numismatics.org/ocre/id/ric.2.tr.826"]
    assert [preview.side for preview in previews] == ["obverse", "reverse"]
    assert previews[0].record_url == "https://gallica.bnf.fr/ark:/12148/btv1b104488820"
    assert "Bibliothèque nationale de France" in previews[0].attribution


def test_image_adapter_rejects_non_ocre_source_urls_without_network_access() -> None:
    session = FakeSession("<html></html>")

    with pytest.raises(OcreImageError):
        OcreImageAdapter(session=session).fetch_previews("https://example.invalid/coin")

    assert session.urls == []


def test_image_adapter_ignores_untrusted_or_uncredited_markup() -> None:
    html = '''<a title="Obverse of test: Test"><img class="side-thumbnail" src="http://images.example.invalid/coin.jpg"></a><a><img class="side-thumbnail" src="https://images.example.invalid/coin.jpg"></a>'''

    assert OcreImageAdapter(session=FakeSession(html)).fetch_previews("https://numismatics.org/ocre/id/ric.2.tr.826") == []
