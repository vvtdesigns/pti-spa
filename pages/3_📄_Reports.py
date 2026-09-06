import streamlit as st

import db
from analysis import analyze_period
from report import generate_report_pdf

st.set_page_config(page_title="Reports | PTI Stations Performance", page_icon="📄", layout="wide")
db.init_db()

st.title("📄 Executive report")

periods = db.list_periods()
if not periods:
    st.info("No data yet -- upload a statistics sheet first on the **📤 Upload** page.")
    st.stop()

period_labels = [p.label or f"{p.period_start} - {p.period_end}" for p in periods]
chosen_idx = st.selectbox("Period", options=list(range(len(periods))),
                           format_func=lambda i: period_labels[i], index=len(periods) - 1)
target = periods[chosen_idx]

lang_choice = st.radio("Report language", options=["العربية (Arabic)", "English"], horizontal=True)
lang = "ar" if lang_choice.startswith("العربية") else "en"

settings = db.get_settings()

st.caption(
    f"Alert thresholds currently used: pass rate below **{settings.pass_pct_alert_threshold:.0f}%** "
    f"and absence rate above **{settings.absence_pct_alert_threshold:.0f}%** are flagged. "
    "Adjust these in ⚙️ Settings."
)

if st.button("🖨️ Generate PDF report", type="primary"):
    with st.spinner("Building report..."):
        analysis = analyze_period(
            periods, target,
            pass_pct_threshold=settings.pass_pct_alert_threshold,
            absence_pct_threshold=settings.absence_pct_alert_threshold,
        )
        pdf_bytes = generate_report_pdf(analysis, settings, lang=lang, logo_png_bytes=settings.logo_png)

    st.success("Report ready.")
    fname = f"PTI_Performance_Report_{target.period_start}_{lang}.pdf"
    st.download_button("⬇️ Download PDF", pdf_bytes, file_name=fname, mime="application/pdf")

    with st.expander("Preview (first page as an image isn't available in-browser -- use the download)"):
        st.caption(
            f"{len(analysis.stations)} stations · {analysis.company_current.appointments:,} appointments · "
            f"{analysis.company_current.pass_pct:.1f}% pass rate · "
            f"{sum(1 for f in analysis.flags if f.kind == 'risk')} risk flag(s)"
        )
