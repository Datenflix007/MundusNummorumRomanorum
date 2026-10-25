"""Tests for the pure helper functions required by the CS50P project."""

import pytest

from project import normalize_keyword, normalize_material, validate_year_range


@pytest.mark.parametrize(
    ("raw_text", "expected"),
    [
        ("  IMPERATOR   CAESAR ", "imperator caesar"),
        ("Septimius\tSeverus\n", "septimius severus"),
        ("", ""),
    ],
)
def test_normalize_keyword(raw_text: str, expected: str) -> None:
    assert normalize_keyword(raw_text) == expected


def test_normalize_keyword_rejects_non_string() -> None:
    with pytest.raises(TypeError):
        normalize_keyword(None)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (-27, 14, (-27, 14)),
        (-1, 1, (-1, 1)),
        (69, 69, (69, 69)),
    ],
)
def test_validate_year_range(start: int, end: int, expected: tuple[int, int]) -> None:
    assert validate_year_range(start, end) == expected


@pytest.mark.parametrize(("start", "end"), [(0, 1), (-1, 0), (10, 9)])
def test_validate_year_range_rejects_invalid_interval(start: int, end: int) -> None:
    with pytest.raises(ValueError):
        validate_year_range(start, end)


def test_validate_year_range_rejects_non_integer_year() -> None:
    with pytest.raises(TypeError):
        validate_year_range(1.0, 2)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        (" AV ", "gold"),
        ("ar", "silver"),
        ("Copper   Alloy", "bronze"),
        ("billon", "billon"),
    ],
)
def test_normalize_material(label: str, expected: str) -> None:
    assert normalize_material(label) == expected


@pytest.mark.parametrize("material", ["iron", "", "  "])
def test_normalize_material_rejects_unsupported_value(material: str) -> None:
    with pytest.raises(ValueError):
        normalize_material(material)


def test_normalize_material_rejects_non_string() -> None:
    with pytest.raises(TypeError):
        normalize_material(None)  # type: ignore[arg-type]
