

import subprocess, sys, os, csv
from datetime import date, timedelta
import pandas as pd
import yfinance as yf
import requests
from alpaca_trade_api.rest import REST
from twilio.rest import Client
import importlib.metadata

# ==========================================================
# FIX FOR YFINANCE/WEBSOCKETS CONFLICT (GitHub Actions)
# ==========================================================
subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", "websockets"], check=False)
subprocess.run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "websockets==12.0"], check=True)
os.environ["YFINANCE_NO_WEBSOCKETS"] = "true"

print("✅ websockets version:", importlib.metadata.version("websockets"))

# ==========================================================
# HELPER FUNCTIONS
# ==========================================================
def scalar(x):
    """Safely extract a scalar from a Pandas Series or return the value itself."""
    if isinstance(x, pd.Series) and not x.empty:
        return x.iloc[0]
    return x


def get_allocations(fng_value, index_strength, contribution=150):
    """Calculate allocations dynamically based on Fear & Greed Index and macro index strength."""
    risk_zones = [
        {"min": 0, "max": 35, "btc_factor": 1.0, "desc": "Extreme Fear"},
        {"min": 35, "max": 50, "btc_factor": 0.75, "desc": "Fear"},
        {"min": 50, "max": 80, "btc_factor": 0.5, "desc": "Neutral/Greed"},
        {"min": 80, "max": 101, "btc_factor": 0.0, "desc": "Extreme Greed"},
    ]

    alloc = {"BTC-USD": 0, "VOO": 0, "BIL": 0}

    # Find F&G zone
    for z in risk_zones:
        if z["min"] <= fng_value < z["max"]:
            btc_factor = z["btc_factor"]
            zone_desc = z["desc"]
            break
    else:
        btc_factor = 0.5
        zone_desc = "Unknown"

    # --- Allocation logic ---
    btc_weight = index_strength * btc_factor
    equity_weight = (1 - btc_weight) * (1 if btc_factor >= 0.5 else 0.5)
    cash_weight = 1 - btc_weight - equity_weight

    # Normalize weights
    total = btc_weight + equity_weight + cash_weight
    for k, v in [("BTC-USD", btc_weight), ("VOO", equity_weight), ("BIL", cash_weight)]:
        alloc[k] = v / total

    # Convert to dollars
    alloc_dollars = {k: v * contribution for k, v in alloc.items()}

    print("\n========== ALLOCATION LOGIC ==========")
    print(f"F&G Zone: {zone_desc} ({fng_value}) | Index Strength: {index_strength:.2f}")
    print(f"BTC Factor: {btc_factor} → BTC Weight: {alloc['BTC-USD']:.2f}")
    print(f"VOO Weight: {alloc['VOO']:.2f} | BIL Weight: {alloc['BIL']:.2f}")
    print("======================================\n")

    return alloc, alloc_dollars, zone_desc, btc_factor


