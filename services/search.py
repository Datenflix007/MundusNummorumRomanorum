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
MAX_BOOLEAN_KEYWORD_TERMS = 8


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

    keyword, keyword_groups = _parse_keyword_expression(parameters.get("q"))
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
            keyword_groups=keyword_groups,
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


def _parse_keyword_expression(value: str | None) -> tuple[str | None, tuple[tuple[str, ...], ...]]:
    """Parse a small boolean query grammar while retaining literal search terms.

    ``&&`` requires both terms; ``||`` accepts either alternative. Parentheses
    and bare ampersands/pipes are deliberately rejected rather than interpreted
    ambiguously. Without an operator, a query remains the legacy partial phrase
    search.
    """
    keyword = _normalize_optional(value)
    if keyword is None:
        return None, ()
    if "(" in keyword or ")" in keyword:
        raise SearchValidationError("Keyword expressions do not support parentheses; use && and || from left to right.")
    if re.search(r"(?<!&)&(?!&)|(?<!\|)\|(?!\|)", keyword):
        raise SearchValidationError("Use && for AND and || for OR between complete keywords.")
    if "&&" not in keyword and "||" not in keyword:
        return keyword, ((keyword,),)

    alternatives = keyword.split("||")
    groups: list[tuple[str, ...]] = []
    for alternative in alternatives:
        terms = tuple(normalize_search_keyword(term) for term in alternative.split("&&"))
        if not all(terms):
            raise SearchValidationError("Each && or || must have a keyword on both sides.")
        groups.append(terms)

    if sum(len(group) for group in groups) > MAX_BOOLEAN_KEYWORD_TERMS:
        raise SearchValidationError(f"A keyword expression may contain at most {MAX_BOOLEAN_KEYWORD_TERMS} terms.")
    return keyword, tuple(groups)


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
