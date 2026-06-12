# Hermes Agent central memory ledger

<!--
  HERMES MEMORY LEDGER - CORE SYSTEM INSTRUCTIONS
  ==============================================
  This file is the unified central brain of the Hermes Trading Agent.
  On every startup session, Hermes must call `read_obsidian_note("06_AGENT_MEMORY/MEMORY.md")` or its local configuration path.
  Hermes must read these parameters to initialize current active heuristics, learnings, and parameters.
  
  When writing updates using `write_memory` or custom Obsidian note writes, use the structured sections below.
-->

## 1. System Metadata & Performance Status
- **Last Memory Update**: 2026-06-08 11:22:23
- **Active Operational Phase**: Hypothesis-Validation & Paper Testing
- **Core Active Models**: Hermes-3 (Analysis), qwen2.5-coder-tools (Code/Tools)
- **Primary instrument**: XAUUSD
- **Primary Methodology**: SMC / ICT

---

## 2. Refined SMC Strategic Parameters (Active Rules)
*Enter verified structural rules or modifications here after backtesting.*

| Parameter Category | Core Active Heuristic | Supporting Metric / Origin |
|---|---|---|
| FVG Reversal Mitigation | Minimum 50% Equilibrium retracement required before entry tick. | Backtest Run #BF_19283 (74% win-rate on deep rebalances) |
| Order Block Qualification | OB must generate a clean, displaced Break of Structure (BOS). | Standard Institutional Execution Guideline |
| Session Timing Restriction | Entry window restricted to 07:00-11:00 UTC (London) and 12:30-16:30 UTC (NY). | Volatility optimization to reduce spread drag. |

---

## 3. Core Lessons Identified (Mistakes and Adaptive Fixes)
*Update this section continuously following performance reviews.*

- **Lesson #001 (Spread Drag)**: Avoid trading XAUUSD scalps during Sydney/Tokyo rollover due to widening spreads (often > 65 pips).
  - *Mitigation*: Hard script rules loaded into the risk gateway to auto-reject signal executions occurring between 21:00 and 23:30 UTC.
- **Lesson #002 (News Slip)**: Macro news releases create severe slippage across liquidity sweeps, invalidating precise SL zones.
  - *Mitigation*: Implement a hard ±15-minute freeze around High impact CPI, NFP, and FOMC milestones via the dynamic Forex Factory calendar integration.

---

## 4. Short-Term Memory Registry
*Store immediate anomalies or tasks requiring downstream processing here.*

- [Task] Review backtest reports for the M5 BOS-displacement strategy on Gold.
- [Anomaly] Observed higher-than-average spread behavior on June 5th; verify if broker server configurations changed.
