# Skill Procedure: Write Market Study Note (`write_market_study`)

## Overview
This skill outlines how the Hermes agent converts real-time market data observations into a standardized, visually polished, and readable Obsidian Note under `01_MARKET_STUDIES/`.

---

## Step 1: Note Setup and Frontmatter Rules
Every Market Study note must begin with a complete YAML frontmatter header to facilitate tag categorization, date sorting, and retrieval matching.

```yaml
---
tags: [market-study, gold, m15, london-open]
instrument: XAUUSD
timeframe: M15
date: YYYY-MM-DD
session: London / NewYork / Asian
bias: Bullish / Bearish / Consolidated
---
```

---

## Step 2: Note Structural Sections (Mandatory)
The note body must be structured with the following exact Header structures:

### # SMC Market Structure Study - XAUUSD [{TIMEFRAME}] - {DATE}

### ## 1. Executive Bias Summary
A brief high-level narrative describing current market sentiment. Identify whether Higher Timeframe (H4 or Daily) order flow supports or contradicts Lower Timeframe (M15) setups. Specify the Active Daily Bias.

### ## 2. Core SMC Structural Geometry Analysis
Detail the exact coordinates of identified structural markers:
- **Trend Coordinates**: Highs, Lows, and sequence of Higher Highs or Lower Lows.
- **Fair Value Gaps (FVGs)**: Include specific 3-candle imbalance boundaries (Upper, Lower, Consequent Encroachment) and status (Mitigated or Unfilled).
- **Order Blocks (OBs)**: High and Low coordinates of the raw block and mitigation state.
- **Structural Shifts**: List exact zones of recent BOS or CHoCH body candles closures.

### ## 3. Liquidity Pool Heatmaps
Document key pools where stop orders are highly dense:
- **Buy-side Liquidity (BSL)**: Location of Equal Highs (EQH), Daily Highs, or H4 Swing Highs.
- **Sell-side Liquidity (SSL)**: Location of Equal Lows (EQL), Daily Lows, or H4 Swing Lows.

### ## 4. Dynamic Key Support and Resistance Levels
Outline immediate horizontal price zones that are likely to interact with order flow. Indicate which levels represent institutional premium or discount boundaries.

### ## 5. Strategy Hypotheses and Trading Plan
Formulate tactical execution plans. Describe exact setups: e.g., "Wait for price to sweep SSL under 2342.50, then trigger a buy entry upon immediate M1 M5 CHoCH with target back into the premium M15 FVG at 2355.00."

### ## 6. Conclusion and Risk Disclaimers
A concise, professional closing statement summarizing probability factors. Remind users of active risk guidelines (1% maximum risk allocation per trade).

---

## Step 3: Vault Note Writing Deployment
1. Construct the complete note payload using string concatenation. Ensure no markdown formatting is broken.
2. Formulate the absolute target file write path:
   `01_MARKET_STUDIES/{instrument}/{timeframe}/study_{date}_{session}.md`
3. Dispatch the note to the Obsidian database using the `write_obsidian_note` tool.
