"""Deterministic tests for legend and description reading aids."""

from services.reading_aids import build_reading_aid, normalize_language, translate_legend


def test_normalize_language_defaults_to_english_for_unknown_values() -> None:
    assert normalize_language("DE") == "de"
    assert normalize_language("fr") == "en"
    assert normalize_language(None) == "en"


def test_reading_aid_translates_both_legends_and_keeps_both_ocra_descriptions() -> None:
    reading_aid = build_reading_aid(
        "IMP CAESAR AVGVSTV",
        "P CARISIVS LEG PRO PR EMERITA",
        "Head of Augustus, bare, right",
        "City wall, gateway",
        "en",
    )

    assert reading_aid is not None
    assert [legend.title for legend in reading_aid.legends] == ["Obverse legend", "Reverse legend"]
    assert reading_aid.legends[0].text == "imperator Caesar Augustus"
    assert reading_aid.legends[1].text == "Publius Carisius legate pro-praetor Emerita"
    assert [description.text for description in reading_aid.descriptions] == [
        "Head of Augustus, bare, right",
        "City wall, gateway",
    ]


def test_german_reading_aid_marks_legend_expansion_and_translates_ocra_descriptions() -> None:
    reading_aid = build_reading_aid(
        "IMP CAESAR AVGVSTV",
        "S C",
        "Laureate bust right",
        "Minerva, standing right, holding spear and shield",
        "de",
    )

    assert reading_aid is not None
    assert [legend.title for legend in reading_aid.legends] == ["Avers-Legende", "Revers-Legende"]
    assert reading_aid.legends[0].text == "Imperator Caesar Augustus"
    assert reading_aid.legends[1].text == "auf Senatsbeschluss"
    assert reading_aid.descriptions[1].text == "Minerva, nach rechts stehend, haltend Speer und Schild"
    assert reading_aid.legend_note is not None


def test_legend_translation_leaves_unknown_tokens_visible_instead_of_guessing() -> None:
    assert translate_legend("IMP UNKNOWN XII", "de") == "Imperator UNKNOWN XII"
