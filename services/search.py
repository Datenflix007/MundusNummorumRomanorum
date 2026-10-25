"""Request parsing and validation for the coin-type search API."""

from __future__ import annotations

import re
from collections.abc import Mapping

from database.repository import CoinSearchCriteria


class SearchValidationError(ValueError):
    """An API query value is missing, malformed, or outside an accepted range."""


SORT_OPTIONS = frozenset({"reference", "authority", "mint", "date_start", "date_end"})
ORDER_OPTIONS = frozenset({"asc", "desc"})
MAX_PAGE_SIZE = 100


def normalize_search_keyword(text: str) -> str:
    """Normalize user input while leaving historical source fields untouched."""
    if not isinstance(text, str):
        raise SearchValidationError("Search keywords must be text.")
    return " ".join(text.split()).casefold()


def parse_search_parameters(parameters: Mapping[str, str]) -> tuple[CoinSearchCriteria, int]:
    """Build validated search criteria and a one-based API page number."""
    start_year = _parse_year(parameters.get("start_year"), "start_year")
    end_year = _parse_year(parameters.get("end_year"), "end_year")
    if start_year is not None and end_year is not None and start_year > end_year:
        raise SearchValidationError("start_year must not be after end_year.")

    keyword = _normalize_optional(parameters.get("q"))
    limit = _parse_bounded_int(parameters.get("limit"), "limit", default=25, minimum=1, maximum=MAX_PAGE_SIZE)
    page = _parse_bounded_int(parameters.get("page"), "page", default=1, minimum=1, maximum=None)
    sort = parameters.get("sort", "reference").strip().casefold()
    order = parameters.get("order", "asc").strip().casefold()
    if sort not in SORT_OPTIONS:
        raise SearchValidationError(f"sort must be one of: {', '.join(sorted(SORT_OPTIONS))}.")
    if order not in ORDER_OPTIONS:
        raise SearchValidationError("order must be either asc or desc.")

    return (
        CoinSearchCriteria(
            keyword=keyword,
            start_year=start_year,
            end_year=end_year,
            material=_normalize_optional(parameters.get("material")),
            denomination=_normalize_optional(parameters.get("denomination")),
            authority=_normalize_optional(parameters.get("authority")),
            mint=_normalize_optional(parameters.get("mint")),
            sort=sort,
            descending=order == "desc",
            limit=limit,
            offset=(page - 1) * limit,
        ),
        page,
    )


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = normalize_search_keyword(value)
    return normalized or None


def _parse_year(value: str | None, name: str) -> int | None:
    if value is None or not value.strip():
        return None
    if not re.fullmatch(r"-?[0-9]+", value.strip()):
        raise SearchValidationError(f"{name} must be a whole historical year.")
    year = int(value)
    if year == 0:
        raise SearchValidationError(f"{name} cannot be year zero.")
    return year


def _parse_bounded_int(
    value: str | None, name: str, *, default: int, minimum: int, maximum: int | None
) -> int:
    if value is None or not value.strip():
        return default
    if not value.isdigit():
        raise SearchValidationError(f"{name} must be a positive whole number.")
    parsed = int(value)
    if parsed < minimum or (maximum is not None and parsed > maximum):
        upper_bound = f" and at most {maximum}" if maximum is not None else ""
        raise SearchValidationError(f"{name} must be at least {minimum}{upper_bound}.")
    return parsed
