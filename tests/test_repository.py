"""Deterministic SQLite tests using synthetic data only."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sqlite3

import pytest

from database.fixtures import SYNTHETIC_COIN_TYPES
from database.repository import CoinImageDraft, CoinRepository, FoundCoinDraft, initialize_database


@pytest.fixture
def repository(tmp_path: Path) -> CoinRepository:
    database_path = tmp_path / "catalog.sqlite"
    repository = CoinRepository(database_path)
    repository.initialize()
    return repository


def test_initialize_database_is_repeatable_and_creates_required_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "nested" / "catalog.sqlite"
    initialize_database(database_path)
    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }

    assert {"coin_types", "found_coins", "coin_images"}.issubset(tables)


def test_reference_coin_types_are_retrievable_but_not_editable(repository: CoinRepository) -> None:
    inserted = [repository.insert_coin_type(coin_type) for coin_type in SYNTHETIC_COIN_TYPES]

    assert repository.get_coin_type(inserted[0].id) == inserted[0]
    assert [coin_type.external_id for coin_type in repository.list_coin_types()] == [
        "synthetic-coin-type-001",
        "synthetic-coin-type-002",
    ]
    assert not hasattr(repository, "update_coin_type")


def test_reference_type_constraints_reject_year_zero_and_duplicate_external_id(repository: CoinRepository) -> None:
    fixture = SYNTHETIC_COIN_TYPES[0]
    repository.insert_coin_type(fixture)

    with pytest.raises(sqlite3.IntegrityError):
        repository.insert_coin_type(replace(fixture, external_id="synthetic-invalid-date", date_start=0))
    with pytest.raises(sqlite3.IntegrityError):
        repository.insert_coin_type(fixture)


def test_found_coin_can_be_unidentified_then_updated_with_a_reference_type(repository: CoinRepository) -> None:
    found_coin = repository.insert_found_coin(
        FoundCoinDraft(
            inventory_number="SPECIMEN-001",
            documented_title="Unidentified test specimen",
            material="bronze",
            notes="Synthetic local specimen used only in tests.",
        )
    )
    reference_type = repository.insert_coin_type(SYNTHETIC_COIN_TYPES[0])
    updated = repository.update_found_coin(replace(found_coin, coin_type_id=reference_type.id, notes="Linked in test."))

    assert found_coin.coin_type_id is None
    assert updated.coin_type_id == reference_type.id
    assert updated.notes == "Linked in test."
    assert repository.list_found_coins() == [updated]


def test_coin_images_support_obverse_and_reverse_and_enforce_foreign_keys(repository: CoinRepository) -> None:
    found_coin = repository.insert_found_coin(
        FoundCoinDraft(inventory_number="SPECIMEN-002", documented_title="Photographed test specimen")
    )
    reverse = repository.insert_coin_image(found_coin.id, CoinImageDraft(side="reverse", file_path="tests/reverse.jpg"))
    repository.insert_coin_image(found_coin.id, CoinImageDraft(side="obverse", file_path="tests/obverse.jpg"))
    updated_reverse = repository.update_coin_image(replace(reverse, caption="Synthetic reverse photo"))

    assert [image.side for image in repository.list_coin_images(found_coin.id)] == ["obverse", "reverse"]
    assert repository.get_coin_image(updated_reverse.id) == updated_reverse
    with pytest.raises(sqlite3.IntegrityError):
        repository.insert_coin_image(999, CoinImageDraft(side="obverse", file_path="tests/missing.jpg"))
