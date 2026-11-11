# Workstream starter guide

*Draft for the Risk/Dividend team. Read `README.md` (section "How decisions are made") and `docs/fields_and_definitions.csv` first. Everything here is a proposal, so change it if the team agrees on something better.*

## Shared rules

- **Only the Data owner writes to the base tables in `team_risk`.** Everyone else reads. Experiment in your own copies, named `sbx_<initials>_<table>`.
- **Credentials come from environment variables, never from code, chat, or GitHub.** That includes the database password and the Gemini key.
- **Units:** store ratios and yields as fractions (0.05 = 5%). Yahoo's `dividendYield` and `fiveYearAvgDividendYield` are percents, and `debtToEquity` is percent-style, so divide those by 100.
- **Missing data is never filled with 0.** Leave it empty and flag it.
- **Each person works in their own folder** (`loaders/`, `scoring/`, `agent/`, `app/`). Pull before you push.
- **The dictionary is slightly out of date.** These coverage-check findings override it until it is updated: the trailing dividend yield and rate are unreliable (use the forward fields), `exDividendDate` is a Unix timestamp in seconds, a blank `dividendRate` means non-payer, and scoring is within each stock's sector.

## What the coverage check showed (49 tickers)

Plan around these facts:

- About 1 in 4 payers (11 of 41) is missing at least one of beta, debt-to-equity, current ratio, or free cash flow. Financials lack free cash flow data.
- Utilities (DUK, SO, NEE) have negative free cash flow. The REIT O has a payout ratio of 2.22. A single market-wide rule would misjudge both groups.
- The sample is too small to rank within a sector (3 utilities). Real scoring needs the full S&P 500.

---

## 1. Scoring / Views

**Goal:** turn the fields into a safety score, an income score, and a Low/Medium/High label for each stock, ranked within its sector.

**You do not need the database to start.** Use `coverage_report.csv` as sample data. It has dividend, payout, beta, debt, current ratio, and free cash flow for 49 tickers.

**Start here**

1. **Add what the sample lacks.**
   - `sector`: add `"sector"` to the `FIELDS` list in `loaders/coverage_check.py` and rerun it.
   - `volatility_1y` and `max_drawdown_1y`: compute them from one year of price history. The formulas are in the dictionary.
   - For the real thing, ask the Data owner to run the coverage check on the full S&P 500. The sample is too small to test within-sector ranking.
2. **Prototype the score in pandas** (`scoring/prototype_scores.py`), following the six steps in the README: cap outliers within each sector, z-score within each sector, flip the sign where lower is better, combine with placeholder equal weights, then label by cutoffs. A starting skeleton, tested on toy data:

   ```python
   def winsorize(s, lo=0.01, hi=0.99):
       return s.clip(s.quantile(lo), s.quantile(hi))

   def zscore(s):
       std = s.std(ddof=0)
       if not std or std != std:      # no spread: this metric cannot separate stocks
           return s * 0
       return (s - s.mean()) / std

   # minus sign: lower debt is better, so flip it so higher z = safer
   w = df.groupby("sector")["debt_to_equity"].transform(winsorize)
   df["z_debt_to_equity"] = -w.groupby(df["sector"]).transform(zscore)

   zcols = ["z_debt_to_equity", "z_beta", "z_volatility"]
   df["safety_composite"] = df[zcols].mean(axis=1, skipna=True)     # uses the metrics available
   df["partial_data"] = df[zcols].isna().any(axis=1).astype(int)
   df["sector_rank"] = df.groupby("sector")["safety_composite"].rank(ascending=False, method="min")
   ```
3. **Handle missing data the way the README says:** score on the metrics a stock has, set `partial_data = 1`, and never fill raw data with 0. Note that a stock scored on one metric is less comparable to one scored on three. Propose a minimum number of metrics.
4. **Sanity-check the results.** Sort each sector. Do steady payers (KO, PG, JNJ) land in Low or Medium? Which stocks have partial data? Write down anything surprising.
5. **Propose, with evidence, the open decisions:** weights, Low/Medium/High cutoffs, sector exceptions for the guardrails (utilities, REITs, banks), and the minimum number of metrics. The team decides.
6. **Later, once `team_risk` is loaded, turn it into views** (`sql/03_views.sql`). A suggested layering:
   - `vw_metrics_clean`: unit conversions and NULL handling
   - `vw_sector_z`: z-scores within sector, using `AVG(...) OVER (PARTITION BY sector)` and `STDDEV_SAMP(...) OVER (PARTITION BY sector)`
   - `vw_scores`: composites, flags, `partial_data`, `sector_rank`, and `risk_level`

   MySQL has no simple percentile function, so capping outliers is awkward in SQL. Two options: cap the z-score at plus or minus 3 inside the view, or compute the heavy metrics in Python and store them in a table. Decide as a team.

**Done when:** a script produces a score table from the sample CSV, and a short note records the formula and open questions.

