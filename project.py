"""Application entry point and shared normalization helpers for Roman Coin Atlas."""

from __future__ import annotations

from typing import Final

from flask import Flask, jsonify


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


def normalize_keyword(text: str) -> str:
    """Return a case-insensitive search expression with one space between words."""
    if not isinstance(text, str):
        raise TypeError("Search text must be a string.")

    return " ".join(text.split()).casefold()


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


def create_app() -> Flask:
    """Create the Flask application without requiring a database connection."""
    app = Flask(__name__)

    @app.get("/health")
    def health() -> tuple[object, int]:
        return jsonify(status="ok", service="roman-coin-atlas"), 200

    return app


def main() -> None:
    """Run the local development server."""
    app = create_app()
    app.run(debug=True)


if __name__ == "__main__":
    main()
