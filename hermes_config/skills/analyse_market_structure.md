# Skill Procedure: Analyse Market Structure (`analyse_market_structure`)

## Overview
This skill implements the precise step-by-step quantitative and qualitative procedure the Hermes agent must follow to parse candle data into Smart Money Concepts (SMC) and Inner Circle Trader (ICT) market geometry. 

---

## Step 1: Candle Retrieval Pipeline
1. Determine the target instrument (Default: **XAUUSD**) and Timeframe (e.g., M15).
2. Call the `read_market_bars` tool with parameters:
   - `instrument`: `"XAUUSD"`
   - `tf`: Selected timeframe (e.g., `"M15"`, `"H1"`, or `"H4"`)
   - `n`: **300** (always request at least 300 bars for structural context)

---

## Step 2: SMC Structural Mathematical Engine
Scan the retrieved 300-candle dataset to compute and identify the following:

### 1. Swing Highs & Lows (Fractal Structural Points)
- **Swing High**: An index `i` has a swing high if its High is strictly greater than the preceding two candles and succeeding two candles:
  `High[i] > High[i-1] && High[i] > High[i-2] && High[i] > High[i+1] && High[i] > High[i+2]`
- **Swing Low**: An index `i` has a swing low if its Low is strictly less than the preceding two candles and succeeding two candles:
  `Low[i] < Low[i-1] && Low[i] < Low[i-2] && Low[i] < Low[i+1] && Low[i] < Low[i+2]`

### 2. Market Trend and Order Flow
- Evaluate the series of recent Swing Highs (SH) and Swing Lows (SL).
- **Bullish Trend**: Series of Higher Highs (HH) and Higher Lows (HL).
- **Bearish Trend**: Series of Lower Highs (LH) and Lower Lows (LL).

### 3. Fair Value Gaps (FVG) / Imbalances
Locate all 3-candle imbalance segments:
- **Bullish FVG (Buying Imbalance)**: Occurs when Candle 1 High is strictly lower than Candle 3 Low:
  `Low[i] > High[i-2]` (for candles sequenced 1: `i-2`, 2: `i-1`, 3: `i`)
  - Range: `High[i-2]` to `Low[i]` is the FVG zone. Mark as **Unfilled** if current price has not retraced into this range.
- **Bearish FVG (Selling Imbalance)**: Occurs when Candle 1 Low is strictly higher than Candle 3 High:
  `High[i] < Low[i-2]` (for candles sequenced 1: `i-2`, 2: `i-1`, 3: `i`)
  - Range: `High[i]` to `Low[i-2]` is the FVG zone.

### 4. Active Order Blocks (OB)
- **Bullish OB**: Find the last bearish candle body right before a bullish impulse that led to a Break of Structure (BOS) or Change of Character (CHoCH).
- **Bearish OB**: Find the last bullish candle body right before a bearish impulse that led to a BOS or CHoCH.
- *Active Filter*: Only log OBs that have not been touched (mitigated) by subsequent candles.

### 5. Break of Structure (BOS) & Change of Character (CHoCH)
- **BOS (Break of Structure)**: When price pushes past and closes body candles beyond a previous Swing High/Low in the direction of the dominant trend.
- **CHoCH (Change of Character)**: When price breaks and closes body candles beyond the most recent structural Swing High/Low in the *opposite* direction of the dominant trend, signaling an early reversal of Order Flow.

### 6. Buy-side and Sell-side Liquidity (BSL / SSL)
- **Buy-side Liquidity (BSL)**: Clusters of equal highs or major swing highs where buy stop orders reside.
- **Sell-side Liquidity (SSL)**: Clusters of equal lows or major swing lows where sell stop orders reside.

---

## Step 3: Vault Commitment (Obsidian Market Study)
After running calculations, you must commit the structured report to the Vault using the `write_obsidian_note` tool.

### Target Path Structure:
`01_MARKET_STUDIES/XAUUSD/{timeframe}/market_study_{date}_{session}.md`

### Note Template with Frontmatter:
```markdown
---
tags: [market-study, gold, smc, structural-scan]
instrument: XAUUSD
timeframe: M15
date: 2026-06-08
session: London_Open
bias: Bullish
---

# SMC Market Structure Study - XAUUSD [M15]

## 1. Executive Bias Summary
- **Primary Market Context**: Bullish Order Flow following a clean Higher Timeframe (H4) displacement.
- **Dynamic Session Bias**: London Session Bullish Reversals.

## 2. Structural Geometry Coordinates
| Feature | Type | High Coordinate | Low Coordinate | Mitigation Status |
|---|---|---|---|---|
| FVG_01 | Bullish | 2348.50 | 2345.20 | Unfilled |
| OB_01 | Bullish | 2341.00 | 2338.50 | Untouched |
| BOS_High | Breakout | 2351.20 | - | Closed Above |

## 3. Liquidity Heatmaps
- **Buy-side Liquidity (BSL)**: Major double-high pool clustered above 2358.50.
- **Sell-side Liquidity (SSL)**: Sell-stops resting below the swing low at 2336.00.

## 4. Analytical Reasoning
We have witnessed a clean M15 CHoCH to the upside after price swept buy-side order flow below 2340.00. We anticipate direct mitigation of FVG_01 before continued higher expansion towards BSL.
```
