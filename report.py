"""
Builds the executive PDF report: fills the Jinja2 HTML template with the
analysis results and renders it to PDF bytes with WeasyPrint.
"""
from __future__ import annotations

import base64
import datetime as dt
import math
import os

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

from analysis import PeriodAnalysis, StationTrend

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
_FONT_DIR = os.path.join(os.path.dirname(__file__), "assets", "fonts")

_AR_MONTHS = {
    1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل", 5: "مايو", 6: "يونيو",
    7: "يوليو", 8: "أغسطس", 9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر",
}
_EN_MONTHS = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}


def format_period(start: dt.date | None, end: dt.date | None, lang: str, fallback: str = "") -> str:
    """A period range with month names in the report's own language only --
    never falls back to a free-text label, which could contain the other
    language."""
    if start is None or end is None:
        return fallback
    if lang == "ar":
        months = _AR_MONTHS
        if start.year == end.year and start.month == end.month:
            return f"{start.day} - {end.day} {months[start.month]} {start.year}"
        if start.year == end.year:
            return f"{start.day} {months[start.month]} - {end.day} {months[end.month]} {start.year}"
        return f"{start.day} {months[start.month]} {start.year} - {end.day} {months[end.month]} {end.year}"
    else:
        months = _EN_MONTHS
        if start.year == end.year and start.month == end.month:
            return f"{months[start.month]} {start.day} - {end.day}, {start.year}"
        if start.year == end.year:
            return f"{months[start.month]} {start.day} - {months[end.month]} {end.day}, {start.year}"
        return f"{months[start.month]} {start.day}, {start.year} - {months[end.month]} {end.day}, {end.year}"

LABELS = {
    "ar": {
        "company_name": None,  # filled in from Settings
        "report_title": "تقرير أداء محطات الفحص الدوري",
        "report_subtitle": "تقرير تنفيذي — مقارنات الأداء والاتجاهات",
        "footer_title": "تقرير أداء محطات الفحص الدوري",
        "page": "صفحة",
        "period": "الفترة",
        "stations_count": "عدد المحطات",
        "generated_on": "تاريخ الإنشاء",
        "executive_summary": "الملخص التنفيذي",
        "kpi_title": "مؤشرات الأداء الرئيسية",
        "trend_title": "الاتجاه عبر الفترات",
        "station_table_title": "أداء المحطات",
        "table_change_note": "الأرقام الصغيرة تحت كل قيمة تمثل نسبة التغير مقارنة بالفترة السابقة",
        "charts_title": "الرسوم البيانية",
        "chart_pass_rate": "نسبة النجاح حسب المحطة",
        "chart_volume": "المواعيد مقابل الحضور حسب المحطة",
        "flags_title": "نقاط الضعف والفرص",
        "no_flags": "لا توجد ملاحظات تستدعي الانتباه في هذه الفترة.",
        "total": "الإجمالي",
        "col_station": "المحطة", "col_appointments": "المواعيد", "col_attendance": "الحضور",
        "col_absence": "الغياب", "col_first_time": "لأول مرة", "col_retest1": "إعادة فحص 1",
        "col_retest2": "إعادة فحص 2", "col_passed": "ناجحة", "col_failed": "راسبة",
        "col_pass_pct": "نجاح %", "col_pass_delta": "تغير % النجاح",
        "kpi_appointments": "المواعيد", "kpi_attendance": "الحضور", "kpi_absence": "الغياب",
        "kpi_passed": "المركبات الناجحة", "kpi_failed": "المركبات الراسبة",
        "kpi_pass_pct": "نسبة النجاح", "kpi_complaints": "الشكاوى", "kpi_absher": "نجاح أبشر",
        "tag_risk": "خطر", "tag_opportunity": "فرصة", "tag_positive": "إيجابي",
        "vs_prev": "مقارنة بالفترة السابقة",
    },
    "en": {
        "company_name": None,
        "report_title": "PTI Stations Performance Report",
        "report_subtitle": "Executive report — performance comparisons & trends",
        "footer_title": "PTI Stations Performance Report",
        "page": "Page",
        "period": "Period",
        "stations_count": "Stations",
        "generated_on": "Generated on",
        "executive_summary": "Executive Summary",
        "kpi_title": "Key Performance Indicators",
        "trend_title": "Trend Across Periods",
        "station_table_title": "Station Performance",
        "table_change_note": "The small figure under each value is the % change versus the previous period",
        "charts_title": "Charts",
        "chart_pass_rate": "Pass rate by station",
        "chart_volume": "Appointments vs. attendance by station",
        "flags_title": "Weak Points & Opportunities",
        "no_flags": "No items need attention this period.",
        "total": "Total",
        "col_station": "Station", "col_appointments": "Appointments", "col_attendance": "Attendance",
        "col_absence": "Absence", "col_first_time": "First-time", "col_retest1": "Retest 1",
        "col_retest2": "Retest 2", "col_passed": "Passed", "col_failed": "Failed",
        "col_pass_pct": "Pass %", "col_pass_delta": "Pass % Change",
        "kpi_appointments": "Appointments", "kpi_attendance": "Attendance", "kpi_absence": "Absence",
        "kpi_passed": "Vehicles passed", "kpi_failed": "Vehicles failed",
        "kpi_pass_pct": "Pass rate", "kpi_complaints": "Complaints", "kpi_absher": "Absher success",
        "tag_risk": "Risk", "tag_opportunity": "Opportunity", "tag_positive": "Positive",
        "vs_prev": "vs previous period",
    },
}


