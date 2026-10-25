"""Localized reading aids derived from OCRE's English motif descriptions.

These helpers never alter an imported legend or source description. German
output is explicitly a UI reading aid, not a new scholarly translation or RIC
reference field.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


SUPPORTED_LANGUAGES = frozenset({"de", "en"})


@dataclass(frozen=True)
class CoinReadingAid:
    """One localized OCRE motif description for a search-result card."""

    side: str
    title: str
    description: str
    note: str | None


def normalize_language(value: str | None) -> str:
    """Return one supported UI language, with English as a stable default."""
    normalized = (value or "en").strip().casefold()
    return normalized if normalized in SUPPORTED_LANGUAGES else "en"


def build_reading_aid(
    obverse_description: str | None, reverse_description: str | None, language: str
) -> CoinReadingAid | None:
    """Choose a reverse-first OCRE motif description and localize its display."""
    normalized_language = normalize_language(language)
    if reverse_description:
        side = "reverse"
        source_description = reverse_description
    elif obverse_description:
        side = "obverse"
        source_description = obverse_description
    else:
        return None

    if normalized_language == "de":
        return CoinReadingAid(
            side=side,
            title="Revers" if side == "reverse" else "Avers",
            description=translate_ocre_description_to_german(source_description),
            note="Automatische Lesehilfe auf Basis der englischen OCRE-Beschreibung.",
        )
    return CoinReadingAid(
        side=side,
        title="Reverse" if side == "reverse" else "Obverse",
        description=source_description,
        note="OCRE source description.",
    )


def translate_ocre_description_to_german(description: str) -> str:
    """Translate frequent OCRE iconography terms without modifying source data.

    Unknown terms intentionally remain visible in English rather than being
    guessed. This keeps the reading aid useful while preserving provenance.
    """
    translated = description
    for english, german in _PHRASE_TRANSLATIONS:
        translated = re.sub(rf"\b{re.escape(english)}\b", german, translated, flags=re.IGNORECASE)
    return translated


_PHRASE_TRANSLATIONS: tuple[tuple[str, str], ...] = (
    ("standing right", "nach rechts stehend"),
    ("standing left", "nach links stehend"),
    ("seated right", "nach rechts sitzend"),
    ("seated left", "nach links sitzend"),
    ("riding right", "nach rechts reitend"),
    ("riding left", "nach links reitend"),
    ("head of", "Kopf des"),
    ("bust of", "Büste des"),
    ("bare", "unbedeckt"),
    ("laureate", "lorbeerbekränzt"),
    ("radiate", "strahlenbekränzt"),
    ("draped", "drapiert"),
    ("cuirassed", "gepanzert"),
    ("helmeted", "behelmt"),
    ("diademed", "diademiert"),
    ("holding", "haltend"),
    ("leaning", "gelehnt"),
    ("with", "mit"),
    ("and", "und"),
    ("spear", "Speer"),
    ("shield", "Schild"),
    ("wreath", "Kranz"),
    ("globe", "Globus"),
    ("branch", "Zweig"),
    ("eagle", "Adler"),
    ("horse", "Pferd"),
    ("Victory", "Victoria"),
    ("City wall", "Stadtmauer"),
    ("gateway", "Tor"),
    ("right", "rechts"),
    ("left", "links"),
)
