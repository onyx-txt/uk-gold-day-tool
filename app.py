"""
UK Gold Day Dashboard - V1
Checks the next 7 days across two weather models to find perfect UK days.
A "Gold Day" = dry + sunny + warm enough, confirmed by BOTH models.
"""

import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta

# ─────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────

# The five UK cities with their lat/lon coordinates
CITIES = {
    "London":     {"lat": 51.5074, "lon": -0.1278},
    "Manchester": {"lat": 53.4808, "lon": -2.2426},
    "Birmingham": {"lat": 52.4862, "lon": -1.8904},
    "Glasgow":    {"lat": 55.8642, "lon": -4.2518},
    "Cardiff":    {"lat": 51.4816, "lon": -3.1791},
}

# The two weather models we fetch from Open-Meteo
# ukmo_seamless  = UK Met Office model  (very accurate for Britain)
# ecmwf_ifs025   = European Centre model (global benchmark)
MODELS = ["ukmo_seamless", "ecmwf_ifs025"]

# Sunshine threshold: 4 hours = 4 × 3600 seconds
SUNSHINE_THRESHOLD_SECONDS = 4 * 3600   # 14,400 s

# ─────────────────────────────────────────────
#  DATA FETCHING  (cached for 1 hour)
# ─────────────────────────────────────────────

