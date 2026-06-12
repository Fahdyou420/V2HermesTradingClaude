# Skill Procedure: Review Paper Trades (`review_paper_trades`)

## Overview
This skill implements the continuous performance audit that the Hermes agent executes to review forward-testing paper trades. This step ensures active strategies remain mathematically viable before proceeding towards live deployment.

---

## Step 1: Active Trade Status and Metrics Retrieval
1. Invoke the `get_paper_trade_status` tool to extract:
   - Dynamic running metrics (Balance, Equity, Current Drawdown).
   - Indices of active open positions.
2. Read historical transaction files from `03_TRADE_JOURNAL/` or use directory scanning to load historic executed paper position data.

---

## Step 2: Strategy Performance Compilation
Group all analyzed historical and active database trade rows by their specific `strategy_id` (e.g., `strat_fvg_reversal_002`). Compute the following values for each unique strategy card:

### Mathematical Performance Metrics:
- **Total Trades**: Total number of trades executed by this strategy.
- **Win Rate**: `Total Win Trades / Total Trades`
- **Total R-multiple Profit**: Net sum of R-multiples gained.
- **Average Profit Factor**: `Gross Profits / Gross Losses`
- **Max Strategy Drawdown**: Largest peak-to-trough balance drop specifically attributed to this strategy.

---

## Step 3: Pattern Extraction and System Audit
Study the descriptive variables of successful trades vs. losing trades to identify patterns:
1. **Time of day / Session**: Did the strategy fail exclusively during low-liquidity zones or macroeconomic news events?
2. **Direction Analysis**: Does the strategy maintain a structural bias (e.g., executing buys cleanly but showing a high loss rate on sell zones)?
3. **Spread Degradation**: Check average execution spreads. Are some trades losing solely due to high broker commissions/spread slippage?

---

## Step 4: Upgrading/Downgrading Strategy Confidence Stages
Based on the performance metrics, update the target `status` of each Strategy Note in the vault:

- **LIVE CANDIDATE PROMOTION**: If a strategy compiles a minimum of **30 forward test trades**, maintains a **win-rate >= 0.52**, shows an **expectancy >= 0.4R**, and is within protective drawdown boundaries, update its status from `paper` to `live_candidate`.
- **DEMOTE/REJECT**: If the win-rate drops below **48%** or the strategy-specific drawdown exceeds **8%**, demote its status back to `failed_validation` and halt automated signal generation.

---

## Step 5: Committing Weekly Journal Review Note
Use the `write_obsidian_note` tool to write the weekly review card into the vault:

### Path:
`03_TRADE_JOURNAL/weekly_reviews/review_{year}_w{week_number}.md`

### Note Structure Template:
```markdown
# Weekly Paper Trade Evaluation - Week {WEEK_NUM} ({YEAR})

## 1. General Portfolio Health
- **Final Account Equity**: $102,450.50 (+2.45% weekly return)
- **Active Overall Portfolio Drawdown**: 1.25%
- **Active Open Positions**: 1 (XAUUSD Buy, strat_fvg_reversal_002)

## 2. Strategy Metrics Scoreboard
| Strategy ID | Total Trades | Win Rate | Profit Factor | Net R-multiple | Validation Status |
|---|---|---|---|---|---|
| strat_fvg_002 | 14 | 57.14% | 1.94 | +6.2 R | Active (Paper) |
| strat_ob_001 | 8 | 37.50% | 0.81 | -1.5 R | Under Observation |

## 3. Structural Learnings and Modifications
We noticed three consecutive losses for `strat_ob_001` occurring during the New York high-impact news window.
- **Urgent Action**: Enforce the news-filter block rule for this strategy directly inside execution parameter configurations.
```