def _b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def _fmt_int(n) -> str:
    return f"{int(round(n)):,}"


def _pass_class(pct: float) -> str:
    if pct >= 70:
        return "pass-good"
    if pct >= 60:
        return "pass-mid"
    return "pass-bad"


def _field_delta_str(delta_pct, is_rtl: bool, direction: str = "up"):
    """
    Format a raw-count field's period-over-period % change.
    direction: "up" = an increase is good news (green), "down" = an increase
    is bad news (red, e.g. Absence/Failed/Retest), "neutral" = always gray.
    """
    if delta_pct is None:
        return None, "delta-flat"
    if abs(delta_pct) < 0.05:
        return ("0.0%", "delta-flat")
    arrow = "▲" if delta_pct > 0 else "▼"
    text = f"{arrow} {abs(delta_pct):.1f}%"
    if direction == "neutral":
        cls = "delta-flat"
    elif direction == "up":
        cls = "delta-up" if delta_pct > 0 else "delta-down"
    else:  # "down" -- increase is bad
        cls = "delta-down" if delta_pct > 0 else "delta-up"
    return text, cls


def _delta_str(delta, is_rtl: bool = False):
    suffix = " نقطة" if is_rtl else "pp"
    if delta is None:
        return "—", "delta-flat"
    if abs(delta) < 0.05:
        return "0.0" + suffix, "delta-flat"
    cls = "delta-up" if delta > 0 else "delta-down"
    arrow = "▲" if delta > 0 else "▼"
    return f"{arrow} {abs(delta):.1f}{suffix}", cls


def _kpi_card(label, value, sub=None, sub_class="flat", accent="#0B93B8"):
    return {"label": label, "value": value, "sub": sub, "sub_class": sub_class, "accent": accent}


def _build_pass_rate_bars(stations: list[StationTrend], threshold: float, lang: str) -> list[dict]:
    ordered = sorted(stations, key=lambda s: s.current.pass_pct)
    bars = []
    for st in ordered:
        v = st.current.pass_pct
        bars.append({
            "name": st.display_name(lang),
            "pct": round(v, 1),
            "value_label": f"{v:.1f}%",
            "color": "#0B93B8" if v >= threshold else "#D64545",
            "threshold_pct": round(threshold, 1),
        })
    return bars


_DONUT_R = 42.0
_DONUT_CIRCUMFERENCE = 2 * math.pi * _DONUT_R


