"""Localized legend reading aids and OCRE image descriptions for result cards.

The imported Latin legends and OCRE source descriptions remain unchanged.
Legend output is a clearly labelled abbreviation-expansion aid, while OCRE
image descriptions are displayed for both available sides.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


SUPPORTED_LANGUAGES = frozenset({"de", "en"})


@dataclass(frozen=True)
class LegendReadingAid:
    """A localized expansion of one stored Latin inscription."""

    side: str
    title: str
    text: str


@dataclass(frozen=True)
class DescriptionReadingAid:
    """An available OCRE motif description for one side of a type."""

    side: str
    title: str
    text: str


@dataclass(frozen=True)
class CoinReadingAid:
    """All legend and descriptive reading aids shown on one result card."""

    legends: tuple[LegendReadingAid, ...]
    descriptions: tuple[DescriptionReadingAid, ...]
    legend_note: str | None
    description_note: str | None


def normalize_language(value: str | None) -> str:
    """Return one supported UI language, with English as a stable default."""
    normalized = (value or "en").strip().casefold()
    return normalized if normalized in SUPPORTED_LANGUAGES else "en"


def build_reading_aid(
    obverse_legend: str | None,
    reverse_legend: str | None,
    obverse_description: str | None,
    reverse_description: str | None,
    language: str,
) -> CoinReadingAid | None:
    """Build side-specific legend expansions and every available OCRE description."""
    normalized_language = normalize_language(language)
    legends = tuple(
        LegendReadingAid(
            side=side,
            title=_side_title(side, normalized_language, "legend"),
            text=translate_legend(legend, normalized_language),
        )
        for side, legend in (("obverse", obverse_legend), ("reverse", reverse_legend))
        if legend
    )
    descriptions = tuple(
        DescriptionReadingAid(
            side=side,
            title=_side_title(side, normalized_language, "description"),
            text=(translate_ocre_description_to_german(description) if normalized_language == "de" else description),
        )
        for side, description in (("obverse", obverse_description), ("reverse", reverse_description))
        if description
    )
    if not legends and not descriptions:
        return None
    return CoinReadingAid(
        legends=legends,
        descriptions=descriptions,
        legend_note=(
            "Automatische Legendenauflösung; keine zitierfähige RIC-Übersetzung."
            if normalized_language == "de"
            else "Automatic legend expansion; not a citable RIC translation."
        )
        if legends
        else None,
        description_note=(
            "OCRE-Bildbeschreibungen; deutsche Ausgabe als automatische Lesehilfe."
            if normalized_language == "de"
            else "OCRE source image descriptions."
        )
        if descriptions
        else None,
    )


def translate_legend(legend: str, language: str) -> str:
    """Expand frequent Roman legend abbreviations while leaving unknown tokens intact."""
    normalized_language = normalize_language(language)
    tokens = legend.split()
    expanded: list[str] = []
    index = 0
    while index < len(tokens):
        token = _normalize_legend_token(tokens[index])
        next_token = _normalize_legend_token(tokens[index + 1]) if index + 1 < len(tokens) else ""
        if token == "S" and next_token == "P" and _following_tokens(tokens, index, ("S", "P", "Q", "R")):
            expanded.append(_phrase("senate and people of Rome", "Senat und Volk von Rom", normalized_language))
            index += 4
        elif token == "S" and next_token == "C":
            expanded.append(_phrase("by decree of the Senate", "auf Senatsbeschluss", normalized_language))
            index += 2
        elif token == "P" and next_token == "M":
            expanded.append(_phrase("chief priest", "Oberpriester", normalized_language))
            index += 2
        elif token == "TR" and next_token == "P":
            expanded.append(_phrase("tribunician power", "tribunizische Gewalt", normalized_language))
            index += 2
        elif token == "PRO" and next_token == "PR":
            expanded.append(_phrase("pro-praetor", "Proprätor", normalized_language))
            index += 2
        elif token == "P" and next_token == "P":
            expanded.append(_phrase("father of the fatherland", "Vater des Vaterlandes", normalized_language))
            index += 2
        elif token == "P" and next_token == "CARISIVS":
            expanded.append("Publius")
            index += 1
        else:
            expanded.append(_token_translation(token, normalized_language) or tokens[index])
            index += 1
    return " ".join(expanded)


def translate_ocre_description_to_german(description: str) -> str:
    """Translate frequent OCRE iconography terms without modifying source data."""
    translated = description
    for english, german in _PHRASE_TRANSLATIONS:
        translated = re.sub(rf"\b{re.escape(english)}\b", german, translated, flags=re.IGNORECASE)
    return translated


def _side_title(side: str, language: str, kind: str) -> str:
    titles = {
        "en": {
            ("obverse", "legend"): "Obverse legend",
            ("reverse", "legend"): "Reverse legend",
            ("obverse", "description"): "OCRE obverse description",
            ("reverse", "description"): "OCRE reverse description",
        },
        "de": {
            ("obverse", "legend"): "Avers-Legende",
            ("reverse", "legend"): "Revers-Legende",
            ("obverse", "description"): "OCRE-Bildbeschreibung Avers",
            ("reverse", "description"): "OCRE-Bildbeschreibung Revers",
        },
    }
    return titles[language][(side, kind)]


def _following_tokens(tokens: list[str], start: int, expected: tuple[str, ...]) -> bool:
    return tuple(_normalize_legend_token(token) for token in tokens[start : start + len(expected)]) == expected


def _normalize_legend_token(token: str) -> str:
    return token.strip(".,;:()[]").upper()


def _phrase(english: str, german: str, language: str) -> str:
    return german if language == "de" else english


def _token_translation(token: str, language: str) -> str | None:
    translations = {
        "IMP": ("imperator", "Imperator"),
        "CAES": ("Caesar", "Caesar"),
        "CAESAR": ("Caesar", "Caesar"),
        "AVG": ("Augustus", "Augustus"),
        "AVGVST": ("Augustus", "Augustus"),
        "AVGVSTV": ("Augustus", "Augustus"),
        "AVGVSTO": ("Augustus", "Augustus"),
        "CARISIVS": ("Carisius", "Carisius"),
        "LEG": ("legate", "Legat"),
        "COS": ("consul", "Konsul"),
        "EMERITA": ("Emerita", "Emerita"),
    }
    translation = translations.get(token)
    if translation is None:
        return None
    return translation[1] if language == "de" else translation[0]


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
