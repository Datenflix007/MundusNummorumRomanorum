"""Template and endpoint coverage for the server-rendered research interface."""

from __future__ import annotations

from pathlib import Path

import pytest

from database.repository import CoinRepository, CoinTypeInput
from project import create_app


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


def test_results_page_shows_invalid_and_empty_search_states(web_client) -> None:
    invalid = web_client.get("/results?start_year=0")
    empty = web_client.get("/results?q=not-a-record")

    assert invalid.status_code == 400
    assert "Search could not be completed" in invalid.get_data(as_text=True)
    assert empty.status_code == 200
    assert "No matching coin types" in empty.get_data(as_text=True)