**Hand off:** the column list of the final `scores` view. The Agent owner needs it to define the tools.

---

## 2. Data

**Goal:** fill `team_risk` with the S&P 500 reference data, price history, and the new dividend and risk fields.

**Start here**

1. **Design the new tables (`sql/02_create_new_tables.sql`).** Likely `dividend_metrics` and `risk_metrics`, keyed on `ticker` and `as_of_date` like `daily_metrics`. The columns come from the dictionary fields that are usable. Agree on them with the Scoring owner before creating anything.
2. **Run the coverage check on the full S&P 500** and share `coverage_report.csv`. This is the Scoring owner's sample data until the database is loaded. It takes several minutes. If you see rate-limit errors, rerun with `--pause 2`.
3. **Load the reference tables** `company`, `sector`, and `security`. David has working scripts from Assignment 3 (`sp500.py`, `sp500_to_sql.py`, `sector_load.py`, `openfigi_sp500.py`). They point at the old database and hardcode the password. Adapt them to read credentials from environment variables, point them at `team_risk`, and use the column name `sec_percent` in the `sector` loader.
4. **Backfill one year of price history** into `daily_price`, including `adj_close`. Use `history(period="1y", auto_adjust=False)` per ticker with a pause between calls. Both OpenFIGI and Yahoo rate-limited us earlier.
5. **Write the dividend and risk loader**, adapting the professor's "Financial Daily Loads" pattern. Apply the unit rules, convert `exDividendDate` from seconds to a date, and store NULL for missing values.

**Done when:** the reference tables and price history are loaded, and a note records the units and NULL rules.

**Hand off:** loaded tables, plus the full-universe coverage report as soon as it exists.

---

## 3. Agent

**Goal:** an agent that takes a user's risk level (and optionally a sector or ticker), calls tools, and explains the result using only database numbers.

**You do not need the scores to start.** Build against a sample CSV and swap in the real data later.

**Start here**

1. **Set up the Gemini key safely.** The professor shared it. Put it in an environment variable (`GEMINI_API_KEY`) or a `.env` file that `.gitignore` covers. Never put it in code, chat, or the repo.
2. **Hello world:** use the `google-genai` library to send one prompt and print the reply. The class example uses `gemini-2.5-flash`. Confirm the model with the professor.
3. **One tool, sample data.** Write a plain Python function such as `get_stock_profile(ticker)` that reads from `coverage_report.csv`. Give it to Gemini through function calling and watch it call your function. Add a retry for 503 errors, as in the professor's example.
4. **Write the tool spec** (`agent/TOOLS.md`) before building more. Proposed tools:
   - `get_stock_profile(ticker)`
   - `screen_stocks(risk_level, sector=None, min_yield=None, limit=5)`
   - `sector_summary(sector)`

   List each tool's inputs and the output columns, and agree on the columns with the Scoring owner.
5. **Write the agent's rules** (the system prompt): numbers come only from tool results, every label is shown with the raw numbers and the sector rank behind it, partial data is flagged, a sector-relative label means "safest among its peers," and the user makes the final decision. It is an educational tool, not financial advice.
6. **Optional, in the style of the Deep Value example:** send the top few scored stocks to Gemini as an auditor and print its critique.

**Done when:** a script lets you ask one question and see Gemini call a tool and answer from the result.

**Hand off:** the tool spec, and the keys and model name the Integration owner needs.

---

## 4. Integration / Lead

**Goal:** make the pieces fit, and have something demonstrable by the showcase on December 2nd.

**Start here**

1. **Own the contract:** the dictionary edits, the new table columns, and the `scores` view columns. These are the interfaces between workstreams.
2. **Repo hygiene:** confirm `.gitignore` covers `.env`, `venv/`, and `__pycache__/`, commit the base SQL and loaders, and add teammates to the private repo.
3. **Share the Drive folder** with the team (it is currently private) and set up the group chat. Run a short Monday check-in where everyone posts what they did, what's next, and any blocker.
4. **Decide the demo format with the professor:** a live agent demo, a web page on Cloud Run, or both. Find out whether CSE teams follow the business pitch format.
5. **After the MCP demo,** confirm whether the agent should connect through MCP. If so, swap the tool implementations and keep the function signatures the same.
6. **Plan the end-to-end test and the demo script.** Keep a cached copy of the data so a live demo does not depend on Yahoo being reachable.

**Done when:** a question typed in at the interface returns an answer drawn from the database.

---

## Timeline (proposed)

| By | What |
|---|---|
| Wed 11/11 | Each workstream's "start here" steps done. Data: tables designed and reference data loaded. Scoring: prototype on the sample. Agent: one working tool. |
| Wed 11/18 | First end-to-end run, even if rough. Scoring views over the loaded data, tools reading from them. |
| Wed 11/25 | Feature freeze (a short week). Tuning and testing only. |
| Mon 11/30 | Full rehearsal. |
| Wed 12/2 | Showcase, 6 to 8 pm. |