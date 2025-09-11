# app.py
# Time × Money Damages Calculator (date-only, coin presets only)
# ─────────────────────────────────────────────────────────────
# - Inputs: start date (date of loss), end date (defaults to today)
# - Units: second/minute/hour/day
# - Rate: coin presets only (penny, nickel, dime, quarter, dollar)
# - Targeting: show closest preset combos, or solve exact rate for the chosen unit
# - Future projection: optional (years/days)
# - Exports: CSV for scenarios; PDF summary if 'reportlab' is installed
#
# Notes:
# * Date-only handling: we compute elapsed seconds between [start @ 00:00:00] and [end @ 23:59:59.999...],
#   i.e., treating the end date as a full day. Toggle "Inclusive days" only affects the *displayed* day count
#   (for narrative friendliness), not the underlying seconds math (which already spans the full end day).
# * No custom rate control—only coin presets, per your request.

import math
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
import io

import pandas as pd
import numpy as np
import streamlit as st

# Optional PDF export
try:
    from reportlab.lib.pagesizes import LETTER
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
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
]

def money(x: float) -> str:
    return f"${x:,.2f}"

def start_of_day(dt_date: date) -> datetime:
    # 00:00:00 local time
    return datetime.combine(dt_date, time.min).replace(tzinfo=LA_TZ)

def end_of_day(dt_date: date) -> datetime:
    # 23:59:59.999999 local time
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

def solve_rate_for_target(seconds: float, unit: str, target_amount: float) -> float:
    units = seconds / TIME_UNITS[unit]
    return target_amount / units if units > 0 else float("nan")

def closest_scenarios(seconds: float, target_amount: float, units_list, coins_list, top_k=20):
    rows = []
    for tu in units_list:
        for name, val in coins_list:
            amt = compute_amount(seconds, tu, val)
            diff = abs(amt - target_amount)
            rows.append({
                "Time Unit": tu,
                "Coin": name,
                "Rate (per unit)": val,
                "Amount": amt,
                "Abs Δ from target": diff,
                "% Δ": (diff / target_amount * 100.0) if target_amount else np.nan,
            })
    df = pd.DataFrame(rows)
    df.sort_values(by=["Abs Δ from target"], inplace=True, ascending=True)
    return df.head(top_k), df

def add_future_seconds(add_days: float = 0.0, add_years: float = 0.0) -> float:
    # Simple: 1 civil year ≈ 365.2425 days
    total_days = add_days + (add_years * 365.2425)
    return total_days * 86400.0

def make_narrative(start_dt: datetime, end_dt: datetime, seconds: float, unit: str, rate: float, amount: float, inclusive_days_flag: bool) -> str:
    au = all_units(seconds)
    units_val = {
        "second": au["seconds"],
        "minute": au["minutes"],
        "hour":   au["hours"],
        "day":    au["days"],
    }[unit]

    # Days for display (optionally inclusive)
    disp_days = au["days"] + (1.0 if inclusive_days_flag else 0.0)

    return (
        f"From {start_dt.date():%b %d, %Y} through {end_dt.date():%b %d, %Y}, "
        f"that’s approximately {units_val:,.0f} {unit}{'' if units_val == 1 else 's'} "
        f"({disp_days:,.2f} day span for juror-friendly counting). "
        f"At {money(rate)} per {unit}, the past pain-and-suffering equals {money(amount)}."
    )