def _build_volume_bars(stations: list[StationTrend], lang: str) -> list[dict]:
    """One donut chart per station: filled arc = attendance as a % of
    appointments, so the chart reads as a pie/donut rather than a bar."""
    ordered = sorted(stations, key=lambda s: s.current.appointments, reverse=True)
    bars = []
    for st in ordered:
        c = st.current
        ratio = (c.attendance / c.appointments * 100.0) if c.appointments else 0.0
        ratio = min(max(ratio, 0.0), 100.0)
        arc = _DONUT_CIRCUMFERENCE * ratio / 100.0
        bars.append({
            "name": st.display_name(lang),
            "attendance_pct_of_appt": round(ratio, 1),
            "value_label": f"{ratio:.1f}%",
            "detail_label": f"{_fmt_int(c.attendance)} / {_fmt_int(c.appointments)}",
            "dash_fg": f"{arc:.2f}",
            "dash_gap": f"{max(_DONUT_CIRCUMFERENCE - arc, 0.0):.2f}",
        })
    return bars


def build_executive_summary(analysis: PeriodAnalysis, lang: str) -> str:
    c = analysis.company_current
    p = analysis.company_previous
    best = max(analysis.stations, key=lambda s: s.current.pass_pct, default=None)
    worst = min(analysis.stations, key=lambda s: s.current.pass_pct, default=None)
    n_risk = sum(1 for f in analysis.flags if f.kind == "risk")
    n_opp = sum(1 for f in analysis.flags if f.kind == "opportunity")
    period_str = format_period(analysis.period_start, analysis.period_end, lang, fallback=analysis.period_label)

    if lang == "ar":
        trend_txt = ""
        if p:
            d = c.pass_pct - p.pass_pct
            direction = "ارتفعت" if d > 0.05 else ("انخفضت" if d < -0.05 else "استقرت")
            trend_txt = f" مقارنة بالفترة السابقة، {direction} نسبة النجاح الإجمالية بمقدار {abs(d):.1f} نقطة."
        parts = [
            f"خلال فترة {period_str}، استقبلت المحطات {_fmt_int(c.appointments)} موعدًا "
            f"وسُجّل حضور {_fmt_int(c.attendance)} مركبة ({c.attendance_pct:.1f}%)، "
            f"بنسبة نجاح إجمالية {c.pass_pct:.1f}%.{trend_txt}"
        ]
        if best and worst and best.station_name_ar != worst.station_name_ar:
            parts.append(
                f" أفضل أداء كانت محطة {best.display_name('ar')} بنسبة نجاح {best.current.pass_pct:.1f}%، "
                f"بينما سجّلت محطة {worst.display_name('ar')} أدنى نسبة نجاح ({worst.current.pass_pct:.1f}%) وتحتاج لمتابعة."
            )
        if n_risk or n_opp:
            parts.append(f" تم رصد {n_risk} نقطة تستدعي الانتباه و{n_opp} فرصة تحسين تفصيلية أدناه.")
        return "".join(parts)
    else:
        trend_txt = ""
        if p:
            d = c.pass_pct - p.pass_pct
            direction = "rose" if d > 0.05 else ("fell" if d < -0.05 else "held steady")
            trend_txt = f" Compared with the previous period, the overall pass rate {direction} by {abs(d):.1f} points."
        parts = [
            f"Over {period_str}, stations booked {_fmt_int(c.appointments)} appointments "
            f"with {_fmt_int(c.attendance)} vehicles attending ({c.attendance_pct:.1f}%), "
            f"for an overall pass rate of {c.pass_pct:.1f}%.{trend_txt}"
        ]
        if best and worst and best.station_name_ar != worst.station_name_ar:
            parts.append(
                f" {best.display_name('en')} led with a {best.current.pass_pct:.1f}% pass rate, while "
                f"{worst.display_name('en')} posted the lowest ({worst.current.pass_pct:.1f}%) and needs follow-up."
            )
        if n_risk or n_opp:
            parts.append(f" {n_risk} risk item(s) and {n_opp} improvement opportunity(ies) are detailed below.")
        return "".join(parts)


