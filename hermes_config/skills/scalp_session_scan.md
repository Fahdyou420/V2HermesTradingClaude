# Skill Procedure: Scalp Session Scan (`scalp_session_scan`)

## Overview
This skill defines the high-precision low-timeframe (M1/M5) scanning workflow executed specifically during the highly liquid opening hours of the London and New York financial sessions. This procedure balances aggressive execution targets with protective validation filters.

---

## Step 1: Pre-Scan Safety Filters (Mandatory Checks)
Before performing any structural analysis, you must run four critical safety checks. If ANY check fails, you must immediately halt the scan and issue a `NO_TRADE` decision.

### 1. The Session Time Check
- Validate current UTC execution time:
  - **London Open Window**: `07:00 - 10:00 UTC`
  - **New York Open Window**: `12:30 - 15:30 UTC`
  - *If timezone is outside these bounds, HALT scan.*

### 2. The Broker Spread Check
- Inspect the current spread returned in the `read_market_bars` candle data.
  - **Constraint**: Safe spread must be **<= 50 pips** (5.0 pips / 500 points on Gold).
  - *If spread exceeds 50 pips, HALT scan (high friction).*

### 3. Macroeconomic Event News Check
- Call `get_economic_calendar` to load high-impact calendar events for the day.
  - **Constraint**: Current time must be outside of a **±15-minute** window of any High-impact USD or Gold news publication.
  - *If a news event is imminent or recently released, HALT scan.*

### 4. High Timeframe Bias Check
- Call `read_market_bars` with timeframe `H4` to verify the dominant Order Flow direction.
  - **Constraint**: If H4 shows strong bearish displacement, do not scalp long. If H4 shows strong bullish displacement, do not scalp short.

---

## Step 2: Low Timeframe Structural Analysis
If all filters are passed, analyze close-range M5 bar data to pinpoint liquidity sweeps and imbalances:

1. **Locate Immediate Liquidity Pools**:
   - Find the closest swing high (BSL) and swing low (SSL) on the M5 timeframe.
2. **Detect Imbalance Mitigation (FVG)**:
   - Identify unfilled M5 Fair Value Gaps located within **20 pips** of the current price.
3. **Verify Displacement and Reversals**:
   - Confirm if price has recently swept an active liquidity pool and generated an immediate M1/M5 Change of Character (CHoCH) with a strong displacement candle body closure.

---

## Step 3: Execution Decision and Output Generation

### Option A: Complete Scalp TradeSignal
If a high-probability setup is fully formed, compute exact entry and risk levels and output them strictly enclosed inside a ```signal block:

```signal
{
  "signal_id": "SCALP_20260608_01",
  "instrument": "XAUUSD",
  "direction": "buy",
  "entry_price": 2345.50,
  "sl": 2341.00,
  "tp": 2355.00,
  "lots": 1.50,
  "timeframe": "M5",
  "strategy_id": "strat_m5_scalp_004",
  "setup_type": "M5_Liquidity_Sweep_Reversal",
  "session": "London",
  "mode": "paper",
  "r_ratio": 2.11,
  "confidence": "high",
  "agent_notes": "Buy scalp triggered after SSL sweep at 2342.00 followed by M5 displacement and FVG rebalance."
}
```

### Option B: NO_TRADE Order
If any defensive filter fails or structural confirmation is absent, issue a readable `NO_TRADE` update explaining the precise reasoning:

`DECISION: NO_TRADE`

**Reasoning**:
- **Safety Filter Breach**: Scan blocked because current time is 11:15 UTC, placing it outside the highly liquid London and New York opening sessions.
- **Spread Drag**: Current broker spread is 65 pips, violating the mandatory 50-pip execution threshold.
- **Micro News Event**: Scraped Forex Factory feed shows high-impact US CPI publication at 12:30 UTC. Scan halted within the 15-minute protective boundary.
- **Trend Discrepancy**: Price is trading inside an intraday premium territory against a dominant H4 bearish displacement, presenting unfavorable risk multiples.