def export_summary_pdf(buffer: io.BytesIO, header: str, summary: dict, df_scenarios: pd.DataFrame | None):
    doc = SimpleDocTemplate(buffer, pagesize=LETTER,
                            rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    flow = []
    flow.append(Paragraph(header, styles["Title"]))
    flow.append(Spacer(1, 0.20 * inch))

    for k, v in summary.items():
        flow.append(Paragraph(f"<b>{k}:</b> {v}", styles["BodyText"]))
        flow.append(Spacer(1, 0.06 * inch))

    flow.append(Spacer(1, 0.12 * inch))

    if df_scenarios is not None and not df_scenarios.empty:
        flow.append(Paragraph("Top Target-Match Scenarios", styles["Heading2"]))
        show = df_scenarios.head(12).copy()
        show["Amount"] = show["Amount"].map(money)
        show["Rate (per unit)"] = show["Rate (per unit)"].map(lambda x: f"${x:,.2f}")
        show["Abs Δ from target"] = show["Abs Δ from target"].map(money)
        show["% Δ"] = show["% Δ"].map(lambda x: f"{x:.2f}%" if pd.notna(x) else "")
        data = [show.columns.tolist()] + show.values.tolist()

        tbl = Table(data, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
            ("TEXTCOLOR", (0,0), (-1,0), colors.black),
            ("ALIGN", (0,0), (-1,-1), "CENTER"),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,0), 9),
            ("FONTSIZE", (0,1), (-1,-1), 8),
            ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.whitesmoke, colors.lightyellow]),
        ]))
        flow.append(tbl)

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
st.caption("Date-only input • Coin presets only • Target solver • Scenario grid • Narrative • Exports")

with st.sidebar:
    st.header("Inputs")

    st.subheader("Date Range (LA)")
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

    st.subheader("Targeting (optional)")
    target_toggle = st.checkbox("Target a number (e.g., $400,000)", value=True)
    target_amount = st.number_input(
        "Target total $",
        min_value=0.0, value=400_000.00, step=1_000.00, format="%.2f",
        disabled=not target_toggle
    )
    target_mode = st.radio(
        "Target mode",
        options=["Show best preset combos", "Solve exact rate for current unit"],
        index=0,
        disabled=not target_toggle,
        help="Compare clean preset combos or compute the exact per-unit rate for your chosen unit."
    )

    st.subheader("Future Projection (optional)")
    add_future = st.checkbox("Add future pain window", value=False)
    fut_years = st.number_input("Future years (~365.2425 days/yr)", min_value=0.0, value=0.0, step=0.5, disabled=not add_future)
    fut_days = st.number_input("Future days", min_value=0.0, value=0.0, step=1.0, disabled=not add_future)

# Validate dates
if end_date < start_date:
    st.error("End date must be on or after the date of loss.")
    st.stop()

# Build datetime span covering whole days
start_dt = start_of_day(start_date)
end_dt = end_of_day(end_date)

# Base window seconds (past pain)
base_seconds = elapsed_seconds(start_dt, end_dt)

# Future projection seconds
future_seconds = add_future_seconds(add_days=fut_days, add_years=fut_years) if add_future else 0.0
total_seconds = base_seconds + future_seconds

# ---------- Main Hero & Breakdown ----------

hero_col, info_col = st.columns([1.1, 1.2])

with hero_col:
    amount_now = compute_amount(base_seconds, unit, applied_rate)
    amount_total = compute_amount(total_seconds, unit, applied_rate)

    st.metric(
        label=f"Past Pain @ {money(applied_rate)}/{unit}",
        value=money(amount_now)
    )

    if add_future:
        st.metric(
            label=f"Past + Future ({fut_years}y, {fut_days}d) @ {money(applied_rate)}/{unit}",
            value=money(amount_total)
        )

    st.caption("Display rounds to cents; internal math retains full precision.")

with info_col:
    au_base = all_units(base_seconds)
    au_total = all_units(total_seconds)

    # Day count display (optionally inclusive)
    days_disp = au_base["days"] + (1.0 if inclusive_days else 0.0)
    days_total_disp = au_total["days"] + (1.0 if inclusive_days else 0.0)

    st.subheader("Time Breakdown")
    tb1, tb2 = st.columns(2)
    with tb1:
        st.markdown("**Past window**")
        st.write(f"Start: {start_dt.date():%b %d, %Y}")
        st.write(f"End:   {end_dt.date():%b %d, %Y}")
        st.write(f"Seconds: {au_base['seconds']:,.0f}")
        st.write(f"Minutes: {au_base['minutes']:,.0f}")
        st.write(f"Hours:   {au_base['hours']:,.0f}")
        st.write(f"Days:    {days_disp:,.2f}" + (" (inclusive display)" if inclusive_days else ""))

    with tb2:
        if add_future:
            projected_end_dt = end_dt + timedelta(seconds=future_seconds)
            st.markdown("**Past + Future window**")
            st.write(f"Projected end: {projected_end_dt.date():%b %d, %Y}")
            st.write(f"Seconds: {au_total['seconds']:,.0f}")
            st.write(f"Minutes: {au_total['minutes']:,.0f}")
            st.write(f"Hours:   {au_total['hours']:,.0f}")
            st.write(f"Days:    {days_total_disp:,.2f}" + (" (inclusive display)" if inclusive_days else ""))
        else:
            st.info("No future window added. Toggle it in the sidebar to project forward.")

