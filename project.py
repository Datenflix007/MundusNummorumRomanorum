"""Application entry point and shared normalization helpers for Roman Coin Atlas."""

from __future__ import annotations

import argparse
from time import monotonic
from pathlib import Path
from typing import Final, Sequence

from flask import Flask, jsonify, render_template, request

from database.repository import CoinRepository, DatabaseRequestError, initialize_database
from services.ocre import OcreCoinTypeRecord, OcreError, OcreImportService, OcreSourceAdapter
from services.ocre_images import OcreImageAdapter, OcreImageError
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
OCRE_IMAGE_CACHE_SECONDS: Final[float] = 600.0
OCRE_IMAGE_CACHE_LIMIT: Final[int] = 256


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
    app.config["OCRE_IMAGE_ADAPTER_FACTORY"] = OcreImageAdapter
    app.extensions["ocre_image_preview_cache"] = {}

    @app.get("/health")
    def health() -> tuple[object, int]:
        return jsonify(status="ok", service="roman-coin-atlas"), 200

    @app.get("/")
    def search_page() -> str:
        return render_template("search.html", filters=_search_filters(request.args))

    @app.get("/results")
    def results_page() -> tuple[str, int] | str:
        filters = _search_filters(request.args)
        try:
            criteria, page_number = parse_search_parameters(request.args.to_dict(flat=True))
        except SearchValidationError as error:
            return render_template("results.html", filters=filters, error=str(error), results=None), 400

        try:
            results = CoinRepository(app.config["DATABASE_PATH"]).search_coin_types(criteria)
        except DatabaseRequestError as error:
            return render_template("results.html", filters=filters, error=str(error), results=None), 500
        return render_template(
            "results.html",
            filters=filters,
            error=None,
            results=results,
            page_number=page_number,
            page_count=(results.total + criteria.limit - 1) // criteria.limit,
            limit=criteria.limit,
        )

    @app.get("/coins/<int:coin_type_id>")
    def coin_page(coin_type_id: int) -> tuple[str, int] | str:
        try:
            coin_type = CoinRepository(app.config["DATABASE_PATH"]).get_coin_type(coin_type_id)
        except Exception:
            return render_template("error.html", message="The coin catalog could not be read."), 500
        if coin_type is None:
            return render_template("error.html", message=f"Coin type {coin_type_id} was not found."), 404
        return render_template("coin_detail.html", coin_type=coin_type)

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

    @app.get("/api/coins/<int:coin_type_id>/images")
    def coin_image_previews(coin_type_id: int) -> tuple[object, int]:
        """Fetch attributed specimen previews only after a user requests them."""
        try:
            coin_type = CoinRepository(app.config["DATABASE_PATH"]).get_coin_type(coin_type_id)
        except Exception:
            return jsonify(error={"code": "database_error", "message": "The coin catalog could not be read."}), 500
        if coin_type is None:
            return jsonify(error={"code": "not_found", "message": f"Coin type {coin_type_id} was not found."}), 404

        cache: dict[int, tuple[float, list[dict[str, str | None]]]] = app.extensions["ocre_image_preview_cache"]
        cached = cache.get(coin_type_id)
        if cached and monotonic() - cached[0] < OCRE_IMAGE_CACHE_SECONDS:
            return jsonify(items=cached[1], cached=True), 200

        try:
            adapter_factory = app.config["OCRE_IMAGE_ADAPTER_FACTORY"]
            previews = adapter_factory().fetch_previews(coin_type.source_url)
        except OcreImageError as error:
            return jsonify(error={"code": "image_source_unavailable", "message": str(error)}), 502

        items = [preview.as_dict() for preview in previews]
        if len(cache) >= OCRE_IMAGE_CACHE_LIMIT:
            oldest_key = min(cache, key=lambda key: cache[key][0])
            del cache[oldest_key]
        cache[coin_type_id] = (monotonic(), items)
        return jsonify(items=items, cached=False), 200

    return app


def _search_filters(arguments: object) -> dict[str, str]:
    """Keep submitted form values visible without normalizing source catalog text."""
    allowed_names = ("q", "start_year", "end_year", "material", "denomination", "authority", "mint", "sort", "order")
    return {name: getattr(arguments, "get")(name, "") for name in allowed_names}


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

    import_ocre_parser = subcommands.add_parser("import-ocre", help="Import OCRE coin types from canonical NUDS/XML.")
    import_ocre_parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help="SQLite database path (default: database/roman_coin_atlas.sqlite)",
    )
    import_selection = import_ocre_parser.add_mutually_exclusive_group()
    import_selection.add_argument(
        "--limit",
        type=int,
        help="Number of OCRE pilot records from the documented feed (1-200; default: 100).",
    )
    import_selection.add_argument(
        "--full",
        action="store_true",
        help="Import the complete published OCRE catalog; this can take a substantial time.",
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
        adapter = OcreSourceAdapter()
        importer = OcreImportService(CoinRepository(repository_path))
        try:
            if arguments.full:
                def full_batches() -> Iterable[tuple[list[str], list[OcreCoinTypeRecord]]]:
                    discovered_count = 0
                    for record_ids in adapter.iter_full_record_id_batches(batch_size=100):
                        discovered_count += len(record_ids)
                        if discovered_count % 500 == 0:
                            print(f"OCRE full import: fetched {discovered_count} canonical identifiers...", flush=True)
                        yield record_ids, adapter.fetch_records(record_ids, batch_size=100)

                report = importer.import_batches(full_batches())
            else:
                discovered_ids, records = adapter.fetch_pilot(arguments.limit or 100)
                report = importer.import_records(discovered_ids, records)
        except (OcreError, ValueError) as error:
            parser.exit(1, f"OCRE import failed: {error}\n")
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
