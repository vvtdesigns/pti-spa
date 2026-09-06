"""
Turns an uploaded statistics sheet (Excel/CSV, or a fallback PDF export in the
same layout Massar's operations system produces) into a list of clean,
per-station metric dictionaries ready to save to the database.

Design goal: be forgiving about the exact column names / header wording,
since real-world exports drift slightly (extra spaces, "إعادة الفحص 1" vs
"إعادة فحص1", English vs Arabic headers, etc).
"""
from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


@dataclass
class StationRow:
    station_name: str
    appointments: int = 0
    attendance: int = 0
    absence: int = 0
    first_time: int = 0
    retest_1: int = 0
    retest_2: int = 0
    passed: int = 0
    failed: int = 0


@dataclass
class ParseResult:
    rows: list[StationRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# Canonical field -> list of header spellings we should recognize (normalized:
# lowercased, extra whitespace collapsed, Arabic presentation forms folded).
HEADER_ALIASES: dict[str, list[str]] = {
    "station_name": ["المحطة", "اسم المحطة", "station", "station name"],
    "appointments": ["المواعيد", "appointments", "booked"],
    "attendance": ["الحضور", "attendance", "attended"],
    "absence": ["الغياب", "absence", "no show", "no-show", "noshow"],
    "first_time": ["لأول مرة", "أول مرة", "first time", "first_time"],
    "retest_1": ["إعادة الفحص 1", "إعادة فحص 1", "إعادة الفحص1", "retest 1", "retest1", "re-test 1"],
    "retest_2": ["إعادة الفحص 2", "إعادة فحص 2", "إعادة الفحص2", "retest 2", "retest2", "re-test 2"],
    "passed": ["ناجحة", "المركبات الناجحة", "passed", "pass"],
    "failed": ["راسبة", "المركبات الراسبة", "failed", "fail"],
}


def _normalize_header(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s))
    s = s.replace("‏", "").replace("‎", "")
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


_ALIAS_LOOKUP: dict[str, str] = {}
for canon, aliases in HEADER_ALIASES.items():
    for a in aliases:
        _ALIAS_LOOKUP[_normalize_header(a)] = canon


def _to_int(v) -> int:
    if v is None:
        return 0
    if isinstance(v, (int, float)):
        if pd.isna(v):
            return 0
        return int(round(v))
    s = str(v).strip().replace(",", "")
    if s == "" or s.lower() == "nan":
        return 0
    try:
        return int(round(float(s)))
    except ValueError:
        return 0


def parse_spreadsheet(file_bytes: bytes, filename: str) -> ParseResult:
    """Parse an uploaded .xlsx/.xls/.csv statistics sheet."""
    result = ParseResult()
    buf = io.BytesIO(file_bytes)

    if filename.lower().endswith(".csv"):
        df = pd.read_csv(buf)
    else:
        df = pd.read_excel(buf)

    # Map whatever headers are present onto our canonical field names.
    colmap: dict[str, str] = {}
    for col in df.columns:
        norm = _normalize_header(col)
        if norm in _ALIAS_LOOKUP:
            colmap[col] = _ALIAS_LOOKUP[norm]

    if "station_name" not in colmap.values():
        result.warnings.append(
            "Could not find a station-name column. Expected a column called "
            "'المحطة' (or 'Station'). No rows were imported."
        )
        return result

    df = df.rename(columns=colmap)
    missing = [f for f in HEADER_ALIASES if f not in df.columns]
    if missing:
        result.warnings.append(
            "These columns were not found and were treated as 0: " + ", ".join(missing)
        )

    for _, row in df.iterrows():
        name = str(row.get("station_name", "")).strip()
        if not name or name.lower() == "nan":
            continue
        # Skip an obvious "total" row -- totals are computed by the app itself.
        if _normalize_header(name) in {"الإجمالي", "الاجمالي", "total", "grand total"}:
            continue
        result.rows.append(
            StationRow(
                station_name=unicodedata.normalize("NFKC", name),
                appointments=_to_int(row.get("appointments")),
                attendance=_to_int(row.get("attendance")),
                absence=_to_int(row.get("absence")),
                first_time=_to_int(row.get("first_time")),
                retest_1=_to_int(row.get("retest_1")),
                retest_2=_to_int(row.get("retest_2")),
                passed=_to_int(row.get("passed")),
                failed=_to_int(row.get("failed")),
            )
        )

    if not result.rows:
        result.warnings.append("No station rows were found in the file.")

    return result


# ---------------------------------------------------------------------------
# PDF fallback parser
# ---------------------------------------------------------------------------
# Massar's own "Operations Department Report" PDF export lays its station
# table out with these columns, left-to-right on the page (this is a
# right-to-left report, so physically-first column on the page is the
# right-most conceptually):
#   نجاح% | راسبة | ناجحة | إعادة الفحص 2 | إعادة الفحص 1 | لأول مرة | الغياب | الحضور | المواعيد | المحطة
#
# pdfplumber often can't split each station's row into separate cells (no
# visible cell borders) and instead returns the whole row as one
# space-joined string in the first column, with the Arabic station name at
# the end -- and because of how the PDF stores RTL glyphs, that name comes
# out both word-reversed and character-reversed. Reversing the whole string
# and then Unicode-normalizing (NFKC) reliably restores the real name, which
# we verified against this exact report layout.
NUMERIC_FIELDS_LTR_ORDER = [
    "pass_pct", "failed", "passed", "retest_2", "retest_1",
    "first_time", "absence", "attendance", "appointments",
]


