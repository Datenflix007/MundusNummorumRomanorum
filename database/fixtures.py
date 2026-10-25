"""Synthetic test-only records; these are not RIC or historical reference data."""

from __future__ import annotations

from database.repository import CoinTypeInput


SYNTHETIC_COIN_TYPES: tuple[CoinTypeInput, ...] = (
    CoinTypeInput(
        external_id="synthetic-coin-type-001",
        reference_label="SYNTHETIC TEST TYPE 001",
        authority="Synthetic test authority A",
        mint="Synthetic mint A",
        denomination="Synthetic denomination",
        material="bronze",
        date_start=-12,
        date_end=8,
        obverse_legend="SYNTHETIC OBVERSE",
        reverse_legend="SYNTHETIC REVERSE",
        obverse_description="Synthetic obverse description for automated tests.",
        reverse_description="Synthetic reverse description for automated tests.",
        source_url="https://example.invalid/roman-coin-atlas/synthetic-001",
        image_attribution="Synthetic fixture; no image supplied.",
        image_license="Test data only",
    ),
    CoinTypeInput(
        external_id="synthetic-coin-type-002",
        reference_label="SYNTHETIC TEST TYPE 002",
        authority="Synthetic test authority B",
        mint="Synthetic mint B",
        denomination="Synthetic denomination",
        material="silver",
        date_start=41,
        date_end=54,
        source_url="https://example.invalid/roman-coin-atlas/synthetic-002",
    ),
)
