# app.py
# Streamlit "Time × Money" Damages Calculator
# by Max's AI dev buddy 🤝

import math
from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo
import io

import pandas as pd
import numpy as np
import streamlit as st

# Optional PDF export
try:
    from reportlab.lib.pagesizes import LETTER
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import inch
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors
    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False


# ---------- Constants & helpers ----------

LA_TZ = ZoneInfo("America/Los_Angeles")

TIME_UNITS = {
    "second": 1,
    "minute": 60,
    "hour": 3600,
    "day": 86400,  # elapsed seconds; DST handled at datetime diff layer
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

def as_tzaware(d: date, t: time, tz=LA_TZ) -> datetime:
    # Combine date and time, assume tz-local naive -> make aware in LA_TZ
    naive = datetime.combine(d, t)
    return naive.replace(tzinfo=tz)

def elapsed_seconds(start_dt: datetime, end_dt: datetime) -> float:
    """Precise elapsed seconds (exclusive end)."""
    delta = end_dt - start_dt
    return delta.total_seconds()

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
                "Rate (per unit)": val,
                "Coin": name,
                "Amount": amt,
                "Abs Δ from target": diff,
                "% Δ": (diff / target_amount * 100.0) if target_amount else np.nan,
            })
    df = pd.DataFrame(rows)
    df.sort_values(by=["Abs Δ from target"], inplace=True, ascending=True)
    return df.head(top_k), df

def add_future_seconds(base_end: datetime, add_days: float = 0.0, add_years: float = 0.0) -> float:
    """Simple future projection: years≈365.2425 days to stay civil (no extra deps)."""
    total_days = add_days + (add_years * 365.2425)
    return total_days * 86400.0

def make_narrative(start_dt: datetime, end_dt: datetime, seconds: float, unit: str, rate: float, amount: float) -> str:
    au = all_units(seconds)
    if unit == "minute":
        units_val = au["minutes"]
    elif unit == "hour":
        units_val = au["hours"]
    elif unit == "day":
        units_val = au["days"]
    else:
        units_val = au["seconds"]

    return (
        f"From {start_dt.strftime('%b %d, %Y, %I:%M %p %Z')} to "
        f"{end_dt.strftime('%b %d, %Y, %I:%M %p %Z')}, that’s approximately "
        f"{units_val:,.0f} {unit}{'' if units_val == 1 else 's'} of continuous pain. "
        f"At {money(rate)} per {unit}, the past pain-and-suffering equals {money(amount)}."
    )

