"""Manual smoke test: parse the sample PDF, store two periods, generate both
language reports, and print a summary. Run with:
    python3 scripts/test_pipeline.py
"""
import sys
import os
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db
from parser import parse_operations_pdf, StationRow
from analysis import analyze_period
from report import generate_report_pdf

DB_PATH = "data/test_pti.db"
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
# force re-init of module-level engine singletons
db._engine = None
db._SessionLocal = None

db.init_db()

SAMPLE_PDF = "/root/.claude/uploads/9008723c-8276-5ba3-b644-499dac2ace01/655fcc75-8.pdf"
with open(SAMPLE_PDF, "rb") as f:
    pdf_bytes = f.read()

result = parse_operations_pdf(pdf_bytes)
print(f"Parsed {len(result.rows)} station rows, warnings: {result.warnings}")
for r in result.rows:
    print(" ", r)


def save_period(period_start, period_end, label, rows: list[StationRow], complaints, absher, scale=1.0):
    with db.get_session() as s:
        period = db.Period(
            period_start=period_start, period_end=period_end, label=label,
            complaints=complaints, absher_success_pct=absher,
        )
        s.add(period)
        s.flush()
        for r in rows:
            station = db.get_or_create_station(s, r.station_name)
            s.add(db.StationMetric(
                period_id=period.id, station_id=station.id,
                appointments=int(r.appointments * scale), attendance=int(r.attendance * scale),
                absence=int(r.absence * scale), first_time=int(r.first_time * scale),
                retest_1=int(r.retest_1 * scale), retest_2=int(r.retest_2 * scale),
                passed=int(r.passed * scale), failed=int(r.failed * scale),
            ))
        s.commit()
        return period.id


# a synthetic "previous period" (scaled down + slightly worse pass rate) so trend/deltas have something to show
prev_rows = []
for r in result.rows:
    prev_rows.append(StationRow(
        station_name=r.station_name,
        appointments=int(r.appointments * 0.9),
        attendance=int(r.attendance * 0.9),
        absence=int(r.absence * 1.1),
        first_time=int(r.first_time * 0.9),
        retest_1=int(r.retest_1 * 0.9),
        retest_2=int(r.retest_2 * 1.3),
        passed=int(r.passed * 0.82),
        failed=int(r.failed * 1.25),
    ))

pid_prev = save_period(dt.date(2026, 7, 18), dt.date(2026, 7, 24), "Jul 18 - 24, 2026", prev_rows, 5, 97.9)
pid_curr = save_period(dt.date(2026, 7, 25), dt.date(2026, 7, 31), "Jul 25 - 31, 2026", result.rows, 7, 98.6)

all_periods = db.list_periods()
target = db.get_period_with_metrics(pid_curr)
analysis = analyze_period(all_periods, target, pass_pct_threshold=60.0, absence_pct_threshold=15.0)

print("\nCompany current:", analysis.company_current)
print("Flags:", len(analysis.flags))
for f in analysis.flags:
    print(" -", f.kind, f.station_name_ar, "|", f.message_en)

settings = db.get_settings()

for lang in ("ar", "en"):
    pdf_bytes_out = generate_report_pdf(analysis, settings, lang=lang)
    out_path = f"/tmp/report_{lang}.pdf"
    with open(out_path, "wb") as f:
        f.write(pdf_bytes_out)
    print(f"Wrote {out_path} ({len(pdf_bytes_out)} bytes)")