@st.cache_data(ttl=3600)   # re-fetch at most once per hour to be kind to the API
def fetch_forecast(lat: float, lon: float, model: str) -> pd.DataFrame | None:
    """
    Call the Open-Meteo API for one city + one weather model.
    Returns a DataFrame with columns:
        date, temperature_max, precipitation_sum, sunshine_duration
    Returns None if the request fails.
    """
    url = "https://api.open-meteo.com/v1/forecast"

    params = {
        "latitude":  lat,
        "longitude": lon,
        "daily": [
            "temperature_2m_max",     # highest temp of the day (°C)
            "precipitation_sum",      # total rain/snow (mm)
            "sunshine_duration",      # seconds of sunshine
        ],
        "timezone":   "Europe/London",
        "forecast_days": 7,
        "models":     model,          # which weather model to use
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()   # raise an error for bad status codes
        data = response.json()

        # Build a tidy DataFrame from the API response
        df = pd.DataFrame({
            "date":               data["daily"]["time"],
            "temperature_max":    data["daily"]["temperature_2m_max"],
            "precipitation_sum":  data["daily"]["precipitation_sum"],
            "sunshine_duration":  data["daily"]["sunshine_duration"],
        })

        # Convert the date strings to real date objects so we can format them nicely
        df["date"] = pd.to_datetime(df["date"]).dt.date

        return df

    except Exception as e:
        # If anything goes wrong (network issue, API down, etc.) return None
        st.warning(f"Could not fetch data from model '{model}': {e}")
        return None


# ─────────────────────────────────────────────
#  GOLD DAY LOGIC
# ─────────────────────────────────────────────

def is_gold_day(row: pd.Series, min_temp: float) -> tuple[bool, str]:
    """
    Check whether a single forecast row qualifies as a Gold Day.

    Returns:
        (True,  "GOLD")           – all three conditions met
        (False, "RAIN")           – rain predicted
        (False, "COLD")           – temperature too low
        (False, "CLOUDY")         – not enough sunshine
        (False, "COLD+CLOUDY")    – both temp and sunshine fail
    """
    warm_enough  = row["temperature_max"]   >= min_temp
    no_rain      = row["precipitation_sum"] == 0.0
    sunny_enough = row["sunshine_duration"] >= SUNSHINE_THRESHOLD_SECONDS

    # Rain is the biggest disqualifier – check it first
    if not no_rain:
        return False, "RAIN"

    # Check the remaining two conditions together
    if warm_enough and sunny_enough:
        return True, "GOLD"
    elif not warm_enough and not sunny_enough:
        return False, "COLD+CLOUDY"
    elif not warm_enough:
        return False, "COLD"
    else:
        return False, "CLOUDY"


# ─────────────────────────────────────────────
#  STREAMLIT UI
# ─────────────────────────────────────────────

def main():
    # ── Page setup ──────────────────────────────
    st.set_page_config(
        page_title="🌤 UK Gold Day",
        page_icon="☀️",
        layout="centered",
    )

    # Inject a small amount of CSS to make Gold Day banners pop
    st.markdown("""
        <style>
            .gold-banner {
                background: linear-gradient(90deg, #f9c74f, #f4a261);
                border-radius: 10px;
                padding: 14px 20px;
                font-size: 1.15rem;
                font-weight: 700;
                color: #1a1a1a;
                margin-bottom: 8px;
            }
            .grey-card {
                background: #f0f0f0;
                border-radius: 10px;
                padding: 12px 20px;
                font-size: 0.95rem;
                color: #555;
                margin-bottom: 8px;
            }
            .rain-card {
                background: #dce8f5;
                border-radius: 10px;
                padding: 12px 20px;
                font-size: 0.95rem;
                color: #2c5f8a;
                margin-bottom: 8px;
            }
        </style>
    """, unsafe_allow_html=True)

    # ── Header ──────────────────────────────────
    st.title("☀️ UK Gold Day Dashboard")
    st.caption(
        "A **Gold Day** is dry, sunny (4 h+), and warm — "
        "confirmed by **both** the Met Office and ECMWF models."
    )
    st.divider()

    # ── Sidebar controls ────────────────────────
    st.sidebar.header("⚙️ Settings")

    city_name = st.sidebar.selectbox(
        "📍 Choose a city",
        options=list(CITIES.keys()),
    )

    min_temp = st.sidebar.slider(
        "🌡️ Minimum temperature (°C)",
        min_value=0,
        max_value=25,
        value=11,        # default Gold Day threshold
        step=1,
        help="A day must reach at least this temperature to qualify.",
    )

    st.sidebar.divider()
    st.sidebar.info(
        "**Models used:**\n"
        "- 🇬🇧 Met Office (ukmo_seamless)\n"
        "- 🌍 ECMWF IFS025\n\n"
        "Both must agree for a ☀️ Gold Day."
    )

    # ── Fetch data ──────────────────────────────
    coords = CITIES[city_name]

    with st.spinner(f"Fetching forecasts for {city_name}…"):
        df_ukmo  = fetch_forecast(coords["lat"], coords["lon"], "ukmo_seamless")
        df_ecmwf = fetch_forecast(coords["lat"], coords["lon"], "ecmwf_ifs025")

    # If either model failed completely, stop here
    if df_ukmo is None or df_ecmwf is None:
        st.error("❌ Could not load forecast data. Please try again later.")
        return

    # ── Compare the two models day-by-day ───────
    st.subheader(f"📅 7-Day Forecast — {city_name}")
    st.caption(f"Temperature threshold: **{min_temp}°C** | Sunshine: **4 h+** | Precipitation: **0 mm**")

    gold_count = 0   # track how many Gold Days we find

    for i in range(7):
        # Pull today's row from each model
        row_ukmo  = df_ukmo.iloc[i]
        row_ecmwf = df_ecmwf.iloc[i]

        # Format the date nicely, e.g. "Mon 14 Jul"
        day_label = row_ukmo["date"].strftime("%a %d %b")

        # ── THE CORE CONSENSUS CHECK ──
        # We call is_gold_day() for EACH model separately.
        # A day is only "GOLD" if BOTH models return True.
        ukmo_gold,  ukmo_reason  = is_gold_day(row_ukmo,  min_temp)
        ecmwf_gold, ecmwf_reason = is_gold_day(row_ecmwf, min_temp)

        # Both must agree → True AND True = consensus Gold Day
        consensus_gold = ukmo_gold and ecmwf_gold

        # ── Build a detail line showing what each model thinks ──
        def model_summary(row):
            return (
                f"{row['temperature_max']:.0f}°C · "
                f"{row['precipitation_sum']:.1f} mm rain · "
                f"{row['sunshine_duration']/3600:.1f} h sun"
            )

        detail = (
            f"Met Office: {model_summary(row_ukmo)}  |  "
            f"ECMWF: {model_summary(row_ecmwf)}"
        )

        # ── Render the correct banner ──
        if consensus_gold:
            # ✅ Both models agree: perfect day!
            gold_count += 1
            st.markdown(
                f'<div class="gold-banner">☀️ GOLD DAY — {day_label}<br>'
                f'<span style="font-weight:400;font-size:0.85rem;">{detail}</span></div>',
                unsafe_allow_html=True,
            )

        else:
            # ❌ Not a Gold Day — figure out the best message to show.
            # We check if EITHER model predicts rain, because rain from
            # just one major model is still worth flagging.
            either_rain = (ukmo_reason == "RAIN") or (ecmwf_reason == "RAIN")

            if either_rain:
                st.markdown(
                    f'<div class="rain-card">🌧️ Rain Predicted — {day_label}<br>'
                    f'<span style="font-size:0.82rem;">{detail}</span></div>',
                    unsafe_allow_html=True,
                )
            else:
                # Dry but not warm/sunny enough
                st.markdown(
                    f'<div class="grey-card">☁️ Not quite — {day_label}<br>'
                    f'<span style="font-size:0.82rem;">{detail}</span></div>',
                    unsafe_allow_html=True,
                )

    # ── Summary ─────────────────────────────────
    st.divider()

    if gold_count == 0:
        st.info("😔 No Gold Days found in the next 7 days. Check back tomorrow!")
    elif gold_count == 1:
        st.success(f"🌟 **1 Gold Day** found this week — make the most of it!")
    else:
        st.success(f"🌟 **{gold_count} Gold Days** found this week — great week ahead!")

    # ── Footer ──────────────────────────────────
    st.caption(
        "Data: [Open-Meteo](https://open-meteo.com/) · "
        "Free & open-source weather API · "
        f"Last refreshed: {datetime.now().strftime('%H:%M on %d %b %Y')}"
    )


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    main()
