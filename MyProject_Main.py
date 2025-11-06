

import subprocess, sys, os

# --- Fix yfinance/websockets issue on GitHub Actions ---
subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", "websockets"], check=False)
subprocess.run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "websockets==12.0"], check=True)

os.environ["YFINANCE_NO_WEBSOCKETS"] = "true"

# Optional: confirm version
import importlib.metadata
print("✅ websockets version:", importlib.metadata.version("websockets"))
from datetime import date, timedelta
import pandas as pd
import yfinance as yf
import requests
from alpaca_trade_api.rest import REST
from twilio.rest import Client

# =========================
# DATE SETUP
# =========================
today = date.today()
print("Today's date:", today)

last_mond = today - timedelta(days=7)
last_fri = today - timedelta(days=3)

# =========================
# BITCOIN WEEKLY PERFORMANCE
# =========================
bitcoin = yf.download("FBTC", start=last_mond, end=last_fri)
perf = round((bitcoin["Close"].iloc[-1] - bitcoin["Close"].iloc[0]) / bitcoin["Close"].iloc[0] * 100, 2)
print("FBTC % change:", perf)

# =========================
# FEAR AND GREED INDEX
# =========================
url = "https://pro-api.coinmarketcap.com/v3/fear-and-greed/latest"
headers = {
    "Accepts": "application/json",
    "X-CMC_PRO_API_KEY": os.getenv("CMC_KEY")
}
response = requests.get(url, headers=headers)
response.raise_for_status()
data = response.json()
fng_value = data["data"]["value"]
print("Fear & Greed Index:", fng_value)

# =========================
# US DOLLAR INDEX (DXY)
# =========================
us_dol_ind = yf.download("DX-Y.NYB", start=last_mond - timedelta(days=7), end=today, interval="1d")
us_dol_ind = us_dol_ind.sort_index()
close_mond = us_dol_ind["Close"].asof(str(last_mond))
close_fri = us_dol_ind["Close"].asof(str(last_fri))
dol_ind_pct_change = ((close_fri - close_mond) / close_mond) * 100
print("USD Index % change:", round(dol_ind_pct_change, 2))

# =========================
# M2 MONEY SUPPLY
# =========================
fred_key = os.getenv("FRED_KEY")
url = "https://api.stlouisfed.org/fred/series/observations"
params = {
    "series_id": "M2SL",
    "api_key": fred_key,
    "file_type": "json",
    "observation_start": "2010-01-01"
}
response = requests.get(url, params=params)
m2 = pd.DataFrame(response.json()["observations"])
m2["date"] = pd.to_datetime(m2["date"])
m2["value"] = pd.to_numeric(m2["value"], errors="coerce")
m2 = m2.dropna(subset=["value"]).set_index("date").sort_index()
latest = m2.iloc[-1]["value"]
previous = m2.iloc[-2]["value"]
m2_pct_change = ((latest - previous) / previous) * 100
print("M2 % change:", round(m2_pct_change, 2))

# =========================
# 10-YEAR TREASURY YIELD
# =========================
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
close_mond = treas10["value"].asof(str(last_mond))
close_fri = treas10["value"].asof(str(last_fri))
Tres_Yield_pct_change = ((close_fri - close_mond) / close_mond) * 100
print("10Y Yield % change:", round(Tres_Yield_pct_change, 2))

# =========================
# INDEX STRENGTH LOGIC
# =========================
index_strength = 0.25
if dol_ind_pct_change.iloc[0] < 0:
    index_strength += 0.25
if m2_pct_change > 0:
    index_strength += 0.25
if Tres_Yield_pct_change > 0:
    index_strength += 0.25
print("Index strength:", index_strength)

# =========================
# ALLOCATIONS
# =========================
contribution = 150
alloc = {"BTC-USD": 0, "VOO": 0, "BIL": 0}

if fng_value < 35:
    alloc["BTC-USD"] = index_strength
    alloc["VOO"] = 1 - index_strength
elif 35 <= fng_value < 50:
    alloc["BTC-USD"] = 0.75 * index_strength
    alloc["VOO"] = 1 - alloc["BTC-USD"]
elif 50 <= fng_value < 80:
    alloc["BTC-USD"] = 0.5 * index_strength
    remaining = 1 - alloc["BTC-USD"]
    alloc["VOO"] = remaining / 2
    alloc["BIL"] = remaining / 2
else:
    alloc["BIL"] = 1.0

btc_alloc = contribution * alloc["BTC-USD"]
voo_alloc = contribution * alloc["VOO"]
bil_alloc = contribution * alloc["BIL"]

print(f"BTC alloc: ${btc_alloc:.2f}, VOO alloc: ${voo_alloc:.2f}, BIL alloc: ${bil_alloc:.2f}")

# =========================
# ALPACA ORDERS
# =========================
api = REST(
    os.getenv("ALPACA_KEY_ID"),
    os.getenv("ALPACA_SECRET_KEY"),
    base_url="https://paper-api.alpaca.markets"
)

allocations = {
    "FBTC": btc_alloc,
    "VOO": voo_alloc,
    "VBIL": bil_alloc
}

for symbol, notional in allocations.items():
    if notional > 0:
        api.submit_order(
            symbol=symbol,
            notional=notional,
            side="buy",
            type="market",
            time_in_force="day"
        )

# =========================
# TWILIO SUMMARY TEXT
# =========================
summary = (
    f"Weekly Allocation Summary ({today}):\n"
    f"FBTC: ${btc_alloc:.2f}, VOO: ${voo_alloc:.2f}, BIL: ${bil_alloc:.2f}\n\n"
    f"F&G Index: {fng_value}\n"
    f"USD Δ: {dol_ind_pct_change:.2f}% | M2 Δ: {m2_pct_change:.2f}% | 10Y Δ: {Tres_Yield_pct_change:.2f}%\n"
    f"Index Strength: {index_strength}"
)

print(summary)

try:
    client = Client(
        os.getenv("TWILIO_ACCOUNT_SID"),
        os.getenv("TWILIO_AUTH_TOKEN")
    )
    message = client.messages.create(
        to=os.getenv("MY_PHONE_NUMBER"),
        from_=os.getenv("TWILIO_PHONE_NUMBER"),
        body=summary
    )
    print("SMS sent:", message.sid)
except Exception as e:
    print("Error sending SMS:", e)





