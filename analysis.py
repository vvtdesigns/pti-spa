"""
Executive-level analysis: company & per-station KPIs, period-over-period
trends, rankings, and automatically flagged weak points / opportunities.

Everything here works off plain dicts/lists (not live SQLAlchemy sessions)
so it's easy to unit-test and easy to feed into the report builder.

Station names are carried in both languages everywhere (station_name_ar /
station_name_en) so a report can pick the right one and never mix Arabic
and English in one document -- see station_names.py for how the English
name is sourced.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Optional

from db import Period, StationMetric


def pct(numerator: float, denominator: float) -> float:
    return (numerator / denominator * 100.0) if denominator else 0.0


def delta_points(curr: float, prev: Optional[float]) -> Optional[float]:
    if prev is None:
        return None
    return curr - prev


@dataclass
class StationSnapshot:
    station_name_ar: str
    station_name_en: Optional[str]
    appointments: int
    attendance: int
    absence: int
    first_time: int
    retest_1: int
    retest_2: int
    passed: int
    failed: int

    def display_name(self, lang: str) -> str:
        if lang == "ar":
            return self.station_name_ar
        return self.station_name_en or self.station_name_ar

    @property
    def pass_pct(self) -> float:
        return pct(self.passed, self.passed + self.failed)

    @property
    def absence_pct(self) -> float:
        return pct(self.absence, self.appointments)

    @property
    def attendance_pct(self) -> float:
        return pct(self.attendance, self.appointments)

    @property
    def retest_load_pct(self) -> float:
        """Share of attendance that needed a 2nd retest -- a quality/training signal."""
        return pct(self.retest_2, self.attendance)


@dataclass
class StationTrend:
    station_name_ar: str
    station_name_en: Optional[str]
    current: StationSnapshot
    previous: Optional[StationSnapshot]

    def display_name(self, lang: str) -> str:
        if lang == "ar":
            return self.station_name_ar
        return self.station_name_en or self.station_name_ar

    @property
    def pass_pct_delta(self) -> Optional[float]:
        return delta_points(self.current.pass_pct, self.previous.pass_pct if self.previous else None)

    @property
    def absence_pct_delta(self) -> Optional[float]:
        return delta_points(self.current.absence_pct, self.previous.absence_pct if self.previous else None)

    @property
    def appointments_delta_pct(self) -> Optional[float]:
        if not self.previous or not self.previous.appointments:
            return None
        return pct(self.current.appointments - self.previous.appointments, self.previous.appointments)

    def field_delta_pct(self, field: str) -> Optional[float]:
        """% change vs the previous period for a raw count field (appointments,
        attendance, absence, first_time, retest_1, retest_2, passed, failed).
        None when there's no previous period or the previous value was 0
        (a % change from zero is undefined)."""
        if not self.previous:
            return None
        prev_val = getattr(self.previous, field)
        if not prev_val:
            return None
        curr_val = getattr(self.current, field)
        return pct(curr_val - prev_val, prev_val)


@dataclass
class Flag:
    station_name_ar: str
    station_name_en: Optional[str]
    kind: str          # "risk" | "opportunity" | "positive"
    message_ar: str
    message_en: str

    def display_name(self, lang: str) -> str:
        if lang == "ar":
            return self.station_name_ar
        return self.station_name_en or self.station_name_ar


@dataclass
class PeriodAnalysis:
    period_label: str
    period_start: Optional[dt.date]
    period_end: Optional[dt.date]
    stations: list[StationTrend]
    company_current: StationSnapshot
    company_previous: Optional[StationSnapshot]
    complaints: Optional[int]
    complaints_resolved: Optional[int]
    absher_success_pct: Optional[float]
    flags: list[Flag] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)  # for trend line charts across many periods


def _snapshot_from_metric(m: StationMetric) -> StationSnapshot:
    return StationSnapshot(
        station_name_ar=m.station.name_ar,
        station_name_en=m.station.name_en,
        appointments=m.appointments, attendance=m.attendance, absence=m.absence,
        first_time=m.first_time, retest_1=m.retest_1, retest_2=m.retest_2,
        passed=m.passed, failed=m.failed,
    )


def _company_snapshot(snapshots: list[StationSnapshot]) -> StationSnapshot:
    return StationSnapshot(
        station_name_ar="__company__",
        station_name_en="__company__",
        appointments=sum(s.appointments for s in snapshots),
        attendance=sum(s.attendance for s in snapshots),
        absence=sum(s.absence for s in snapshots),
        first_time=sum(s.first_time for s in snapshots),
        retest_1=sum(s.retest_1 for s in snapshots),
        retest_2=sum(s.retest_2 for s in snapshots),
        passed=sum(s.passed for s in snapshots),
        failed=sum(s.failed for s in snapshots),
    )


def build_flags(
    stations: list[StationTrend],
    company: StationSnapshot,
    pass_pct_threshold: float = 60.0,
    absence_pct_threshold: float = 15.0,
) -> list[Flag]:
    flags: list[Flag] = []

    for st in stations:
        c = st.current
        names = (st.station_name_ar, st.station_name_en)
        if c.pass_pct < pass_pct_threshold:
            flags.append(Flag(
                *names, "risk",
                f"نسبة النجاح {c.pass_pct:.1f}% أقل من الحد المستهدف ({pass_pct_threshold:.0f}%).",
                f"Pass rate of {c.pass_pct:.1f}% is below the {pass_pct_threshold:.0f}% target.",
            ))
        if c.absence_pct > absence_pct_threshold:
            flags.append(Flag(
                *names, "opportunity",
                f"نسبة الغياب {c.absence_pct:.1f}% أعلى من المتوسط المستهدف -- فرصة لتحسين التذكير والحجز.",
                f"Absence rate of {c.absence_pct:.1f}% is above target -- an opportunity to improve reminders and booking.",
            ))
        if st.pass_pct_delta is not None and st.pass_pct_delta <= -5:
            flags.append(Flag(
                *names, "risk",
                f"تراجع نسبة النجاح {abs(st.pass_pct_delta):.1f} نقطة مقارنة بالفترة السابقة.",
                f"Pass rate dropped {abs(st.pass_pct_delta):.1f} points versus the previous period.",
            ))
        if st.pass_pct_delta is not None and st.pass_pct_delta >= 5:
            flags.append(Flag(
                *names, "positive",
                f"تحسّن نسبة النجاح {st.pass_pct_delta:.1f} نقطة مقارنة بالفترة السابقة.",
                f"Pass rate improved {st.pass_pct_delta:.1f} points versus the previous period.",
            ))
        if c.retest_load_pct > 20:
            flags.append(Flag(
                *names, "opportunity",
                f"نسبة إعادة الفحص الثانية {c.retest_load_pct:.1f}% من الحضور، وهو مؤشر محتمل على جودة الفحص الأول أو التدريب.",
                f"2nd-retest load is {c.retest_load_pct:.1f}% of attendance -- a possible first-check quality or training signal.",
            ))
        if (st.appointments_delta_pct is not None and st.appointments_delta_pct > 10
                and st.pass_pct_delta is not None and st.pass_pct_delta < 0):
            flags.append(Flag(
                *names, "risk",
                f"نمو في المواعيد ({st.appointments_delta_pct:+.1f}%) مصحوب بتراجع في نسبة النجاح، ما يشير لاحتمال ضغط تشغيلي.",
                f"Appointment volume grew {st.appointments_delta_pct:+.1f}% while pass rate fell -- possible capacity strain.",
            ))

    return flags


def rank_stations(stations: list[StationTrend]) -> tuple[list[StationTrend], list[StationTrend]]:
    by_pass = sorted(stations, key=lambda s: s.current.pass_pct, reverse=True)
    top = by_pass[:3]
    bottom = list(reversed(by_pass[-3:])) if len(by_pass) > 3 else list(reversed(by_pass))
    return top, bottom


def analyze_period(
    all_periods_chrono: list[Period],
    target_period: Period,
    pass_pct_threshold: float = 60.0,
    absence_pct_threshold: float = 15.0,
) -> PeriodAnalysis:
    """
    all_periods_chrono: every period in the DB, oldest -> newest (for history/trend lines)
    target_period: the period the report is being built for
    """
    idx = next((i for i, p in enumerate(all_periods_chrono) if p.id == target_period.id), None)
    prev_period = all_periods_chrono[idx - 1] if idx is not None and idx > 0 else None

    curr_by_station = {m.station.name_ar: _snapshot_from_metric(m) for m in target_period.metrics}
    prev_by_station = {}
    if prev_period:
        prev_by_station = {m.station.name_ar: _snapshot_from_metric(m) for m in prev_period.metrics}

    trends = [
        StationTrend(name, snap.station_name_en, snap, prev_by_station.get(name))
        for name, snap in curr_by_station.items()
    ]
    trends.sort(key=lambda t: t.station_name_ar)

    company_current = _company_snapshot(list(curr_by_station.values()))
    company_previous = _company_snapshot(list(prev_by_station.values())) if prev_by_station else None

    flags = build_flags(trends, company_current, pass_pct_threshold, absence_pct_threshold)

    history = []
    for p in all_periods_chrono:
        snaps = [_snapshot_from_metric(m) for m in p.metrics]
        if not snaps:
            continue
        comp = _company_snapshot(snaps)
        history.append({
            "label": p.label or f"{p.period_start} - {p.period_end}",
            "period_start": p.period_start,
            "period_end": p.period_end,
            "pass_pct": comp.pass_pct,
            "absence_pct": comp.absence_pct,
            "attendance_pct": comp.attendance_pct,
            "appointments": comp.appointments,
        })

    return PeriodAnalysis(
        period_label=target_period.label or f"{target_period.period_start} - {target_period.period_end}",
        period_start=target_period.period_start,
        period_end=target_period.period_end,
        stations=trends,
        company_current=company_current,
        company_previous=company_previous,
        complaints=target_period.complaints,
        complaints_resolved=target_period.complaints_resolved,
        absher_success_pct=target_period.absher_success_pct,
        flags=flags,
        history=history,
    )