def generate_report_pdf(
    analysis: PeriodAnalysis,
    settings,
    lang: str = "ar",
    logo_png_bytes: bytes | None = None,
) -> bytes:
    assert lang in ("ar", "en")
    is_rtl = lang == "ar"
    t = dict(LABELS[lang])
    t["company_name"] = settings.company_name_ar if is_rtl else settings.company_name_en

    env = Environment(loader=FileSystemLoader(_TEMPLATE_DIR))
    template = env.get_template("report.html")

    threshold = settings.pass_pct_alert_threshold

    # direction=up: an increase is good news (green). direction=down: an
    # increase is bad news (red) -- e.g. more absence/retests/failures.
    _FIELD_DIRECTIONS = {
        "appointments": "up", "attendance": "up", "absence": "down",
        "first_time": "neutral", "retest_1": "down", "retest_2": "down",
        "passed": "up", "failed": "down",
    }

    def _field_cell(st, field, fmt_key):
        value = getattr(st.current, field)
        delta_text, delta_class = _field_delta_str(
            st.field_delta_pct(field), is_rtl, _FIELD_DIRECTIONS[field]
        )
        return {"value": _fmt_int(value), "delta_text": delta_text, "delta_class": delta_class}

    station_rows = []
    for st in analysis.stations:
        c = st.current
        pass_delta_text, pass_delta_class = _delta_str(st.pass_pct_delta, is_rtl)
        station_rows.append({
            "name": st.display_name(lang),
            "appointments": _field_cell(st, "appointments", "appointments"),
            "attendance": _field_cell(st, "attendance", "attendance"),
            "absence": _field_cell(st, "absence", "absence"),
            "first_time": _field_cell(st, "first_time", "first_time"),
            "retest1": _field_cell(st, "retest_1", "retest1"),
            "retest2": _field_cell(st, "retest_2", "retest2"),
            "passed": _field_cell(st, "passed", "passed"),
            "failed": _field_cell(st, "failed", "failed"),
            "pass": {
                "value": f"{c.pass_pct:.1f}%",
                "value_class": _pass_class(c.pass_pct),
                "delta_text": pass_delta_text,
                "delta_class": pass_delta_class,
            },
        })
    # keep table sorted by pass% ascending so weakest stations are easy to spot first (RTL: top of list read first)
    station_rows.sort(key=lambda r: float(r["pass"]["value"].rstrip("%")))

    comp = analysis.company_current
    totals = {
        "appointments": _fmt_int(comp.appointments), "attendance": _fmt_int(comp.attendance),
        "absence": _fmt_int(comp.absence), "first_time": _fmt_int(comp.first_time),
        "retest1": _fmt_int(comp.retest_1), "retest2": _fmt_int(comp.retest_2),
        "passed": _fmt_int(comp.passed), "failed": _fmt_int(comp.failed),
        "pass_pct": f"{comp.pass_pct:.1f}%",
    }

    prev = analysis.company_previous
    appt_delta_txt, appt_delta_cls = None, "flat"
    if prev and prev.appointments:
        d = (comp.appointments - prev.appointments) / prev.appointments * 100
        appt_delta_txt = f"{'▲' if d >= 0 else '▼'} {abs(d):.1f}% {t['vs_prev']}"
        appt_delta_cls = "up" if d > 0 else ("down" if d < 0 else "flat")

    pass_delta = None if not prev else comp.pass_pct - prev.pass_pct
    pass_delta_txt, pass_delta_cls_raw = _delta_str(pass_delta, is_rtl)
    pass_delta_cls = {"delta-up": "up", "delta-down": "down", "delta-flat": "flat"}[pass_delta_cls_raw]

    absence_delta = None if not prev else comp.absence_pct - prev.absence_pct
    absence_delta_txt, absence_delta_cls_raw = _delta_str(absence_delta, is_rtl)
    # for absence, a drop is good news -> invert color semantics
    absence_delta_cls = {"delta-up": "down", "delta-down": "up", "delta-flat": "flat"}[absence_delta_cls_raw]

    kpi_cards = [
        _kpi_card(t["kpi_appointments"], _fmt_int(comp.appointments),
                  appt_delta_txt, appt_delta_cls, "#0B93B8"),
        _kpi_card(t["kpi_attendance"], f"{_fmt_int(comp.attendance)} ({comp.attendance_pct:.1f}%)",
                  None, "flat", "#0B93B8"),
        _kpi_card(t["kpi_absence"], f"{_fmt_int(comp.absence)} ({comp.absence_pct:.1f}%)",
                  (f"{absence_delta_txt} {t['vs_prev']}" if prev else None), absence_delta_cls, "#D64545"),
        _kpi_card(t["kpi_pass_pct"], f"{comp.pass_pct:.1f}%",
                  (f"{pass_delta_txt} {t['vs_prev']}" if prev else None), pass_delta_cls, "#4F9A4A"),
        _kpi_card(t["kpi_passed"], _fmt_int(comp.passed), None, "flat", "#4F9A4A"),
        _kpi_card(t["kpi_failed"], _fmt_int(comp.failed), None, "flat", "#D64545"),
        _kpi_card(t["kpi_complaints"],
                  "—" if analysis.complaints is None else _fmt_int(analysis.complaints),
                  None, "flat", "#C98A1E"),
        _kpi_card(t["kpi_absher"],
                  "—" if analysis.absher_success_pct is None else f"{analysis.absher_success_pct:.1f}%",
                  None, "flat", "#0B93B8"),
    ]

    tag_label_map = {"risk": t["tag_risk"], "opportunity": t["tag_opportunity"], "positive": t["tag_positive"]}
    flags = []
    order = {"risk": 0, "opportunity": 1, "positive": 2}
    for f in sorted(analysis.flags, key=lambda f: order.get(f.kind, 9)):
        flags.append({
            "station_name": f.display_name(lang),
            "kind": f.kind,
            "message": f.message_ar if is_rtl else f.message_en,
            "tag_label": tag_label_map.get(f.kind, f.kind),
        })

    period_str = format_period(analysis.period_start, analysis.period_end, lang, fallback=analysis.period_label)

    trend_rows = None
    if len(analysis.history) > 1:
        trend_rows = []
        for h in analysis.history:
            trend_rows.append({
                "label": format_period(h.get("period_start"), h.get("period_end"), lang, fallback=h["label"]),
                "is_current": h.get("period_start") == analysis.period_start,
                "appointments": _fmt_int(h["appointments"]),
                "pass_pct": f"{h['pass_pct']:.1f}%",
                "absence_pct": f"{h['absence_pct']:.1f}%",
                "attendance_pct": f"{h['attendance_pct']:.1f}%",
            })

    pass_rate_bars = _build_pass_rate_bars(analysis.stations, threshold, lang)
    volume_bars = _build_volume_bars(analysis.stations, lang)

    if logo_png_bytes:
        logo_b64 = base64.b64encode(logo_png_bytes).decode("ascii")
    else:
        default_logo = os.path.join(os.path.dirname(__file__), "assets", "logo_cropped.png")
        logo_b64 = _b64(default_logo)

    html_str = template.render(
        lang=lang,
        dir="rtl" if is_rtl else "ltr",
        start_side="right" if is_rtl else "left",
        end_align="left" if is_rtl else "right",
        page_num_side="left" if is_rtl else "right",
        t=t,
        font_regular_b64=_b64(os.path.join(_FONT_DIR, "Cairo-Regular.woff2")),
        font_semibold_b64=_b64(os.path.join(_FONT_DIR, "Cairo-SemiBold.woff2")),
        font_bold_b64=_b64(os.path.join(_FONT_DIR, "Cairo-Bold.woff2")),
        logo_b64=logo_b64,
        period_label=period_str,
        station_count=len(analysis.stations),
        generated_on=dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        summary_text=build_executive_summary(analysis, lang),
        kpi_cards=kpi_cards,
        trend_rows=trend_rows,
        station_rows=station_rows,
        totals=totals,
        pass_rate_bars=pass_rate_bars,
        volume_bars=volume_bars,
        flags=flags,
    )

    return HTML(string=html_str, base_url=_TEMPLATE_DIR).write_pdf()
