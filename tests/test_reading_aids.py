"""Deterministic tests for localized OCRE motif reading aids."""

from services.reading_aids import build_reading_aid, normalize_language, translate_ocre_description_to_german


def test_normalize_language_defaults_to_english_for_unknown_values() -> None:
    assert normalize_language("DE") == "de"
    assert normalize_language("fr") == "en"
    assert normalize_language(None) == "en"


def test_reading_aid_prefers_reverse_and_keeps_english_ocre_source_text() -> None:
    reading_aid = build_reading_aid("Laureate bust right", "Minerva, standing right, holding spear", "en")

    assert reading_aid is not None
    assert reading_aid.side == "reverse"
    assert reading_aid.title == "Reverse"
    assert reading_aid.description == "Minerva, standing right, holding spear"


def test_german_reading_aid_is_a_labeled_translation_of_the_ocra_description() -> None:
    reading_aid = build_reading_aid(None, "Minerva, standing right, holding spear and shield", "de")

    assert reading_aid is not None
    assert reading_aid.title == "Revers"
    assert reading_aid.description == "Minerva, nach rechts stehend, haltend Speer und Schild"
    assert reading_aid.note is not None


def test_german_translation_keeps_unknown_terms_visible_instead_of_guessing() -> None:
    assert translate_ocre_description_to_german("Unknown cult object, standing left") == "Unknown cult object, nach links stehend"
