# Project Documentation for the Risk/Dividend Team
 
## Files
 
| File | Purpose |
|---|---|
| `fields_and_definitions.csv` | The data dictionary: every field the system uses, where it comes from, what it means, which direction is "better," and what the coverage check found. Everything else (tables, views, scoring, the agent prompt) is built from this file. |
| `WORKSTREAMS.md` | Where each workstream (Scoring/Views, Data, Agent, Integration) should start. |
 
The first three columns (Field Name, Category, Definition) follow the format of the Deep Value team's "Fields and Definitions" sheet from the class folder. The other columns (Source, Table, Unit, Better When, Status, Coverage Notes) make it usable for building the tables.
 
## How we work with it
 
1. The shared Google Sheet is the working copy. The team edits it there.
2. Add your own fields as new rows. Keep one row per field.
3. When the sheet changes meaningfully, export it as CSV (File > Download > CSV) and commit it here, so the repo has a versioned snapshot.
## Status values
 
| Status | Meaning |
|---|---|
| Existing | Already in the database (company, daily_metrics). |
| Professor suggested | Named in the professor's class notes (trailing P/E, forward dividend, yield). Its coverage check result is in Coverage Notes. |
| Proposed | A starter suggestion that the team has not agreed on, or a computed field that has not been tested yet. |
| Verified | Checked in the field-coverage check (49 tickers, 11/5) and usable. The units and rules are in Coverage Notes. |
| Unreliable | Available but gave wrong or inconsistent values in the check. Do not use in scores. |
| Dropped | Decided against. Kept in the list so nobody adds it again without knowing why. |
| Stretch | Nice to have if time allows. |
 
**Coverage Notes** holds the evidence: how often the field came back, which tickers were missing it, the units, and any outliers.
 
## Conventions
 
- **Ratios and yields are stored as fractions** (0.05 means 5%). Yahoo's `dividendYield` and `fiveYearAvgDividendYield` are percents, and `debtToEquity` is percent-style, so divide those by 100 when loading.
- **Use the forward dividend fields** (`dividendRate`, `dividendYield`). The trailing dividend fields are unreliable for some tickers.
- **Winsorize before z-scoring** (1st and 99th percentile, within the sector), as in the Deep Value example, so one bad data point cannot win a ranking.
- **Invert the z-score when a lower raw value is better**, so a higher z always means safer (or more income).
- **Never fill a missing value with 0.** Exclude the stock from that metric and flag it. The reference code in `Risk_code.pdf` defaults missing fundamentals to 0.0, which silently distorts scores.
- **A blank `dividendRate` means non-payer.** Yield and payout columns show 0 for non-payers, and `exDividendDate` shows old dates for former payers, so do not use those to detect payers.
## Open decisions for the team
 
1. Z-scores within each sector, or across the whole S&P 500? Proposed answer: within each sector (see the root README). The coverage check supports it, since utilities, REITs, and financials each break a single market-wide rule.
2. Weights for `safety_composite` and `income_composite`.
3. The cutoffs for Low, Medium, and High, and the pass rule for the safety flags.
4. Which sectors get exceptions to the safety flags (utilities, REITs, banks), and what the exceptions are.
5. The list of fields a stock must have before it can be scored (`flag_data_complete`), and the minimum number of metrics for `partial_data`.
6. Table names (`dividend_metrics`, `risk_metrics`, `scores`), or whether the new fields go into `daily_metrics` instead.
7. Which Gemini model the agent uses (confirm with the professor).
## Checked in the field-coverage check (49 tickers, 11/5)
 
- Yield units: `dividendYield` and `fiveYearAvgDividendYield` are percents, `trailingAnnualDividendYield` is a fraction, and `debtToEquity` is percent-style.
- `trailingAnnualDividendYield` is unreliable (MCD, HD, CAT, NVDA).
- `exDividendDate` is a Unix timestamp in seconds.
- Missing data: about 1 in 4 payers (11 of 41) lacks at least one of beta, debt-to-equity, current ratio, or free cash flow. Financials lack free cash flow data.
- Utilities (DUK, SO, NEE) have negative free cash flow, and the REIT O has a payout ratio of 2.22.
## Still to verify
 
- Which direction is riskier for `overallRisk` (10 is probably the riskiest).
- `volatility_1y` and `max_drawdown_1y`, which need one year of price history.
- Coverage across the full S&P 500. The 49-ticker sample is too small to rank within a sector (3 utilities).
- That `company.Sector` and `sector.sec_name` match exactly once both tables are loaded in `team_risk`.
## Note
 
The agent is an educational tool, not financial advice. The user makes the final decision.
 
Claude finished the response
