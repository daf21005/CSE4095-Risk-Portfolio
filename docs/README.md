# Project Documentation for the Risk/Dividend Team

## Files
| File | Purpose |
|---|---|
| `fields_and_definitions.csv` | The data dictionary: every field the system uses, where it comes from, what it means, and which direction is "better." Everything else (tables, views, scoring, the agent prompt) is built from this file. |

The first three columns (Field Name, Category, Definition) follow the format of the Deep Value team's "Fields and Definitions" sheet from the class folder. The extra columns (Source, Table, Unit, Better When, Status) make it usable for building the tables.

## How we work with it
 
1. Import `fields_and_definitions.csv` into a shared Google Sheet (File > Import). The sheet is the working copy, so the team edits it there.
2. Add your own fields as new rows. Keep one row per field.
3. When the sheet changes meaningfully, export it as CSV and commit it here, so the repo has a versioned snapshot.


## Status values
 
| Status | Meaning |
|---|---|
| Existing | Already in the database (company, daily_metrics). |
| Professor suggested | Named in the professor's class notes (trailing P/E, forward dividend, yield). |
| Proposed | A starter suggestion that the team has not agreed on. Change or delete it. |
| Stretch | Nice to have if time allows. |
 
This is a first draft. Nothing marked Proposed is a decision yet.

## Open decisions for the team
 
1. Z-scores across the whole S&P 500, or within each sector?
2. Weights for `safety_composite` and `income_composite`.
3. The cutoffs for Low, Medium, and High, and the pass rule for the safety flags.
4. Table names (`dividend_metrics`, `risk_metrics`, `scores`), or whether the new fields go into `daily_metrics` instead.
5. Which Gemini model the agent uses (confirm with the professor).
## To verify with the field-coverage check (first task in `loaders/`)
 
- Each Yahoo key exists and returns data for most tickers, including non-dividend payers.
- The units of each percent-style field (`dividendYield`, `fiveYearAvgDividendYield`, `debtToEquity`).
- The format of `exDividendDate`.
- Which direction is riskier for `overallRisk`.

## Notes
 
- The agent is an educational tool, not financial advice. The user makes the final decision.
- The csv file can also be found in the shared Google Drive folder for a cleaner view