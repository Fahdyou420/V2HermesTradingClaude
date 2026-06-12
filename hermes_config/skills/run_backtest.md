# Skill Procedure: Run Backtest Simulation (`run_backtest`)

## Overview
This skill outlines how the Hermes agent reads strategy designs from the vault, invokes the historical simulator, interprets performance statistics mathematically, and transitions strategies along the trust pipeline from `hypothesis` to `backtested`.

---

## Step 1: Strategy Retrieval and Parsing
1. Identify the strategy file path within the Obsidian Vault (e.g., `02_STRATEGIES/XAUUSD/strat_fvg_reversal_002.md`).
2. Call `read_obsidian_note` to extract the note contents.
3. Surgical Search: Scan the file for the embedded `JSON` configuration block containing the simulation rules.

---

## Step 2: Running the Simulator
1. Call the `run_backtest` tool.
2. Under the `strategy_config` parameter, pass the JSON object extracted from the strategy file.
3. Wait for the simulation process to complete and capture the output statistics dictionary.

---

## Step 3: Mathematical Metric Interpretation
To transition a strategy to the next confidence tier or flag it as rejected, evaluate the results using these hard constraints:

```
IF (win_rate >= 0.52) AND (expectancy >= 0.40) AND (max_drawdown <= 10.0%) AND (total_trades >= 50) {
    STRATEGY_STATUS = "backtested"
    VALIDATION_DECISION = "PASS"
} ELSE {
    STRATEGY_STATUS = "hypothesis_failed"
    VALIDATION_DECISION = "REJECTED"
}
```

### Definitions:
- **Win Rate**: `Total Winning Trades / Total Trades`
- **Expectancy (R-value)**: Average R-multiple gain per trade across the entire dataset.
- **Max Drawdown**: Maximum peak-to-trough drop in simulated equity.
- **Minimum Trades**: At least **50 completed trades** are required to establish statistical significance.

---

## Step 4: Updating the Strategy Card and Logging
Upon parsing the decision, update the strategy note:

1. **Modify Status**: Use `write_obsidian_note` to overwrite target file frontmatter:
   - If Passed: Update status from `hypothesis` to `backtested`.
   - If Failed: Update status from `hypothesis` to `failed_validation`.
2. **Inject Results Segment**: Append the backtest performance summary block directly into the card.

---

## Step 5: Write Simulation Report Card
Create a separate backtest audit report using `write_obsidian_note` at:
`04_BACKTEST_REPORTS/XAUUSD/report_{strategy_id}_{date}.md`

### Simulation Report Template:
```markdown
# Backtest Simulation Report: strat_fvg_reversal_002

## 1. System Metadata
- **Strategy ID**: strat_fvg_reversal_002
- **Simulation Time**: 2026-06-08 11:23:43
- **Scanned Database Period**: 2024-01-01 to 2026-05-31
- **Primary Model**: SMC FVG Consequent Encroachment

## 2. Core Simulation Outcome
- **Validation Decision**: **PASS / ACTIVE PROTOCOL**

| Evaluated Metric | Checked Value | Minimum Threshold | Status |
|---|---|---|---|
| Total Trades | 124 | 50 | PASS |
| Win Rate | 54.83% | 52.0% | PASS |
| Expectancy | 0.51 R | 0.40 R | PASS |
| Max Drawdown | 6.84% | 10.0% | PASS |
| Profit Factor | 1.84 | - | PASS |

## 3. Performance Interpretation
The strategy has successfully survived historical validation of M15 Gold datasets. High-displacement FVG mitigations show sustained statistical advantages, particularly within London sessions.

## 4. Next Phase Progression
We authorize the immediate progression of this strategy card into the **Paper Testing** stage of the Staged Trust Framework.
```
