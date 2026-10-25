"""Application entry point and shared normalization helpers for Roman Coin Atlas."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Final, Sequence

from flask import Flask, jsonify, request

from database.repository import CoinRepository, DatabaseRequestError, initialize_database
from services.ocre import OcreError, OcreImportService, OcreSourceAdapter
from services.search import SearchValidationError, normalize_search_keyword, parse_search_parameters


MATERIAL_ALIASES: Final[dict[str, str]] = {
    "ae": "bronze",
    "bronze": "bronze",
    "copper alloy": "bronze",
    "ar": "silver",
    "silver": "silver",
    "billon": "billon",
    "av": "gold",
    "gold": "gold",
}
DEFAULT_DATABASE_PATH: Final[Path] = Path(__file__).parent / "database" / "roman_coin_atlas.sqlite"


def normalize_keyword(text: str) -> str:
    """Return a case-insensitive search expression with one space between words."""
    try:
        return normalize_search_keyword(text)
    except SearchValidationError as error:
        raise TypeError("Search text must be a string.") from error


def validate_year_range(start: int, end: int) -> tuple[int, int]:
    """Validate and return an inclusive historical year range.

    Years before the common era are represented by negative integers. There is
    no year zero in this representation.
    """
    if isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int) or not isinstance(end, int):
        raise TypeError("Years must be integers.")
    if start == 0 or end == 0:
        raise ValueError("Year zero is not valid in a historical date range.")
    if start > end:
        raise ValueError("The start year must not be after the end year.")

    return start, end


def normalize_material(material: str) -> str:
    """Convert a supported material label to its canonical catalogue value."""
    if not isinstance(material, str):
        raise TypeError("Material must be a string.")

    normalized_material = " ".join(material.split()).casefold()
    try:
        return MATERIAL_ALIASES[normalized_material]
    except KeyError as error:
        raise ValueError(f"Unsupported material: {material!r}") from error


def create_app(database_path: str | Path | None = None) -> Flask:
    """Create the Flask application without requiring a database connection."""
    app = Flask(__name__)
    app.config["DATABASE_PATH"] = str(database_path or DEFAULT_DATABASE_PATH)

    @app.get("/health")
    def health() -> tuple[object, int]:
        return jsonify(status="ok", service="roman-coin-atlas"), 200

    @app.get("/api/coins")
    def search_coins() -> tuple[object, int]:
        try:
            criteria, page_number = parse_search_parameters(request.args.to_dict(flat=True))
        except SearchValidationError as error:
            return jsonify(error={"code": "invalid_query", "message": str(error)}), 400

        try:
            results = CoinRepository(app.config["DATABASE_PATH"]).search_coin_types(criteria)
        except DatabaseRequestError as error:
            return jsonify(error={"code": "database_error", "message": str(error)}), 500

        return jsonify(
            items=[_serialize_coin_type(coin_type) for coin_type in results.items],
            pagination={
                "page": page_number,
                "page_size": criteria.limit,
                "total": results.total,
                "pages": (results.total + criteria.limit - 1) // criteria.limit,
            },
        ), 200

    @app.get("/api/coins/<int:coin_type_id>")
    def coin_detail(coin_type_id: int) -> tuple[object, int]:
        try:
            coin_type = CoinRepository(app.config["DATABASE_PATH"]).get_coin_type(coin_type_id)
        except Exception as error:
            if error.__class__.__name__ == "OperationalError":
                return jsonify(error={"code": "database_error", "message": "The coin catalog could not be read."}), 500
            raise
        if coin_type is None:
            return jsonify(error={"code": "not_found", "message": f"Coin type {coin_type_id} was not found."}), 404
        return jsonify(_serialize_coin_type(coin_type)), 200

    return app


def _serialize_coin_type(coin_type: object) -> dict[str, object]:
    """Return immutable reference data as JSON, including source provenance."""
    return {
        field: getattr(coin_type, field)
        for field in (
            "id",
            "external_id",
            "reference_label",
            "authority",
            "mint",
            "denomination",
            "material",
            "date_start",
            "date_end",
            "obverse_legend",
            "reverse_legend",
            "obverse_description",
            "reverse_description",
            "source_url",
            "source_name",
            "original_reference",
            "source_attribution",
            "source_license",
        )
    }


def main(argv: Sequence[str] | None = None) -> None:
    """Run the development server or create the repeatable local database schema."""
    parser = argparse.ArgumentParser(description="Roman Coin Atlas")
    subcommands = parser.add_subparsers(dest="command")

    init_database_parser = subcommands.add_parser("init-db", help="Create or update the SQLite schema.")
    init_database_parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help="SQLite database path (default: database/roman_coin_atlas.sqlite)",
    )

    import_ocre_parser = subcommands.add_parser("import-ocre", help="Import a bounded pilot from OCRE NUDS/XML.")
    import_ocre_parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help="SQLite database path (default: database/roman_coin_atlas.sqlite)",
    )
    import_ocre_parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Number of OCRE records to request from the documented feed (1-200; default: 100).",
    )

    serve_parser = subcommands.add_parser("serve", help="Run the local Flask development server.")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=5000)

    arguments = parser.parse_args(argv)
    if arguments.command == "init-db":
        database_path = initialize_database(arguments.database)
        print(f"Database schema is ready at {database_path}")
        return
    if arguments.command == "import-ocre":
        repository_path = initialize_database(arguments.database)
        try:
            discovered_ids, records = OcreSourceAdapter().fetch_pilot(arguments.limit)
        except (OcreError, ValueError) as error:
            parser.exit(1, f"OCRE import failed: {error}\n")
        report = OcreImportService(CoinRepository(repository_path)).import_records(discovered_ids, records)
        print(
            "OCRE import completed: "
            f"{report.imported} imported, {report.duplicates} already present, "
            f"{report.parsed} parsed from {report.discovered} discovered records."
        )
        return

    app = create_app()
    app.run(
        debug=True,
        host=getattr(arguments, "host", "127.0.0.1"),
        port=getattr(arguments, "port", 5000),
    )


if __name__ == "__main__":
    main()
