# app.py
# Time × Money Damages Calculator (simple version)
# ─────────────────────────────────────────────────────────────
# - Inputs: start date (date of loss), end date (defaults to today)
# - Units: second/minute/hour/day
# - Rate: coin presets only (penny, nickel, dime, quarter, dollar)
# - Outputs: total amount, time breakdown, narrative helper, optional PDF export

from datetime import datetime, date, time
from zoneinfo import ZoneInfo
import io

import pandas as pd
import streamlit as st

# Optional PDF export
try:
    from reportlab.lib.pagesizes import LETTER
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False


# ---------- Constants & helpers ----------

LA_TZ = ZoneInfo("America/Los_Angeles")

TIME_UNITS = {
    "second": 1,
    "minute": 60,
    "hour": 3600,
    "day": 86400,
}

COIN_PRESETS = [
    ("Penny", 0.01),
    ("Nickel", 0.05),
    ("Dime", 0.10),
    ("Quarter", 0.25),
    ("Dollar", 1.00),
    ("Five Dolla", 5.00),
    ("Twenty Dolla", 20.00),
]

def money(x: float) -> str:
    return f"${x:,.2f}"

def start_of_day(dt_date: date) -> datetime:
    return datetime.combine(dt_date, time.min).replace(tzinfo=LA_TZ)

def end_of_day(dt_date: date) -> datetime:
    return datetime.combine(dt_date, time.max).replace(tzinfo=LA_TZ)

def elapsed_seconds(start_dt: datetime, end_dt: datetime) -> float:
    delta = end_dt - start_dt
    return max(delta.total_seconds(), 0.0)

def all_units(seconds: float) -> dict:
    return {
        "seconds": seconds,
        "minutes": seconds / 60,
        "hours": seconds / 3600,
        "days": seconds / 86400,
    }

def compute_amount(seconds: float, unit: str, rate_per_unit: float) -> float:
    units = seconds / TIME_UNITS[unit]
    return units * rate_per_unit

def make_narrative(start_dt: datetime, end_dt: datetime, seconds: float, unit: str, rate: float, amount: float, inclusive_days_flag: bool) -> str:
    au = all_units(seconds)
    units_val = {
        "second": au["seconds"],
        "minute": au["minutes"],
        "hour":   au["hours"],
        "day":    au["days"],
    }[unit]

    disp_days = au["days"] + (1.0 if inclusive_days_flag else 0.0)

    return (
        f"From {start_dt.date():%b %d, %Y} through {end_dt.date():%b %d, %Y}, "
        f"that’s approximately {units_val:,.0f} {unit}{'' if units_val == 1 else 's'} "
        f"({disp_days:,.2f} day span for juror-friendly counting). "
        f"At {money(rate)} per {unit}, the past pain-and-suffering equals {money(amount)}."
    )

def export_summary_pdf(buffer: io.BytesIO, header: str, summary: dict):
    doc = SimpleDocTemplate(buffer, pagesize=LETTER,
                            rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    flow = []
    flow.append(Paragraph(header, styles["Title"]))
    flow.append(Spacer(1, 0.20 * inch))

    for k, v in summary.items():
        flow.append(Paragraph(f"<b>{k}:</b> {v}", styles["BodyText"]))
        flow.append(Spacer(1, 0.06 * inch))

    doc.build(flow)
    buffer.seek(0)
    return buffer


# ---------- UI ----------

st.set_page_config(
    page_title="Time × Money Damages Calculator",
    page_icon="⏱️",
    layout="wide"
)

st.title("⏱️ Time × Money Damages Calculator")
st.caption("Date-only • Coin presets only • No target solver • No future projection")

with st.sidebar:
    st.header("Inputs")

    st.subheader("Date Range")
    start_date = st.date_input("Date of loss", value=date(2022, 7, 28))
    end_date = st.date_input("End date", value=date.today())

    st.subheader("Counting options")
    inclusive_days = st.checkbox(
        "Inclusive days (adds +1 to the displayed day count)",
        value=False,
        help="For phrasing like 'counting the day of the incident as a full day'."
    )

    st.subheader("Unit & Rate (presets only)")
    unit = st.selectbox("Time unit", list(TIME_UNITS.keys()), index=1)  # default to 'minute'
    preset_names = [n for n, _ in COIN_PRESETS]
    sel_preset = st.selectbox("Coin preset", preset_names, index=4)     # default to 'Dollar'
    applied_rate = dict(COIN_PRESETS)[sel_preset]

# Validate dates
if end_date < start_date:
    st.error("End date must be on or after the date of loss.")
    st.stop()

# Build datetime span covering whole days
start_dt = start_of_day(start_date)
end_dt = end_of_day(end_date)

# Base window seconds
base_seconds = elapsed_seconds(start_dt, end_dt)
amount_now = compute_amount(base_seconds, unit, applied_rate)

# ---------- Main Hero & Breakdown ----------

hero_col, info_col = st.columns([1.1, 1.2])

with hero_col:
    st.metric(
        label=f"Past Pain @ {money(applied_rate)}/{unit}",
        value=money(amount_now)
    )
    st.caption("Display rounds to cents; internal math retains full precision.")

with info_col:
    au_base = all_units(base_seconds)
    days_disp = au_base["days"] + (1.0 if inclusive_days else 0.0)

    st.subheader("Time Breakdown")
    st.write(f"Start: {start_dt.date():%b %d, %Y}")
    st.write(f"End:   {end_dt.date():%b %d, %Y}")
    st.write(f"Seconds: {au_base['seconds']:,.0f}")
    st.write(f"Minutes: {au_base['minutes']:,.0f}")
    st.write(f"Hours:   {au_base['hours']:,.0f}")
    st.write(f"Days:    {days_disp:,.2f}" + (" (inclusive display)" if inclusive_days else ""))

# ---------- Narrative helper ----------

st.markdown("---")
st.subheader("📝 Narrative Helper")

narr = make_narrative(start_dt, end_dt, base_seconds, unit, applied_rate, amount_now, inclusive_days)
st.text_area("Copy-ready paragraph", value=narr, height=140)

# ---------- Export ----------

st.markdown("---")
st.subheader("📤 Export")

if REPORTLAB_AVAILABLE:
    summary_info = {
        "Start": f"{start_dt.date():%b %d, %Y}",
        "End": f"{end_dt.date():%b %d, %Y}",
        "Unit & Rate": f"{unit} @ {money(applied_rate)}/{unit}",
        "Past Amount": money(amount_now),
        "Inclusive days (display)": "Yes" if inclusive_days else "No",
        "Generated": datetime.now(LA_TZ).strftime("%b %d, %Y, %I:%M %p %Z"),
    }

    pdf_buf = io.BytesIO()
    export_summary_pdf(pdf_buf, "Time × Money Damages Summary", summary_info)

    st.download_button(
        "Download summary (PDF)",
        data=pdf_buf,
        file_name="damages_summary.pdf",
        mime="application/pdf",
        use_container_width=True
    )
else:
    st.info("Optional PDF export requires `reportlab`. Install with: `pip install reportlab`.")

# Footer
st.markdown("<hr style='opacity:0.2'/>", unsafe_allow_html=True)
st.caption("Transparent arithmetic for demonstrative purposes only; not legal advice.")
