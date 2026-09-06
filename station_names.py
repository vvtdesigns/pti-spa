"""
Arabic <-> English station name handling.

The rule this exists to enforce: an Arabic report must contain zero English
words, and an English report must contain zero Arabic words -- including
station names. Since station names are proper nouns with no automatic
"correct" translation, we keep a curated mapping for every station we've
actually seen, and require a human-entered English name for any new one
(the Upload page prompts for it) rather than ever falling back to a raw
transliteration in a finished report.
"""
from __future__ import annotations

# Curated from Massar United Co.'s actual station list.
KNOWN_STATION_NAMES_EN: dict[str, str] = {
    "الدرب - د": "Al Darb - D",
    "بدر - ب": "Badr - B",
    "الرياض - السعادة": "Riyadh - Al Saadah",
    "المدينة المنورة - العاقول": "Madinah - Al Aqoul",
    "الخبر - الثقبة": "Al Khobar - Al Thuqbah",
    "الرياض - جامعة الملك سعود": "Riyadh - King Saud University",
    "الرياض - المنار": "Riyadh - Al Manar",
    "شرورة - ش": "Sharurah - Sh",
    "حوطة بني تميم - ح": "Hotat Bani Tamim - H",
}


def suggest_english_name(name_ar: str) -> str:
    """A rough starting point for the Upload page's text box -- never used
    directly in a report. The person uploading should correct/confirm it."""
    if name_ar in KNOWN_STATION_NAMES_EN:
        return KNOWN_STATION_NAMES_EN[name_ar]
    try:
        from unidecode import unidecode
        guess = unidecode(name_ar).strip(" -")
        return guess.title() if guess else ""
    except Exception:
        return ""
