import datetime as dt

import streamlit as st

import db
from analysis import analyze_period

st.set_page_config(page_title="PTI Stations Performance", page_icon="🚗", layout="wide")
db.init_db()

st.title("🚗 PTI Stations Performance Analysis")
st.caption("Massar United Co. — vehicle periodic technical inspection stations")

periods = db.list_periods()

if not periods:
    st.info(
        "No data yet. Go to **📤 Upload** in the sidebar to add your first "
        "statistics sheet, then come back here for an overview."
    )
else:
    latest = periods[-1]
    analysis = analyze_period(periods, latest)
    c = analysis.company_current
    p = analysis.company_previous

    st.subheader(f"Latest period: {analysis.period_label}")

    cols = st.columns(5)
    cols[0].metric("Appointments", f"{c.appointments:,}",
                    f"{c.appointments - p.appointments:+,}" if p else None)
    cols[1].metric("Attendance", f"{c.attendance:,}", f"{c.attendance_pct:.1f}%")
    cols[2].metric("Pass rate", f"{c.pass_pct:.1f}%",
                    f"{c.pass_pct - p.pass_pct:+.1f}pp" if p else None)
    cols[3].metric("Absence rate", f"{c.absence_pct:.1f}%",
                    f"{c.absence_pct - p.absence_pct:+.1f}pp" if p else None,
                    delta_color="inverse")
    cols[4].metric("Stations", len(analysis.stations))

    n_risk = sum(1 for f in analysis.flags if f.kind == "risk")
    n_opp = sum(1 for f in analysis.flags if f.kind == "opportunity")
    if n_risk or n_opp:
        st.warning(f"⚠️ {n_risk} station(s) below target, {n_opp} improvement opportunity(ies) flagged. "
                   "See the **📊 Dashboard** or generate a report in **📄 Reports** for details.")
    else:
        st.success("✅ No stations are currently below target.")

    st.divider()
    st.markdown(
        "Use the sidebar to **📤 Upload** a new period's sheet, explore the **📊 Dashboard**, "
        "generate an executive **📄 Report** (PDF, Arabic/English, with your logo), "
        "or adjust branding/alerts in **⚙️ Settings**."
    )

st.divider()
with st.expander("ℹ️ About this app / how it works"):
    st.markdown(
        """
This app works the same way from your laptop or your phone, because all the data lives in
one shared database (not on any single device) -- upload a sheet from either one and it's
immediately available everywhere.

**Workflow:** Upload a statistics sheet each period → the app parses it and stores per-station
metrics → the Dashboard and Reports pages compare it against every previous period → an
executive PDF report (Arabic or English, your logo, Cairo font) is generated on demand.
        """
    )