# ---------- Targeting ----------

top_df = None
full_df = None
if target_toggle and target_amount > 0:
    st.markdown("---")
    st.subheader("🎯 Targeting")

    if target_mode == "Show best preset combos":
        units_list = list(TIME_UNITS.keys())
        top_df, full_df = closest_scenarios(base_seconds, target_amount, units_list, COIN_PRESETS, top_k=20)

        view = top_df.copy()
        view["Amount"] = view["Amount"].map(money)
        view["Rate (per unit)"] = view["Rate (per unit)"].map(lambda x: f"${x:,.2f}")
        view["Abs Δ from target"] = view["Abs Δ from target"].map(money)
        view["% Δ"] = view["% Δ"].map(lambda x: f"{x:.2f}%")
        st.dataframe(view, use_container_width=True)

        st.caption("Closest 'clean' combinations (coin presets × time units) for the **past** window.")
    else:
        req_rate = solve_rate_for_target(base_seconds, unit, target_amount)
        if math.isfinite(req_rate):
            st.success(
                f"To hit {money(target_amount)} using **{unit}**, use a rate of **{money(req_rate)} per {unit}** (past window)."
            )
            st.caption("Tip: round to a nearby clean coin/unit combo for persuasion, then display that result above.")
        else:
            st.error("Cannot solve for rate: zero elapsed units.")

# ---------- Narrative helper ----------

st.markdown("---")
st.subheader("📝 Narrative Helper")

narr = make_narrative(start_dt, end_dt, base_seconds, unit, applied_rate, compute_amount(base_seconds, unit, applied_rate), inclusive_days)
# Fix the param order: we passed amount in the wrong place; recompute properly:
amt_for_narr = compute_amount(base_seconds, unit, applied_rate)
narr = make_narrative(start_dt, end_dt, base_seconds, unit, applied_rate, amt_for_narr, inclusive_days)

st.text_area("Copy-ready paragraph", value=narr, height=140)

# ---------- Exports ----------

st.markdown("---")
st.subheader("📤 Exports")

# CSV export (best scenarios)
if top_df is not None and not top_df.empty:
    csv_bytes = top_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download scenarios (CSV)",
        data=csv_bytes,
        file_name="target_scenarios.csv",
        mime="text/csv",
        use_container_width=True
    )
else:
    st.caption("Run 'Show best preset combos' in Targeting to enable CSV export of scenarios.")

# PDF export (if available)
if REPORTLAB_AVAILABLE:
    summary_info = {
        "Start": f"{start_dt.date():%b %d, %Y}",
        "End": f"{end_dt.date():%b %d, %Y}",
        "Unit & Rate": f"{unit} @ {money(applied_rate)}/{unit}",
        "Past Amount": money(amount_now),
        "Future Added": f"{fut_years} years, {fut_days} days" if add_future else "None",
        "Past + Future Amount": money(amount_total) if add_future else "—",
        "Inclusive days (display)": "Yes" if inclusive_days else "No",
        "Generated": datetime.now(LA_TZ).strftime("%b %d, %Y, %I:%M %p %Z"),
    }

    pdf_buf = io.BytesIO()
    export_summary_pdf(pdf_buf, "Time × Money Damages Summary", summary_info, top_df)

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
