-- sql/02_create_new_tables.sql
-- New tables for the Risk/Dividend project in team_risk.
--
-- Run AFTER 01_create_tables.sql. Safe to rerun: every statement uses IF NOT EXISTS.
-- IF NOT EXISTS does not change a table that already exists. While these tables are
-- still empty you can DROP and recreate them. Once data is loaded, use ALTER TABLE.
--
-- Source of truth for the columns: docs/fields_and_definitions.csv and the columns of
-- data/pilot_metrics.csv. Conventions (see docs/README.md):
--   * ratios and yields are stored as FRACTIONS (0.05 = 5%)
--   * a missing value is NULL, never 0
--   * one row per ticker per as_of_date, so each refresh adds a day instead of
--     overwriting the last one
--
-- Deliberately NOT in these tables:
--   * sector                          lives in company.Sector (scores keeps a copy of the
--                                     sector it was scored in; see below)
--   * beta, trailing_pe, forward_pe   stay in the existing daily_metrics table
--   * trailing_annual_dividend_*      unreliable (Dropped in the dictionary)
--
-- Open design question for the team: should scores be a table the scoring script
-- writes (as here) or a view over these tables? Winsorizing and z-scores are awkward
-- in SQL, so this draft uses a table, and a view can sit on top for the agent.

USE team_risk;

-- ---------------------------------------------------------------------------
-- Dividend fields
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dividend_metrics (
  ticker                       VARCHAR(20)   NOT NULL,
  as_of_date                   DATE          NOT NULL,
  dividend_rate                DECIMAL(12,4),   -- USD per share per year; NULL for non-payers
  dividend_yield               DECIMAL(10,6),   -- fraction; Yahoo gives a percent, divide by 100
  five_year_avg_dividend_yield DECIMAL(10,6),   -- fraction; NULL for new payers
  yield_vs_5y_avg              DECIMAL(10,4),   -- dividend_yield / five_year_avg_dividend_yield
  payout_ratio                 DECIMAL(12,4),   -- fraction; above 1 means paying out more than it earns
  ex_dividend_date             DATE,            -- Yahoo gives a Unix timestamp; former payers keep old dates
  shares_outstanding           BIGINT,
  fcf_dividend_coverage        DECIMAL(14,4),   -- free cash flow / (dividend_rate * shares); can be negative
  dividend_years_raised        INT,             -- stretch goal, from dividend history
  loaded_at                    TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (ticker, as_of_date),
  INDEX idx_dividend_metrics_date (as_of_date)
);

-- ---------------------------------------------------------------------------
-- Risk fields
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS risk_metrics (
  ticker                  VARCHAR(20)   NOT NULL,
  as_of_date              DATE          NOT NULL,
  volatility_1y           DECIMAL(10,6),   -- annualized, fraction; NULL if under 200 trading days
  max_drawdown_1y         DECIMAL(10,6),   -- negative fraction (-0.25 = a 25% fall)
  debt_to_equity          DECIMAL(12,4),   -- plain ratio; Yahoo gives a percent, divide by 100
  current_ratio           DECIMAL(10,4),
  free_cashflow           BIGINT,          -- USD; negative is allowed
  governance_overall_risk TINYINT,         -- Yahoo score 1 to 10; direction still to be confirmed
  price_days              SMALLINT,        -- trading days of prices behind volatility and drawdown
  loaded_at               TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (ticker, as_of_date),
  INDEX idx_risk_metrics_date (as_of_date)
);

-- ---------------------------------------------------------------------------
-- Scores (written by the scoring script, read by the agent)
-- ---------------------------------------------------------------------------
-- The flag_* columns are NULL when a flag cannot be evaluated (for example free
-- cash flow is missing). NULL means "unknown", which is different from 0 ("failed").
CREATE TABLE IF NOT EXISTS scores (
  ticker                   VARCHAR(20)   NOT NULL,
  as_of_date               DATE          NOT NULL,
  sector                   VARCHAR(50),     -- the sector this stock was ranked within
  flag_pays_dividend       TINYINT(1),
  flag_payout_ok           TINYINT(1),
  flag_fcf_positive        TINYINT(1),
  flag_fcf_covers_dividend TINYINT(1),
  flag_data_complete       TINYINT(1),
  safety_flags_passed      TINYINT,
  z_volatility             DECIMAL(8,4),    -- within-sector z-scores, inverted so higher = safer
  z_beta                   DECIMAL(8,4),
  z_debt_to_equity         DECIMAL(8,4),
  z_dividend_yield         DECIMAL(8,4),    -- not inverted: higher = more income
  z_fcf_coverage           DECIMAL(8,4),
  safety_composite         DECIMAL(8,4),
  income_composite         DECIMAL(8,4),
  risk_level               ENUM('Low','Medium','High','Unknown') NOT NULL DEFAULT 'Unknown',
  sector_rank              INT,             -- 1 = safest in its sector
  partial_data             TINYINT(1)    NOT NULL DEFAULT 0,
  metrics_used             TINYINT,         -- how many of the scored metrics this stock had
  score_version            VARCHAR(20),     -- which weights and cutoffs produced this row
  loaded_at                TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (ticker, as_of_date),
  INDEX idx_scores_date (as_of_date),
  INDEX idx_scores_screen (as_of_date, sector, risk_level)
);

-- ---------------------------------------------------------------------------
-- Optional, left out on purpose: foreign keys to company(Ticker). They would force
-- the reference tables to be loaded first and reject any ticker not in company.
-- Same choice as the base tables. To add later:
--   ALTER TABLE dividend_metrics ADD CONSTRAINT fk_dividend_company
--     FOREIGN KEY (ticker) REFERENCES company (Ticker);
-- ---------------------------------------------------------------------------