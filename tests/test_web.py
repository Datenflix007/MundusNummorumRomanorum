"""Template and endpoint coverage for the server-rendered research interface."""

from __future__ import annotations

from pathlib import Path

import pytest

from database.repository import CoinRepository, CoinTypeInput
from project import create_app
from services.ocre_images import OcreImagePreview


@pytest.fixture
def web_client(tmp_path: Path):
    repository = CoinRepository(tmp_path / "catalog.sqlite")
    repository.initialize()
    repository.insert_coin_type(
        CoinTypeInput(
            external_id="ric.web.1",
            reference_label="RIC Web Test 1",
            original_reference="RIC Web Test 1",
            authority="Augustus",
            mint="Rome",
            denomination="As",
            material="bronze",
            date_start=-27,
            date_end=14,
            obverse_legend="IMP CAESAR",
            reverse_legend="ROMA",
            obverse_description="Laureate bust right",
            reverse_description="Roma seated left",
            source_url="https://example.invalid/ocre/ric.web.1",
            source_name="OCRE test source",
        )
    )
    return create_app(repository.database_path).test_client()


def test_search_page_has_labeled_accessible_filters(web_client) -> None:
    response = web_client.get("/")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '<label for="q">Keyword</label>' in page
    assert 'name="start_year"' in page
    assert 'name="material"' in page
    assert 'data-search-form' in page
    assert 'static/styles.css' in page
    assert "Searches external RIC reference data from OCRE" in page
    assert "Local research tool" not in page


def test_results_page_renders_compact_coin_card_and_placeholder(web_client) -> None:
    response = web_client.get("/results?q=caesar&material=bronze")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "RIC Web Test 1" in page
    assert "ric.web.1" in page
    assert "Augustus" in page
    assert "IMP CAESAR" in page
    assert "No image available" in page
    assert "/coins/1" in page


def test_coin_detail_page_renders_full_metadata_and_external_reference(web_client) -> None:
    response = web_client.get("/coins/1")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Laureate bust right" in page
    assert "Roma seated left" in page
    assert "Rome" in page
    assert "https://example.invalid/ocre/ric.web.1" in page
    assert "View OCRE test source record" in page
    assert "Show representative images from OCRE" in page


def test_image_preview_endpoint_is_on_demand_and_caches_attributed_metadata(web_client) -> None:
    calls = 0

    class PreviewAdapter:
        def fetch_previews(self, source_url: str) -> list[OcreImagePreview]:
            nonlocal calls
            calls += 1
            assert source_url == "https://example.invalid/ocre/ric.web.1"
            return [
                OcreImagePreview(
                    thumbnail_url="https://images.example.invalid/obverse.jpg",
                    record_url="https://collections.example.invalid/coin/1",
                    side="obverse",
                    attribution="Obverse of Example 1: Example Collection",
                )
            ]

    web_client.application.config["OCRE_IMAGE_ADAPTER_FACTORY"] = PreviewAdapter
    first = web_client.get("/api/coins/1/images")
    second = web_client.get("/api/coins/1/images")
    missing = web_client.get("/api/coins/999/images")

    assert first.status_code == 200
    assert first.json["cached"] is False
    assert first.json["items"][0]["side"] == "obverse"
    assert second.status_code == 200
    assert second.json["cached"] is True
    assert calls == 1
    assert missing.status_code == 404


def test_results_page_shows_invalid_and_empty_search_states(web_client) -> None:
    invalid = web_client.get("/results?start_year=0")
    empty = web_client.get("/results?q=not-a-record")

    assert invalid.status_code == 400
    assert "Search could not be completed" in invalid.get_data(as_text=True)
    assert empty.status_code == 200
    assert "No matching coin types" in empty.get_data(as_text=True)