def export_summary_pdf(buffer: io.BytesIO, header: str, summary: dict, df_scenarios: pd.DataFrame | None):
    """Write a simple 1–2 page PDF to the buffer."""
    doc = SimpleDocTemplate(buffer, pagesize=LETTER,
                            rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    flow = []

    flow.append(Paragraph(header, styles["Title"]))
    flow.append(Spacer(1, 0.20 * inch))

    # Summary bullets
    for k, v in summary.items():
        flow.append(Paragraph(f"<b>{k}:</b> {v}", styles["BodyText"]))
        flow.append(Spacer(1, 0.06 * inch))

    flow.append(Spacer(1, 0.12 * inch))

    if df_scenarios is not None and not df_scenarios.empty:
        flow.append(Paragraph("Top Target-Match Scenarios", styles["Heading2"]))
        # Limit to first 12 to keep it tidy
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
st.caption("Convert time lived with pain into a clear, jury-friendly dollar figure. Flexible units, coin presets, target solver, and exports.")

with st.sidebar:
    st.header("Inputs")

    st.subheader("Date & Time Range (LA time)")
    colA, colB = st.columns(2)
    with colA:
        start_date = st.date_input("Date of loss", value=date(2022, 7, 28))
        start_time = st.time_input("Start time", value=time(0, 0))
    with colB:
        use_now = st.toggle("Use current time as end", value=True)
        end_date = st.date_input("End date", value=date.today(), disabled=use_now)
        end_time = st.time_input("End time", value=datetime.now(LA_TZ).time().replace(microsecond=0), disabled=use_now)

    st.subheader("Counting options")
    inclusive_days = st.checkbox("Inclusive days (add 1 day to day count)", value=False,
                                 help="For statements like 'counting the day of the incident as a full day'.")

    st.subheader("Unit & Rate")
    unit = st.selectbox("Time unit", list(TIME_UNITS.keys()), index=1)  # default minute
    preset_names = [n for n, _ in COIN_PRESETS]
    sel_preset = st.selectbox("Coin preset", ["(none)"] + preset_names, index=4)  # default Dollar
    custom_rate = st.number_input("Custom rate (per chosen unit)", min_value=0.0, value=0.25, step=0.01)

    applied_rate = custom_rate
    if sel_preset != "(none)":
        applied_rate = dict(COIN_PRESETS)[sel_preset]

    st.subheader("Targeting (optional)")
    target_toggle = st.checkbox("Target a number (e.g., $400,000)", value=True)
    target_amount = st.number_input("Target total $", min_value=0.0, value=400_000.00, step=1_000.00, format="%.2f", disabled=not target_toggle)
    target_mode = st.radio(
        "Target mode",
        options=["Show best preset combos", "Solve exact rate for current unit"],
        index=0,
        disabled=not target_toggle,
        help="Pick whether to search nice preset combos, or directly solve the exact per-unit rate."
    )

    st.subheader("Future Projection (optional)")
    add_future = st.checkbox("Add future pain window", value=False)
    fut_years = st.number_input("Future years (adds ~365.2425 days/yr)", min_value=0.0, value=0.0, step=0.5, disabled=not add_future)
    fut_days = st.number_input("Future days", min_value=0.0, value=0.0, step=1.0, disabled=not add_future)

# Construct aware start/end
start_dt = as_tzaware(start_date, start_time, tz=LA_TZ)
if use_now:
    end_dt = datetime.now(LA_TZ)
else:
    end_dt = as_tzaware(end_date, end_time, tz=LA_TZ)

if end_dt < start_dt:
    st.error("End datetime must be after start datetime.")
    st.stop()

base_seconds = elapsed_seconds(start_dt, end_dt)
sec_for_display = base_seconds

# Inclusive-day option only affects the *day count* presentation (not the precise money calculation).
inc_days_bonus = 1.0 if inclusive_days else 0.0

# Future projection
future_seconds = 0.0
if add_future:
    future_seconds = add_future_seconds(end_dt, add_days=fut_days, add_years=fut_years)

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

    st.caption("Amounts are rounded to 2 decimals for display; internal math retains full precision.")

with info_col:
    au_base = all_units(base_seconds)
    au_total = all_units(total_seconds)

    # Day count display w/ inclusive option
    days_disp = au_base["days"] + inc_days_bonus
    days_total_disp = au_total["days"] + inc_days_bonus

    st.subheader("Time Breakdown")
    tb1, tb2 = st.columns(2)
    with tb1:
        st.markdown("**Past window**")
        st.write(f"Start: {start_dt.strftime('%b %d, %Y, %I:%M %p %Z')}")
        st.write(f"End:   {end_dt.strftime('%b %d, %Y, %I:%M %p %Z')}")
        st.write(f"Seconds: {au_base['seconds']:,.0f}")
        st.write(f"Minutes: {au_base['minutes']:,.0f}")
        st.write(f"Hours:   {au_base['hours']:,.0f}")
        st.write(f"Days:    {days_disp:,.2f}" + (" (inclusive)" if inclusive_days else ""))

    with tb2:
        if add_future:
            st.markdown("**Past + Future window**")
            st.write(f"Projected end: {(end_dt + timedelta(seconds=future_seconds)).strftime('%b %d, %Y, %I:%M %p %Z')}")
            st.write(f"Seconds: {au_total['seconds']:,.0f}")
            st.write(f"Minutes: {au_total['minutes']:,.0f}")
            st.write(f"Hours:   {au_total['hours']:,.0f}")
            st.write(f"Days:    {days_total_disp:,.2f}" + (" (inclusive)" if inclusive_days else ""))
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

        # Pretty print
        view = top_df.copy()
        view["Amount"] = view["Amount"].map(money)
        view["Rate (per unit)"] = view["Rate (per unit)"].map(lambda x: f"${x:,.2f}")
        view["Abs Δ from target"] = view["Abs Δ from target"].map(money)
        view["% Δ"] = view["% Δ"].map(lambda x: f"{x:.2f}%")
        st.dataframe(view, use_container_width=True)

        st.caption("These are the closest 'clean' combinations across coin presets and time units for the **past** window.")
    else:
        req_rate = solve_rate_for_target(base_seconds, unit, target_amount)
        if math.isfinite(req_rate):
            st.success(
                f"To hit {money(target_amount)} using **{unit}**, use a rate of **{money(req_rate)} per {unit}** (past window only)."
            )
            st.caption("Tip: round that rate to a nearby 'clean' number for persuasion, and show the new total below.")
        else:
            st.error("Cannot solve for rate: zero elapsed units.")

# ---------- Narrative helper ----------

st.markdown("---")
st.subheader("📝 Narrative Helper")

amt_for_narr = amount_now
narr = make_narrative(start_dt, end_dt, base_seconds, unit, applied_rate, amt_for_narr)
st.text_area("Copy-ready paragraph", value=narr, height=140)

# ---------- Exports ----------

st.markdown("---")
st.subheader("📤 Exports")

# CSV export of best scenarios (if any)
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
    # Build a compact summary dict
    summary_info = {
        "Start": start_dt.strftime("%b %d, %Y, %I:%M %p %Z"),
        "End": end_dt.strftime("%b %d, %Y, %I:%M %p %Z"),
        "Unit & Rate": f"{unit} @ {money(applied_rate)}/{unit}",
        "Past Amount": money(amount_now),
        "Future Added": f"{fut_years} years, {fut_days} days" if add_future else "None",
        "Past + Future Amount": money(amount_total) if add_future else "—",
        "Inclusive days": "Yes" if inclusive_days else "No",
        "Generated": datetime.now(LA_TZ).strftime("%b %d, %Y, %I:%M %p %Z"),
    }

    pdf_buf = io.BytesIO()
    hdr = "Time × Money Damages Summary"
    export_summary_pdf(pdf_buf, hdr, summary_info, top_df)

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
st.markdown(
    "<hr style='opacity:0.2'/>",
    unsafe_allow_html=True
)
st.caption("This tool provides transparent arithmetic only and is not legal advice. Always pair with case-specific facts and law.")
