
import yfinance as yf
from datetime import date, timedelta
import pandas as pd
from alpaca_trade_api.rest import REST

today = date.today()
print(today)
last_mond = today - timedelta(days=7)
last_fri = today -  timedelta(days=3)

#have variables to find stock information for prior week up to current day
bitcoin = yf.download("FBTC",start=last_mond, end=last_fri)
#getting prior week performance %change from start to end of the week
perf = round((bitcoin["Close"].iloc[-1] - bitcoin["Close"].iloc[0]) / bitcoin["Close"].iloc[0] * 100, 2)
print(perf)

#using CMC API to bring in bitcoin fear and greed index (market sentiment)
import requests
url = "https://pro-api.coinmarketcap.com/v3/fear-and-greed/latest"

headers = {
    "Accepts": "application/json",
    "X-CMC_PRO_API_KEY": "1c3d64a8ed6048c0a33298336bd775df"  # replace with your key
}

response = requests.get(url, headers=headers)
response.raise_for_status()
data = response.json()
fng_value = data["data"]["value"]

#bringing in the dollar index
us_dol_ind = yf.download("DX-Y.NYB", start=last_mond - timedelta(days=7), end=today, interval="1d")
# Find closing prices for the closest available dates
us_dol_ind = us_dol_ind.sort_index()
close_mond = us_dol_ind["Close"].asof(str(last_mond)).iloc[0]
close_fri = us_dol_ind["Close"].asof(str(last_fri)).iloc[0]
dol_ind_pct_change = ((close_fri - close_mond) / close_mond) * 100

#bring in the M2 money supply this data is updated monthly so I'm only looking at the trend between the most recent months
import pandas as pd
API_KEY = "dcba1d08fb563236473918c892eda594"
url = "https://api.stlouisfed.org/fred/series/observations"
params = {
    "series_id": "M2SL",       # M2 Money Stock (Seasonally Adjusted)
    "api_key": API_KEY,
    "file_type": "json",
    "observation_start": "2010-01-01"
}
response = requests.get(url, params=params)
data = response.json()["observations"]
# Convert to DataFrame
m2 = pd.DataFrame(data)
m2["date"] = pd.to_datetime(m2["date"])
m2["value"] = pd.to_numeric(m2["value"], errors="coerce")
m2 = m2.sort_values("date").dropna(subset=["value"]).set_index("date")
# Get the last two data points
latest = m2.iloc[-1]["value"]
previous = m2.iloc[-2]["value"]
# Compute % change
m2_pct_change = ((latest - previous) / previous) * 100


#bringing in the 10 year treasury yield 
API_KEY = "dcba1d08fb563236473918c892eda594"
url = "https://api.stlouisfed.org/fred/series/observations"
params = {
    "series_id": "DGS10",       # 10-Year Treasury Constant Maturity Rate
    "api_key": API_KEY,
    "file_type": "json",
    "observation_start": (today - timedelta(days=30)).strftime("%Y-%m-%d")  # pull last ~month of data
}
response = requests.get(url, params=params)
data = response.json()["observations"]
# Convert to DataFrame
treas10 = pd.DataFrame(data)
treas10["date"] = pd.to_datetime(treas10["date"])
treas10["value"] = pd.to_numeric(treas10["value"], errors="coerce")
treas10 = treas10.dropna(subset=["value"]).set_index("date").sort_index()
# ----------------------------
# Find yields for last Monday & Friday (closest available trading days)
# ----------------------------
close_mond = treas10["value"].asof(str(last_mond))
close_fri = treas10["value"].asof(str(last_fri))
# Compute weekly percent change
Tres_Yield_pct_change = ((close_fri - close_mond) / close_mond) * 100



#logic for determining allocation amount based off of and index values so strength can be either {.25,.5}
index_strength = .25
# +0.25 if US Dollar Index fell (weaker dollar = risk-on sentiment)
if dol_ind_pct_change < 0:
    index_strength += 0.25
# +0.25 if M2 money supply grew (more liquidity)
if m2_pct_change > 0:
    index_strength += 0.25
# +0.25 if Treasury yields rose (often risk-off, but could mean inflation expectations rising)
if Tres_Yield_pct_change > 0:
    index_strength += 0.25
print(index_strength)

contribution = 150
tickers = ["BTC-USD", "VOO", "BIL"]
#determining allocation splits from fng index
alloc = {"BTC-USD": 0, "VOO": 0, "BIL": 0}

if fng_value < 35:
    # BTC gets boosted by index_strength
    alloc["BTC-USD"] = index_strength
    alloc["VOO"] = 1 - index_strength
elif 35 <= fng_value < 50:
    # Neutral market: split more evenly
    alloc["BTC-USD"] = 0.75 * index_strength
    alloc["VOO"] = 1 - alloc["BTC-USD"]
elif 50 <= fng_value < 80:
    # Greedy market: lean risk-off
    alloc["BTC-USD"] = 0.5 * index_strength
    remaining = 1 - alloc["BTC-USD"]
    alloc["VOO"] = remaining / 2
    alloc["BIL"] = remaining / 2
else:
    # Extreme greed: flight to safety
    alloc["BIL"] = 1.0

# Calculate dollar allocations
btc_alloc = contribution * alloc["BTC-USD"]
voo_alloc = contribution * alloc["VOO"]
bil_alloc = contribution * alloc["BIL"]

#setting up API connection to ALPACA paper trading
api = REST("PKUHMBZI6ZJW5OYBO2YGELMTIT", "56tJ3D1DTgFxdVyEg1Ri2gHHLrYdqzvu9a9p6eBVsSjz", base_url="https://paper-api.alpaca.markets")

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


#add in a portfolio sharp ratio and text message
from twilio.rest import Client
import os

# Gather the summary text
summary = (
    f"Allocations placed:\n"
    f"BTC: ${btc_alloc:.2f}\n"
    f"VOO: ${voo_alloc:.2f}\n"
    f"BIL: ${bil_alloc:.2f}\n\n"
    f"Indices:\n"
    f"Fear & Greed: {fng_value}\n"
    f"USD Index Δ: {dol_ind_pct_change:.2f}%\n"
    f"M2 Δ: {m2_pct_change:.2f}%\n"
    f"10Y Δ: {Tres_Yield_pct_change:.2f}%"
)

# Send SMS
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