def log_allocation(
    today, fng_value, zone_desc, index_strength,
    dol_ind_pct_change, m2_pct_change, Tres_Yield_pct_change,
    alloc
):
    """Append the week’s allocation and macro data to a CSV log file."""
    file_path = "allocation_history.csv"
    headers = [
        "Date", "F&G Index", "Zone", "Index Strength",
        "USD %Δ", "M2 %Δ", "10Y %Δ",
        "BTC Weight", "VOO Weight", "BIL Weight"
    ]
    row = [
        today, fng_value, zone_desc, round(index_strength, 2),
        round(dol_ind_pct_change, 2), round(m2_pct_change, 2), round(Tres_Yield_pct_change, 2),
        round(alloc["BTC-USD"], 2), round(alloc["VOO"], 2), round(alloc["BIL"], 2)
    ]
    write_header = not os.path.exists(file_path)

    with open(file_path, mode="a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(headers)
        writer.writerow(row)
    print(f"✅ Logged weekly data to {file_path}\n")


# ==========================================================
# DATE SETUP
# ==========================================================
today = date.today()
print("Today's date:", today)
last_mond = today - timedelta(days=7)
last_fri = today - timedelta(days=3)

# ==========================================================
# BITCOIN WEEKLY PERFORMANCE
# ==========================================================
bitcoin = yf.download("FBTC", start=last_mond, end=last_fri)
perf = round((bitcoin["Close"].iloc[-1] - bitcoin["Close"].iloc[0]) / bitcoin["Close"].iloc[0] * 100, 2)
print("FBTC % change:", perf)

# ==========================================================
# FEAR AND GREED INDEX
# ==========================================================
url = "https://pro-api.coinmarketcap.com/v3/fear-and-greed/latest"
headers = {"Accepts": "application/json", "X-CMC_PRO_API_KEY": os.getenv("CMC_KEY")}
response = requests.get(url, headers=headers)
response.raise_for_status()
data = response.json()
fng_value = int(data["data"]["value"])
print("Fear & Greed Index:", fng_value)

# ==========================================================
# US DOLLAR INDEX (DXY)
# ==========================================================
us_dol_ind = yf.download("DX-Y.NYB", start=last_mond - timedelta(days=7), end=today, interval="1d").sort_index()
close_mond = scalar(us_dol_ind["Close"].asof(str(last_mond)))
close_fri = scalar(us_dol_ind["Close"].asof(str(last_fri)))
dol_ind_pct_change = ((close_fri - close_mond) / close_mond) * 100
print("USD Index % change:", round(dol_ind_pct_change, 2))

# ==========================================================
# M2 MONEY SUPPLY
# ==========================================================
fred_key = os.getenv("FRED_KEY")
url = "https://api.stlouisfed.org/fred/series/observations"
params = {"series_id": "M2SL", "api_key": fred_key, "file_type": "json", "observation_start": "2010-01-01"}
response = requests.get(url, params=params)
m2 = pd.DataFrame(response.json()["observations"])
m2["date"] = pd.to_datetime(m2["date"])
m2["value"] = pd.to_numeric(m2["value"], errors="coerce")
m2 = m2.dropna(subset=["value"]).set_index("date").sort_index()
m2_pct_change = ((m2.iloc[-1]["value"] - m2.iloc[-2]["value"]) / m2.iloc[-2]["value"]) * 100
print("M2 % change:", round(m2_pct_change, 2))

# ==========================================================
# 10-YEAR TREASURY YIELD
# ==========================================================
params = {
    "series_id": "DGS10",
    "api_key": fred_key,
    "file_type": "json",
    "observation_start": (today - timedelta(days=30)).strftime("%Y-%m-%d")
}
response = requests.get(url, params=params)
treas10 = pd.DataFrame(response.json()["observations"])
treas10["date"] = pd.to_datetime(treas10["date"])
treas10["value"] = pd.to_numeric(treas10["value"], errors="coerce")
treas10 = treas10.dropna(subset=["value"]).set_index("date").sort_index()
close_mond = scalar(treas10["value"].asof(str(last_mond)))
close_fri = scalar(treas10["value"].asof(str(last_fri)))
Tres_Yield_pct_change = ((close_fri - close_mond) / close_mond) * 100
print("10Y Yield % change:", round(Tres_Yield_pct_change, 2))

# ==========================================================
# INDEX STRENGTH LOGIC
# ==========================================================
index_strength = 0.25
if dol_ind_pct_change < 0:
    index_strength += 0.25
if m2_pct_change > 0:
    index_strength += 0.25
if Tres_Yield_pct_change > 0:
    index_strength += 0.25
print("Index strength:", index_strength)

# ==========================================================
# DYNAMIC ALLOCATIONS
# ==========================================================
alloc, alloc_dollars, zone_desc, btc_factor = get_allocations(fng_value, index_strength, contribution=150)

btc_alloc = alloc_dollars["BTC-USD"]
voo_alloc = alloc_dollars["VOO"]
bil_alloc = alloc_dollars["BIL"]

print(f"BTC alloc: ${btc_alloc:.2f}, VOO alloc: ${voo_alloc:.2f}, BIL alloc: ${bil_alloc:.2f}")

# ==========================================================
# LOG WEEKLY DATA
# ==========================================================
log_allocation(today, fng_value, zone_desc, index_strength,
               dol_ind_pct_change, m2_pct_change, Tres_Yield_pct_change, alloc)

# ==========================================================
# ALPACA ORDERS
# ==========================================================
api = REST(os.getenv("ALPACA_KEY_ID"), os.getenv("ALPACA_SECRET_KEY"),
           base_url="https://paper-api.alpaca.markets")

allocations = {"FBTC": btc_alloc, "VOO": voo_alloc, "VBIL": bil_alloc}

for symbol, notional in allocations.items():
    if notional > 0:
        api.submit_order(symbol=symbol, notional=notional,
                         side="buy", type="market", time_in_force="day")

# ==========================================================
# TWILIO SUMMARY TEXT
# ==========================================================
summary = (
    f"Weekly Allocation Summary ({today}):\n"
    f"FBTC: ${btc_alloc:.2f}, VOO: ${voo_alloc:.2f}, BIL: ${bil_alloc:.2f}\n\n"
    f"F&G Index: {fng_value} ({zone_desc})\n"
    f"USD Δ: {round(dol_ind_pct_change, 2):.2f}% | M2 Δ: {round(m2_pct_change, 2):.2f}% | 10Y Δ: {round(Tres_Yield_pct_change, 2):.2f}%\n"
    f"Index Strength: {index_strength:.2f} | BTC Factor: {btc_factor}\n"
    f"Weights → BTC: {alloc['BTC-USD']:.2f}, VOO: {alloc['VOO']:.2f}, BIL: {alloc['BIL']:.2f}"
)

print(summary)

try:
    client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
    message = client.messages.create(
        to=os.getenv("MY_PHONE_NUMBER"),
        from_=os.getenv("TWILIO_PHONE_NUMBER"),
        body=summary
    )
    print("SMS sent:", message.sid)
except Exception as e:
    print("Error sending SMS:", e)







