# CSE4095 Risk/Dividend Portfolio
 
This is a project for the course CSE 4095 where we are tasked to create a portfolio based on risk/dividend.
 
The team includes:
- David F.
- Dylan M.
- Diva E.
- Leonardo W.
Don't forget to create an .env file to hold the Gemini API Key and create a virtual environment:
```bash
python3 -m venv venv
```
 
___To activate the virtual environment:___
```bash
source venv/bin/activate
```
 
## Project documents
 
| Path | What it is |
|---|---|
| `docs/fields_and_definitions.csv` | Data dictionary: every field we use, where it comes from, its unit, and which direction is "better." |
| `docs/README.md` | How to use the dictionary, conventions, and open decisions. |
| `sql/01_create_tables.sql` | Creates the base tables in the shared `team_risk` database. |
| `loaders/coverage_check.py` | Checks which Yahoo Finance fields are actually available, and in what units. |
 
## How decisions are made
 
*Draft. Anything marked TBD is an open team decision.*
 
The question we are answering: **what is our risk-based portfolio, and how do the numbers score it?**
 
```
Yahoo Finance data -> tables in team_risk -> scores (views / pandas) -> agent tools -> Gemini agent -> user decides
```
 
### 1. Scores are computed ahead of time, within each sector
 
Every stock is compared only with the other stocks in its own sector. This happens for all sectors, whether or not anyone asks.
 
1. Collect the metrics listed in the data dictionary. Safety metrics: volatility, beta, debt-to-equity. Income metrics: forward dividend yield, free cash flow coverage of the dividend.
2. Cap outliers inside each sector (winsorize at the 1st and 99th percentile) so one bad data point cannot win a ranking.
3. Convert each metric to a z-score within its sector.
4. Flip the z-score where a lower raw value is better, so a higher z always means safer (or more income).
5. Combine the z-scores with weights into `safety_composite` and `income_composite` (weights TBD).
6. Assign `risk_level` (Low, Medium, or High) from cutoffs on `safety_composite` (cutoffs TBD).
**Why by sector.** The coverage check on 49 tickers showed that one market-wide rule would misjudge whole groups:
 
- The utilities in the sample (DUK, SO, NEE) have negative free cash flow, because they spend heavily on infrastructure.
- The REIT Realty Income (O) has a payout ratio of 2.22, because REITs report low accounting earnings.
- The banks and financials (JPM, BAC, WFC, GS, BLK) have no free cash flow data.
### 2. Guardrails
 
Safety flags catch problems that a relative score can hide:
 
- pays a dividend (`dividendRate` above 0; a missing value means non-payer)
- payout ratio within a sensible range
- free cash flow positive, and covering the dividend
- data complete for every field the score needs
A sector-relative label means "safest among its peers," not "safe." Proposed rule: a stock is not labeled Low risk if its dividend is not covered by cash flow, except in sectors where that measure does not apply (utilities, banks, REITs). The exceptions are TBD.
 
### 3. What the user provides
 
| Input | Required? |
|---|---|
| Risk tolerance: Low, Medium, or High | Yes |
| Goal (this project focuses on dividend income) | Defaults to income |
| Sector | Optional filter |
| A specific ticker | Optional, to ask about one stock |
 
| The user says | The agent does |
|---|---|
| "Medium risk, income, utilities only" | Finds the best income stocks in Utilities with a Medium label and explains why |
| "Medium risk, income" (no sector) | Searches every sector and shows the best from each |
| "Is KO a safe dividend stock?" | Finds KO's sector, shows its score against its peers, and shows its actual numbers |
 
### 4. What the agent does
 
- Python tools query the stored scores. Gemini explains the result.
- Every number comes from the database. The model never supplies figures of its own.
- Each label is shown next to the real numbers behind it (beta, payout ratio, and so on) and the stock's rank within its sector.
- If data is partial, the agent says so.
- This is an educational tool, not financial advice. The user makes the final decision.
### 5. Missing data
 
A missing value is never filled with 0. A stock is scored on the metrics it does have and flagged as partial. The minimum number of metrics required is TBD.
 
### Open decisions
 
1. Weights for `safety_composite` and `income_composite`.
2. Cutoffs for Low, Medium, and High (for example, the top third of each sector is Low).
3. Which sectors get exceptions to the guardrails, and what the exceptions are.
4. One scoring recipe for all sectors, or custom metrics for Financials, Utilities, and Real Estate.
5. The minimum number of available metrics before a stock can be scored.
6. Which Gemini model the agent uses (confirm with the professor).