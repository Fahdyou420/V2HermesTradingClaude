# Skill Procedure: Generate Strategy Hypothesis (`generate_strategy`)

## Overview
This skill outlines how the Hermes agent translates raw qualitative and quantitative market structure observations into a formal, testable strategy configuration. Every strategy is initialized under the `hypothesis` stage of our staged trust framework.

---

## Step 1: Synthesis of Market Studies
Before writing a strategy hypothesis, evaluate the findings from your most recent `analyse_market_structure` studies:
1. Is there a clean trend direction (Bullish or Bearish)?
2. Where are the unfilled inefficiencies (FVGs) and untouched institutional blocks (OBs)?
3. What is the location of the nearest key liquidity pools (BSL/SSL)?

---

## Step 2: Formulating Entry, SL, and TP Logic
You must define your entry triggers using strict SMC boundaries:

### 1. The Trigger Level
- Determine the entry zone. For example: "Trace the 50% equilibrium level (Consequent Encroachment) of the unfilled H1 FVG or the mean threshold of the M15 Bullish OB."

### 2. The Stop Loss (SL) Boundary
- Position the SL strictly outside the protective structure:
  - For **Buys**: At least 5-10 pips below the swing low of the qualifying Order Block or FVG anchor candle.
  - For **Sells**: At least 5-10 pips above the swing high of the qualifying Order Block or FVG anchor candle.

### 3. The Take Profit (TP) Goal (Minimum R:R)
- Target key liquidity pools.
- **Minimum Risk-to-Reward Ratio (R:R)**: Every strategy MUST maintain a minimum theoretical R:R of **2.0R**. If target liquidity pools do not project a 2.0R distance from the entry and SL coordinates, the trade hypothesis is invalidated and discarded.

### 4. Time and Session Filter
- Set strict operational session intervals:
  - London Session hours: `07:00 - 11:00 UTC`
  - New York Session hours: `12:30 - 16:30 UTC`

---

## Step 3: Drafting the Strategy Config JSON
Format your strategy config using a standardized programmatic JSON structure. This schema is digestible by the `run_backtest` simulator and execution containers:

```json
{
  "strategy_id": "strat_fvg_reversal_002",
  "name": "Gold M15 FVG Mitigation Reversal",
  "instrument": "XAUUSD",
  "timeframe": "M15",
  "status": "hypothesis",
  "rules": {
    "entry_condition": "fvg_touch",
    "fvg_min_size_pips": 15.0,
    "equilibrium_retracement": 0.50,
    "ob_mitigation": true
  },
  "risk_mgmt": {
    "max_risk_percent": 1.0,
    "target_rr_ratio": 2.5,
    "trailing_stop_activation_r": 1.5
  },
  "filters": {
    "sessions_allowed": ["London", "NewYork"],
    "max_raw_spread_pips": 5.0,
    "min_atr_m15": 8.0
  }
}
```

---

## Step 4: Vault Commitment (Strategy Card Initiation)
Use the `write_obsidian_note` tool to commit the strategy card to the Obsidian Vault.

### Target Path Structure:
`02_STRATEGIES/XAUUSD/strat_{strategy_id}.md`

### Strategy Card Template with Frontmatter:
```markdown
---
id: strat_fvg_reversal_002
name: Gold M15 FVG Mitigation Reversal
status: hypothesis
date_created: 2026-06-08
instrument: XAUUSD
timeframe: M15
author: Hermes
---

# Strategy Card: Gold M15 FVG Mitigation Reversal

## 1. Executive Concept
The strategy aims to trade the market correction back into unfilled M15 Fair Value Gaps (FVG) that align with dominant H4 Higher Timeframe trends on Gold.

## 2. Dynamic Trading Rules Configuration
- **Entry Trigger**: Price mitigation of the 50% Consequent Encroachment level of an M15 FVG.
- **Stop Loss Rule**: 5 pips below the lowest wick of the FVG anchor candle.
- **Take Profit Rule**: Target the opposing major BSL or SSL level (Must project >= 2.0R).

## 3. Backtest Simulation Parameters (JSON Configuration)
```json
{
  "strategy_id": "strat_fvg_reversal_002",
  "name": "Gold M15 FVG Mitigation Reversal",
  "instrument": "XAUUSD",
  "timeframe": "M15",
  "status": "hypothesis",
  "rules": {
    "entry_condition": "fvg_touch",
    "fvg_min_size_pips": 15.0,
    "equilibrium_retracement": 0.50,
    "ob_mitigation": true
  },
  "risk_mgmt": {
    "max_risk_percent": 1.0,
    "target_rr_ratio": 2.5,
    "trailing_stop_activation_r": 1.5
  },
  "filters": {
    "sessions_allowed": ["London", "NewYork"],
    "max_raw_spread_pips": 5.0,
    "min_atr_m15": 8.0
  }
}
```

## 4. Operational Validation Log (Phase Progression)
- [x] **Hypothesis Created**: 2026-06-08 (System initialization)
- [ ] **Backtest Commited**: Pending simulation
- [ ] **Paper Testing Log**: Active testing pipeline
```
