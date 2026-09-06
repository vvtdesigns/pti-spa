import datetime as dt
import io

import pandas as pd
import streamlit as st

import db
from parser import parse_upload, build_template_dataframe
from station_names import KNOWN_STATION_NAMES_EN, suggest_english_name

st.set_page_config(page_title="Upload | PTI Stations Performance", page_icon="📤", layout="wide")
db.init_db()

st.title("📤 Upload a statistics sheet")

st.markdown(
    "Upload the period's operations sheet (Excel/CSV is most reliable; the PDF export from "
    "the operations system also works as a fallback). The app will show you what it parsed "
    "before anything is saved."
)

with st.expander("📋 Expected columns (Excel/CSV) -- download a template"):
    st.markdown(
        "Column headers can be in Arabic (as below) or a close English equivalent "
        "(Station / Appointments / Attendance / Absence / First time / Retest 1 / Retest 2 / "
        "Passed / Failed). Extra columns are ignored."
    )
    template_df = build_template_dataframe()
    st.dataframe(template_df, use_container_width=True)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        template_df.to_excel(writer, index=False, sheet_name="Stations")
    st.download_button("⬇️ Download Excel template", buf.getvalue(),
                        file_name="pti_stations_template.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

uploaded = st.file_uploader("Statistics sheet", type=["xlsx", "xls", "csv", "pdf"])

if "parse_result" not in st.session_state:
    st.session_state.parse_result = None
    st.session_state.parse_filename = None

if uploaded is not None and uploaded.name != st.session_state.parse_filename:
    file_bytes = uploaded.read()
    st.session_state.parse_result = parse_upload(file_bytes, uploaded.name)
    st.session_state.parse_filename = uploaded.name

result = st.session_state.parse_result

if result is not None:
    for w in result.warnings:
        st.warning(w)

    if result.rows:
        st.subheader(f"Parsed {len(result.rows)} station rows")
        preview_df = pd.DataFrame([{
            "Station": r.station_name, "Appointments": r.appointments, "Attendance": r.attendance,
            "Absence": r.absence, "First-time": r.first_time, "Retest 1": r.retest_1,
            "Retest 2": r.retest_2, "Passed": r.passed, "Failed": r.failed,
            "Pass %": round(r.passed / (r.passed + r.failed) * 100, 1) if (r.passed + r.failed) else 0,
        } for r in result.rows])
        st.dataframe(preview_df, use_container_width=True, hide_index=True)

        st.divider()

        # English reports must never contain Arabic text (including station
        # names) -- so any station this database hasn't seen before, and
        # that isn't in the curated mapping, needs a human-confirmed English
        # name before it can be saved.
        known_names = db.known_station_names()
        new_en_names: dict[str, str] = {}
        unresolved = [
            r.station_name for r in result.rows
            if r.station_name not in known_names and r.station_name not in KNOWN_STATION_NAMES_EN
        ]
        # dedupe, preserve order
        unresolved = list(dict.fromkeys(unresolved))

        if unresolved:
            st.subheader("New station(s) -- confirm English names")
            st.caption(
                "These stations haven't been seen before. English reports show these names "
                "instead of the Arabic ones -- please confirm or edit them."
            )
            for name_ar in unresolved:
                new_en_names[name_ar] = st.text_input(
                    f"English name for ‏{name_ar}",
                    value=suggest_english_name(name_ar),
                    key=f"en_name_{name_ar}",
                )

        st.divider()
        st.subheader("Period details")
        st.caption(
            "These figures usually aren't in the export -- enter them once per upload. "
            "Complaints/Absher are optional company-wide figures for this period."
        )

        col1, col2 = st.columns(2)
        today = dt.date.today()
        period_start = col1.date_input("Period start", value=today - dt.timedelta(days=6))
        period_end = col2.date_input("Period end", value=today)

        col3, col4, col5 = st.columns(3)
        label = col3.text_input("Period label (optional)", placeholder="e.g. Week 31, 2026")
        complaints = col4.number_input("Complaints (optional)", min_value=0, value=0, step=1)
        absher_pct = col5.number_input("Absher success % (optional)", min_value=0.0, max_value=100.0,
                                        value=0.0, step=0.1)

        existing = {p.period_start: p for p in db.list_periods()}
        overlap_warning = None
        for p_start, p in existing.items():
            if p.period_start == period_start and p.period_end == period_end:
                overlap_warning = (
                    f"A period for {period_start} → {period_end} already exists "
                    f"(uploaded {p.uploaded_at:%Y-%m-%d}). Saving again will add a duplicate period."
                )
        if overlap_warning:
            st.warning(overlap_warning)

        missing_en_names = [n for n in unresolved if not new_en_names.get(n, "").strip()]
        if missing_en_names:
            st.warning(
                "Please fill in an English name for every new station above before saving "
                "(so English reports never show Arabic text)."
            )

        if st.button("💾 Save this period to the database", type="primary", disabled=bool(missing_en_names)):
            with db.get_session() as s:
                period = db.Period(
                    period_start=period_start,
                    period_end=period_end,
                    label=label or None,
                    source_filename=uploaded.name,
                    complaints=int(complaints) or None,
                    absher_success_pct=absher_pct or None,
                )
                s.add(period)
                s.flush()
                for r in result.rows:
                    station = db.get_or_create_station(
                        s, r.station_name, name_en=new_en_names.get(r.station_name)
                    )
                    s.add(db.StationMetric(
                        period_id=period.id, station_id=station.id,
                        appointments=r.appointments, attendance=r.attendance, absence=r.absence,
                        first_time=r.first_time, retest_1=r.retest_1, retest_2=r.retest_2,
                        passed=r.passed, failed=r.failed,
                    ))
                s.commit()
            st.success("Saved! This period is now available on every device using this database.")
            st.session_state.parse_result = None
            st.session_state.parse_filename = None
            st.balloons()
    else:
        st.error("No station rows could be parsed from this file -- please check it matches the expected columns.")

st.divider()
st.subheader("Previously uploaded periods")
periods = db.list_periods()
if periods:
    hist_df = pd.DataFrame([{
        "Period": p.label or f"{p.period_start} - {p.period_end}",
        "Start": p.period_start, "End": p.period_end,
        "Stations": len(p.metrics), "Uploaded": p.uploaded_at.strftime("%Y-%m-%d %H:%M"),
        "Source file": p.source_filename or "—",
    } for p in reversed(periods)])
    st.dataframe(hist_df, use_container_width=True, hide_index=True)
else:
    st.caption("No periods uploaded yet.")
