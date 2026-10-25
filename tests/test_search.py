"""Unit and integration tests for Python-backed coin-type catalog search."""

from __future__ import annotations

from pathlib import Path

import pytest

from database.repository import CoinRepository, CoinTypeInput
from project import create_app
from services.search import SearchValidationError, parse_search_parameters


@pytest.fixture
def catalog(tmp_path: Path) -> CoinRepository:
    repository = CoinRepository(tmp_path / "catalog.sqlite")
    repository.initialize()
    for coin_type in (
        CoinTypeInput(
            external_id="ric.test.alpha",
            reference_label="RIC Test Alpha",
            original_reference="RIC Test Alpha original reference",
            authority="Augustus",
            mint="Rome",
            denomination="As",
            material="bronze",
            date_start=-10,
            date_end=-5,
            obverse_legend="IMP ALPHA",
            reverse_legend="ROMA",
            obverse_description="Laureate portrait facing right",
            reverse_description="Roma seated with shield",
            source_url="https://example.invalid/alpha",
        ),
        CoinTypeInput(
            external_id="ric.test.beta",
            reference_label="RIC Test Beta",
            authority="Tiberius",
            mint="Lugdunum",
            denomination="Denarius",
            material="silver",
            date_start=-3,
            date_end=4,
            obverse_legend="TI CAESAR",
            reverse_legend="PONTIF MAXIM",
            obverse_description="Bare head facing left",
            reverse_description="Pax standing with branch",
            source_url="https://example.invalid/beta",
        ),
        CoinTypeInput(
            external_id="ric.test.gamma",
            reference_label="RIC Test Gamma",
            authority="Tiberius",
            mint="Rome",
            denomination="As",
            material="bronze",
            date_start=8,
            date_end=12,
            obverse_legend="TI GAMMA",
            reverse_legend="S C",
            obverse_description="Radiate bust facing right",
            reverse_description="Eagle on globe",
            source_url="https://example.invalid/gamma",
        ),
    ):
        repository.insert_coin_type(coin_type)
    return repository


def _search(repository: CoinRepository, **parameters: str) -> tuple[list[str], int]:
    criteria, _ = parse_search_parameters(parameters)
    page = repository.search_coin_types(criteria)
    return [coin.external_id for coin in page.items], page.total


@pytest.mark.parametrize(
    "keyword, expected",
    [
        ("imP alpha", ["ric.test.alpha"]),
        ("pax standing", ["ric.test.beta"]),
        ("augustus", ["ric.test.alpha"]),
        ("lugd", ["ric.test.beta"]),
        ("test gamma", ["ric.test.gamma"]),
    ],
)
def test_keyword_search_is_case_insensitive_and_partial(catalog: CoinRepository, keyword: str, expected: list[str]) -> None:
    items, total = _search(catalog, q=keyword)

    assert items == expected
    assert total == len(expected)


def test_date_range_uses_interval_overlap(catalog: CoinRepository) -> None:
    items, total = _search(catalog, start_year="-7", end_year="-2", sort="date_start")

    assert items == ["ric.test.alpha", "ric.test.beta"]
    assert total == 2


def test_combined_filters_use_and_semantics(catalog: CoinRepository) -> None:
    items, total = _search(catalog, material="bronze", authority="tiberius", mint="rome", denomination="as")

    assert items == ["ric.test.gamma"]
    assert total == 1


def test_pagination_sorting_and_empty_results(catalog: CoinRepository) -> None:
    first_page, first_total = _search(catalog, sort="authority", limit="1", page="1")
    second_page, second_total = _search(catalog, sort="authority", limit="1", page="2")
    empty_items, empty_total = _search(catalog, q="not present")

    assert first_page == ["ric.test.alpha"]
    assert second_page == ["ric.test.beta"]
    assert (first_total, second_total) == (3, 3)
    assert empty_items == []
    assert empty_total == 0


@pytest.mark.parametrize(
    "parameters",
    [
        {"start_year": "0"},
        {"start_year": "10", "end_year": "9"},
        {"limit": "101"},
        {"page": "nope"},
        {"sort": "drop table"},
    ],
)
def test_invalid_search_parameters_return_useful_errors(parameters: dict[str, str]) -> None:
    with pytest.raises(SearchValidationError):
        parse_search_parameters(parameters)


def test_sql_injection_text_is_literal_and_cannot_broaden_results(catalog: CoinRepository) -> None:
    items, total = _search(catalog, q="' OR 1=1 --")

    assert items == []
    assert total == 0


def test_coin_endpoints_return_source_data_and_distinguish_errors(catalog: CoinRepository, tmp_path: Path) -> None:
    app = create_app(catalog.database_path)
    client = app.test_client()

    response = client.get("/api/coins?q=imp%20alpha")
    detail_response = client.get("/api/coins/1")
    empty_response = client.get("/api/coins?q=not-present")
    invalid_response = client.get("/api/coins?start_year=0")
    missing_response = client.get("/api/coins/999")
    failed_request = create_app(tmp_path / "missing.sqlite").test_client().get("/api/coins")

    assert response.status_code == 200
    assert response.json["items"][0]["external_id"] == "ric.test.alpha"
    assert response.json["items"][0]["source_url"] == "https://example.invalid/alpha"
    assert detail_response.status_code == 200
    assert detail_response.json["external_id"] == "ric.test.alpha"
    assert empty_response.status_code == 200
    assert empty_response.json["items"] == []
    assert invalid_response.status_code == 400
    assert invalid_response.json["error"]["code"] == "invalid_query"
    assert missing_response.status_code == 404
    assert missing_response.json["error"]["code"] == "not_found"
    assert failed_request.status_code == 500
    assert failed_request.json["error"]["code"] == "database_error"