def _fix_rtl_fragment(s: str) -> str:
    return unicodedata.normalize("NFKC", s[::-1]).strip()


def parse_operations_pdf(file_bytes: bytes) -> ParseResult:
    import pdfplumber

    result = ParseResult()
    buf = io.BytesIO(file_bytes)

    with pdfplumber.open(buf) as pdf:
        # The station-performance table is, page over page, the one with the
        # most rows (cover/KPI pages extract as a handful of big single-cell
        # blocks). We can't reliably match on the Arabic title text here
        # because pdfplumber often returns it word- and glyph-reversed.
        best_table = None
        for page in pdf.pages:
            for tbl in page.extract_tables():
                if best_table is None or len(tbl) > len(best_table):
                    best_table = tbl

        if best_table is None or len(best_table) < 3:
            result.warnings.append(
                "Couldn't find a station-performance table in this PDF. "
                "An Excel/CSV export is more reliable -- see the Upload page for the expected columns."
            )
            return result

        t = best_table
        for raw_row in t:
            cells = [c for c in raw_row if c is not None and str(c).strip() != ""]
            if not cells:
                continue
            # Header / already-split rows (each field its own cell): last cell is the name.
            if len(cells) >= 10:
                *nums, name_cell = cells[:10]
                name = _fix_rtl_fragment(name_cell) if _looks_reversed(name_cell) else name_cell.strip()
                if _normalize_row_is_header_or_total(name):
                    if _normalize_header(name) in {"الإجمالي", "الاجمالي"}:
                        continue
                    else:
                        continue
                values = _parse_numeric_list(nums)
                if values:
                    result.rows.append(_row_from_values(name, values))
                continue

            # Merged single-string row: "<9 numeric tokens> <reversed station name tokens>"
            raw = cells[0]
            tokens = raw.split()
            if len(tokens) < len(NUMERIC_FIELDS_LTR_ORDER) + 1:
                continue
            nums = tokens[: len(NUMERIC_FIELDS_LTR_ORDER)]
            name_tokens = tokens[len(NUMERIC_FIELDS_LTR_ORDER):]
            name = _fix_rtl_fragment(" ".join(name_tokens))
            if _normalize_row_is_header_or_total(name):
                continue
            values = _parse_numeric_list(nums)
            if not values:
                continue
            result.rows.append(_row_from_values(name, values))

    if not result.rows:
        result.warnings.append("No station rows could be parsed from this PDF.")

    return result


def _looks_reversed(s: str) -> bool:
    # Presentation-form Arabic glyphs (used when a word/ligature comes out reversed)
    # live in the U+FB50-FDFF / U+FE70-FEFF ranges.
    return any("ﭐ" <= ch <= "﻿" for ch in s)


def _normalize_row_is_header_or_total(name: str) -> bool:
    n = _normalize_header(name)
    return n in {"المحطة", "الإجمالي", "الاجمالي", "total"}


_NUMERIC_TOKEN_RE = re.compile(r"^\d{1,3}(,\d{3})*(\.\d+)?%?$|^\d+(\.\d+)?%?$")


def _parse_numeric_list(tokens: list[str]) -> Optional[dict]:
    if len(tokens) != len(NUMERIC_FIELDS_LTR_ORDER):
        return None
    # Guard against stray header/footer text rows: every token here must
    # actually look like a number (plain or comma-grouped, optional %).
    if not all(_NUMERIC_TOKEN_RE.match(tok) for tok in tokens):
        return None
    out = {}
    for field_name, tok in zip(NUMERIC_FIELDS_LTR_ORDER, tokens):
        if field_name == "pass_pct":
            continue
        out[field_name] = _to_int(tok)
    return out


def _row_from_values(name: str, values: dict) -> StationRow:
    return StationRow(
        station_name=name,
        appointments=values.get("appointments", 0),
        attendance=values.get("attendance", 0),
        absence=values.get("absence", 0),
        first_time=values.get("first_time", 0),
        retest_1=values.get("retest_1", 0),
        retest_2=values.get("retest_2", 0),
        passed=values.get("passed", 0),
        failed=values.get("failed", 0),
    )


def parse_upload(file_bytes: bytes, filename: str) -> ParseResult:
    """Entry point used by the Streamlit Upload page: dispatches on extension."""
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return parse_operations_pdf(file_bytes)
    return parse_spreadsheet(file_bytes, filename)


def build_template_dataframe() -> pd.DataFrame:
    """The column template the Upload page offers as a downloadable example."""
    cols = ["المحطة", "المواعيد", "الحضور", "الغياب", "لأول مرة",
            "إعادة الفحص 1", "إعادة الفحص 2", "ناجحة", "راسبة"]
    sample = [
        ["الرياض - المنار", 14870, 12649, 2231, 10734, 3508, 1167, 8062, 4587],
        ["الخبر - الثقبة", 12806, 11315, 1515, 8357, 2518, 440, 7918, 3397],
    ]
    return pd.DataFrame(sample, columns=cols)
