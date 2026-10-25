"""Repository API for local reference data and user-entered coin specimens."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


SCHEMA_PATH = Path(__file__).with_name("schema.sql")


@dataclass(frozen=True)
class CoinTypeInput:
    """Trusted import data for a reference coin type, never a user specimen."""

    external_id: str
    reference_label: str
    authority: str
    material: str
    date_start: int
    date_end: int
    source_url: str
    mint: str | None = None
    denomination: str | None = None
    obverse_legend: str | None = None
    reverse_legend: str | None = None
    obverse_description: str | None = None
    reverse_description: str | None = None
    obverse_image_url: str | None = None
    reverse_image_url: str | None = None
    image_attribution: str | None = None
    image_license: str | None = None


@dataclass(frozen=True)
class CoinType:
    """An immutable external reference type returned by the repository."""

    id: int
    external_id: str
    reference_label: str
    authority: str
    material: str
    date_start: int
    date_end: int
    source_url: str
    mint: str | None
    denomination: str | None
    obverse_legend: str | None
    reverse_legend: str | None
    obverse_description: str | None
    reverse_description: str | None
    obverse_image_url: str | None
    reverse_image_url: str | None
    image_attribution: str | None
    image_license: str | None


@dataclass(frozen=True)
class FoundCoinDraft:
    """Data supplied when an individually documented coin is first recorded."""

    inventory_number: str
    documented_title: str
    coin_type_id: int | None = None
    material: str | None = None
    weight_grams: float | None = None
    diameter_mm: float | None = None
    notes: str = ""


@dataclass(frozen=True)
class FoundCoin:
    """A user-entered specimen that can remain unidentified."""

    id: int
    inventory_number: str
    documented_title: str
    coin_type_id: int | None
    material: str | None
    weight_grams: float | None
    diameter_mm: float | None
    notes: str


@dataclass(frozen=True)
class CoinImageDraft:
    """A photograph of one side of a documented coin."""

    side: str
    file_path: str
    caption: str | None = None
    rights_note: str | None = None


@dataclass(frozen=True)
class CoinImage:
    """Stored metadata for an obverse or reverse specimen photograph."""

    id: int
    found_coin_id: int
    side: str
    file_path: str
    caption: str | None
    rights_note: str | None


def initialize_database(database_path: str | Path) -> Path:
    """Create all tables and indexes; safe to run repeatedly on the same file."""
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = _connect(path)
    try:
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    finally:
        connection.close()
    return path


def _connect(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def _transaction(database_path: Path) -> Iterator[sqlite3.Connection]:
    connection = _connect(database_path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


class CoinRepository:
    """Repository for immutable reference types and editable local specimens.

    `coin_types` has no update method by design: external reference data is
    read-only in the specimen-management workflow. Future import code may add
    reference records through `insert_coin_type`; it must not use user data.
    """

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def initialize(self) -> Path:
        """Create this repository's schema if it does not exist yet."""
        return initialize_database(self.database_path)

    def insert_coin_type(self, coin_type: CoinTypeInput) -> CoinType:
        """Insert one externally sourced reference type for an import workflow."""
        with _transaction(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO coin_types (
                    external_id, reference_label, authority, mint, denomination,
                    material, date_start, date_end, obverse_legend, reverse_legend,
                    obverse_description, reverse_description, source_url,
                    obverse_image_url, reverse_image_url, image_attribution, image_license
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    coin_type.external_id,
                    coin_type.reference_label,
                    coin_type.authority,
                    coin_type.mint,
                    coin_type.denomination,
                    coin_type.material,
                    coin_type.date_start,
                    coin_type.date_end,
                    coin_type.obverse_legend,
                    coin_type.reverse_legend,
                    coin_type.obverse_description,
                    coin_type.reverse_description,
                    coin_type.source_url,
                    coin_type.obverse_image_url,
                    coin_type.reverse_image_url,
                    coin_type.image_attribution,
                    coin_type.image_license,
                ),
            )
            inserted = self.get_coin_type(cursor.lastrowid, connection=connection)

        if inserted is None:
            raise RuntimeError("Inserted coin type could not be retrieved.")
        return inserted

    def get_coin_type(self, coin_type_id: int, *, connection: sqlite3.Connection | None = None) -> CoinType | None:
        """Retrieve a reference type by its local identifier."""
        if connection is not None:
            row = connection.execute("SELECT * FROM coin_types WHERE id = ?", (coin_type_id,)).fetchone()
            return _coin_type_from_row(row) if row else None

        with _transaction(self.database_path) as open_connection:
            row = open_connection.execute("SELECT * FROM coin_types WHERE id = ?", (coin_type_id,)).fetchone()
        return _coin_type_from_row(row) if row else None

    def list_coin_types(self) -> list[CoinType]:
        """List imported reference types without offering mutation operations."""
        with _transaction(self.database_path) as connection:
            rows = connection.execute(
                "SELECT * FROM coin_types ORDER BY authority COLLATE NOCASE, mint COLLATE NOCASE, reference_label"
            ).fetchall()
        return [_coin_type_from_row(row) for row in rows]

    def insert_found_coin(self, found_coin: FoundCoinDraft) -> FoundCoin:
        """Insert a local specimen; its reference type is intentionally optional."""
        with _transaction(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO found_coins (
                    inventory_number, documented_title, coin_type_id, material,
                    weight_grams, diameter_mm, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    found_coin.inventory_number,
                    found_coin.documented_title,
                    found_coin.coin_type_id,
                    found_coin.material,
                    found_coin.weight_grams,
                    found_coin.diameter_mm,
                    found_coin.notes,
                ),
            )
            inserted = self.get_found_coin(cursor.lastrowid, connection=connection)

        if inserted is None:
            raise RuntimeError("Inserted found coin could not be retrieved.")
        return inserted

    def get_found_coin(self, found_coin_id: int, *, connection: sqlite3.Connection | None = None) -> FoundCoin | None:
        """Retrieve one user-entered specimen by its local identifier."""
        if connection is not None:
            row = connection.execute("SELECT * FROM found_coins WHERE id = ?", (found_coin_id,)).fetchone()
            return _found_coin_from_row(row) if row else None

        with _transaction(self.database_path) as open_connection:
            row = open_connection.execute("SELECT * FROM found_coins WHERE id = ?", (found_coin_id,)).fetchone()
        return _found_coin_from_row(row) if row else None

    def update_found_coin(self, found_coin: FoundCoin) -> FoundCoin:
        """Update editable local specimen fields, including an optional type link."""
        with _transaction(self.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE found_coins
                SET inventory_number = ?, documented_title = ?, coin_type_id = ?, material = ?,
                    weight_grams = ?, diameter_mm = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    found_coin.inventory_number,
                    found_coin.documented_title,
                    found_coin.coin_type_id,
                    found_coin.material,
                    found_coin.weight_grams,
                    found_coin.diameter_mm,
                    found_coin.notes,
                    found_coin.id,
                ),
            )
            if cursor.rowcount == 0:
                raise LookupError(f"Found coin {found_coin.id} does not exist.")
            updated = self.get_found_coin(found_coin.id, connection=connection)

        if updated is None:
            raise RuntimeError("Updated found coin could not be retrieved.")
        return updated

    def list_found_coins(self) -> list[FoundCoin]:
        """List user specimens by their stable local inventory number."""
        with _transaction(self.database_path) as connection:
            rows = connection.execute("SELECT * FROM found_coins ORDER BY inventory_number").fetchall()
        return [_found_coin_from_row(row) for row in rows]

    def insert_coin_image(self, found_coin_id: int, image: CoinImageDraft) -> CoinImage:
        """Attach obverse or reverse photograph metadata to a local specimen."""
        with _transaction(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO coin_images (found_coin_id, side, file_path, caption, rights_note)
                VALUES (?, ?, ?, ?, ?)
                """,
                (found_coin_id, image.side, image.file_path, image.caption, image.rights_note),
            )
            row = connection.execute("SELECT * FROM coin_images WHERE id = ?", (cursor.lastrowid,)).fetchone()

        if row is None:
            raise RuntimeError("Inserted coin image could not be retrieved.")
        return _coin_image_from_row(row)

    def list_coin_images(self, found_coin_id: int) -> list[CoinImage]:
        """List all specimen photographs, with obverse entries first."""
        with _transaction(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT * FROM coin_images
                WHERE found_coin_id = ?
                ORDER BY CASE side WHEN 'obverse' THEN 0 ELSE 1 END, id
                """,
                (found_coin_id,),
            ).fetchall()
        return [_coin_image_from_row(row) for row in rows]

    def get_coin_image(self, image_id: int) -> CoinImage | None:
        """Retrieve one local specimen photograph by its identifier."""
        with _transaction(self.database_path) as connection:
            row = connection.execute("SELECT * FROM coin_images WHERE id = ?", (image_id,)).fetchone()
        return _coin_image_from_row(row) if row else None

    def update_coin_image(self, image: CoinImage) -> CoinImage:
        """Update editable metadata for an existing local specimen photograph."""
        with _transaction(self.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE coin_images
                SET side = ?, file_path = ?, caption = ?, rights_note = ?
                WHERE id = ? AND found_coin_id = ?
                """,
                (
                    image.side,
                    image.file_path,
                    image.caption,
                    image.rights_note,
                    image.id,
                    image.found_coin_id,
                ),
            )
            if cursor.rowcount == 0:
                raise LookupError(f"Coin image {image.id} does not exist for this specimen.")
            row = connection.execute("SELECT * FROM coin_images WHERE id = ?", (image.id,)).fetchone()

        if row is None:
            raise RuntimeError("Updated coin image could not be retrieved.")
        return _coin_image_from_row(row)


def _coin_type_from_row(row: sqlite3.Row) -> CoinType:
    return CoinType(
        id=row["id"],
        external_id=row["external_id"],
        reference_label=row["reference_label"],
        authority=row["authority"],
        material=row["material"],
        date_start=row["date_start"],
        date_end=row["date_end"],
        source_url=row["source_url"],
        mint=row["mint"],
        denomination=row["denomination"],
        obverse_legend=row["obverse_legend"],
        reverse_legend=row["reverse_legend"],
        obverse_description=row["obverse_description"],
        reverse_description=row["reverse_description"],
        obverse_image_url=row["obverse_image_url"],
        reverse_image_url=row["reverse_image_url"],
        image_attribution=row["image_attribution"],
        image_license=row["image_license"],
    )


def _found_coin_from_row(row: sqlite3.Row) -> FoundCoin:
    return FoundCoin(
        id=row["id"],
        inventory_number=row["inventory_number"],
        documented_title=row["documented_title"],
        coin_type_id=row["coin_type_id"],
        material=row["material"],
        weight_grams=row["weight_grams"],
        diameter_mm=row["diameter_mm"],
        notes=row["notes"],
    )


def _coin_image_from_row(row: sqlite3.Row) -> CoinImage:
    return CoinImage(
        id=row["id"],
        found_coin_id=row["found_coin_id"],
        side=row["side"],
        file_path=row["file_path"],
        caption=row["caption"],
        rights_note=row["rights_note"],
    )
