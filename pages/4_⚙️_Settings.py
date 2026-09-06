import pandas as pd
import streamlit as st
from sqlalchemy import select

import db

st.set_page_config(page_title="Settings | PTI Stations Performance", page_icon="⚙️", layout="wide")
db.init_db()

st.title("⚙️ Settings")
st.caption("These settings are shared across every device using this database.")

settings = db.get_settings()

st.subheader("Branding")
col1, col2 = st.columns(2)
name_ar = col1.text_input("Company name (Arabic)", value=settings.company_name_ar)
name_en = col2.text_input("Company name (English)", value=settings.company_name_en)

logo_file = st.file_uploader("Replace logo (PNG, transparent background recommended)", type=["png", "jpg", "jpeg"])
if settings.logo_png:
    st.image(settings.logo_png, width=200, caption="Current logo")

st.subheader("Report alert thresholds")
col3, col4 = st.columns(2)
pass_threshold = col3.number_input("Flag a station when pass rate is below (%)", min_value=0.0, max_value=100.0,
                                    value=float(settings.pass_pct_alert_threshold), step=1.0)
absence_threshold = col4.number_input("Flag a station when absence rate is above (%)", min_value=0.0, max_value=100.0,
                                       value=float(settings.absence_pct_alert_threshold), step=1.0)

if st.button("💾 Save settings", type="primary"):
    with db.get_session() as s:
        row = s.get(db.Settings, 1)
        row.company_name_ar = name_ar
        row.company_name_en = name_en
        row.pass_pct_alert_threshold = pass_threshold
        row.absence_pct_alert_threshold = absence_threshold
        if logo_file is not None:
            row.logo_png = logo_file.read()
        s.commit()
    st.success("Settings saved.")
    st.rerun()

st.divider()
st.subheader("Stations")
st.caption("Rename a station or mark it inactive (inactive stations are kept for history but hidden from new-period entry hints).")

with db.get_session() as s:
    stations = list(s.execute(select(db.Station).order_by(db.Station.name_ar)).scalars())
    stations_df = pd.DataFrame([{
        "id": st_.id, "Name (Arabic)": st_.name_ar, "Name (English)": st_.name_en or "",
        "Active": st_.is_active,
    } for st_ in stations])

edited = st.data_editor(
    stations_df, hide_index=True, use_container_width=True,
    column_config={"id": st.column_config.NumberColumn(disabled=True)},
    key="stations_editor",
)

if st.button("💾 Save station changes"):
    with db.get_session() as s:
        for _, row in edited.iterrows():
            station = s.get(db.Station, int(row["id"]))
            if station:
                station.name_en = row["Name (English)"] or None
                station.is_active = bool(row["Active"])
        s.commit()
    st.success("Stations updated.")
    st.rerun()

st.divider()
with st.expander("🗄️ Database connection info"):
    url = db._database_url()
    if url.startswith("sqlite"):
        st.warning(
            "Currently using a **local SQLite file** -- this only persists on this one "
            "deployment/device and won't sync between your laptop and phone. To share data "
            "everywhere, set a `DATABASE_URL` secret pointing at a Postgres database "
            "(e.g. a free Supabase project) -- see the README."
        )
    else:
        masked = url.split("@")[-1] if "@" in url else url
        st.success(f"Connected to a shared database (…@{masked}). Data here is available on every device.")
