# Automated Weekly Investment Bot

Designed an automated dollar-cost-averaging system for Bitcoin that incorporates the same macro and sentiment indicators I would manually evaluate when timing bitcoin investmnents. 

The Bot dynamically rebalances weekly allocations between **Bitcoin (FBTC)**, **S&P 500 (VOO)**, and **Treasury Bills (VBIL)** using macroeconomic indicators and the **Fear & Greed Index**.

This bot runs automatically every **Monday at 9 AM CST** via GitHub Actions, executes simulated trades through **Alpaca’s paper trading API**, sends real-time SMS summaries via **Twilio**, and logs all performance metrics (including Sharpe ratios) to a CSV file for analysis.

---

## Features

- **Dynamic Weekly Allocations**
  - Adjusts BTC, equity, and cash weights using:
    - Fear & Greed Index *(CoinMarketCap API)*
    - U.S. Dollar Index *(DXY via YFinance)*
    - M2 Money Supply *(FRED API)*
    - 10-Year Treasury Yield *(FRED API)*  
  - Adaptive weighting logic that shifts between *risk-on* and *risk-off* regimes

- **Automated Execution**
  - Executes simulated market orders on Alpaca’s **paper-trading** platform
  - Fully scheduled through **GitHub Actions** with no manual input

- **SMS Reporting**
  - Sends a concise weekly allocation and performance summary using **Twilio**

- **Performance Logging**
  - Automatically appends results to `allocation_history.csv`
  - Tracks macro data, portfolio weights, and 60-day Sharpe ratios
  - Commits weekly updates back to the repository

---
# Potential Improvements:
 After observing the bot’s performance over several months, I plan to refine the allocation logic using insights from the historical data logged in the CSV output. This will allow for data-driven backtesting, parameter tuning, and more adaptive portfolio behavior over time.
