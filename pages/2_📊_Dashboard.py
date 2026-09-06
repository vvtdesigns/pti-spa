import pandas as pd
import streamlit as st

import db
from analysis import analyze_period

st.set_page_config(page_title="Dashboard | PTI Stations Performance", page_icon="📊", layout="wide")
db.init_db()

st.title("📊 Dashboard")

periods = db.list_periods()
if not periods:
    st.info("No data yet -- upload a statistics sheet first on the **📤 Upload** page.")
    st.stop()

period_labels = [p.label or f"{p.period_start} - {p.period_end}" for p in periods]
default_idx = len(periods) - 1
chosen_idx = st.selectbox("Period", options=list(range(len(periods))),
                           format_func=lambda i: period_labels[i], index=default_idx)
target = periods[chosen_idx]
analysis = analyze_period(periods, target)
c = analysis.company_current
p = analysis.company_previous

st.subheader(analysis.period_label)
cols = st.columns(5)
cols[0].metric("Appointments", f"{c.appointments:,}", f"{c.appointments - p.appointments:+,}" if p else None)
cols[1].metric("Attendance", f"{c.attendance:,}", f"{c.attendance_pct:.1f}%")
cols[2].metric("Pass rate", f"{c.pass_pct:.1f}%", f"{c.pass_pct - p.pass_pct:+.1f}pp" if p else None)
cols[3].metric("Absence rate", f"{c.absence_pct:.1f}%",
                f"{c.absence_pct - p.absence_pct:+.1f}pp" if p else None, delta_color="inverse")
cols[4].metric("Complaints", analysis.complaints if analysis.complaints is not None else "—")

st.divider()

left, right = st.columns(2)
with left:
    st.markdown("**Pass rate by station**")
    df = pd.DataFrame([{"Station": s.station_name_ar, "Pass %": round(s.current.pass_pct, 1)}
                        for s in analysis.stations]).set_index("Station").sort_values("Pass %")
    st.bar_chart(df, horizontal=True)

with right:
    st.markdown("**Appointments vs. attendance by station**")
    df2 = pd.DataFrame([{"Station": s.station_name_ar, "Appointments": s.current.appointments,
                          "Attendance": s.current.attendance} for s in analysis.stations]
                        ).set_index("Station")
    st.bar_chart(df2, horizontal=True)

if len(analysis.history) > 1:
    st.markdown("**Trend across all periods**")
    hist_df = pd.DataFrame(analysis.history)[["label", "pass_pct", "absence_pct"]]
    hist_df = hist_df.rename(columns={"label": "Period", "pass_pct": "Pass %", "absence_pct": "Absence %"})
    st.line_chart(hist_df.set_index("Period"))

st.divider()
st.markdown("**Station performance table**")
table_df = pd.DataFrame([{
    "Station": s.station_name_ar,
    "Appointments": s.current.appointments, "Attendance": s.current.attendance,
    "Absence": s.current.absence, "First-time": s.current.first_time,
    "Retest 1": s.current.retest_1, "Retest 2": s.current.retest_2,
    "Passed": s.current.passed, "Failed": s.current.failed,
    "Pass %": round(s.current.pass_pct, 1),
    "Δ Pass % vs prev": round(s.pass_pct_delta, 1) if s.pass_pct_delta is not None else None,
} for s in sorted(analysis.stations, key=lambda s: s.current.pass_pct)])
st.dataframe(table_df, use_container_width=True, hide_index=True)

st.divider()
st.markdown("**Weak points & opportunities**")
if not analysis.flags:
    st.success("No flagged items this period.")
else:
    icon = {"risk": "🔴", "opportunity": "🟠", "positive": "🟢"}
    for f in sorted(analysis.flags, key=lambda f: {"risk": 0, "opportunity": 1, "positive": 2}[f.kind]):
        st.markdown(f"{icon[f.kind]} **{f.station_name_ar}** — {f.message_en}")
