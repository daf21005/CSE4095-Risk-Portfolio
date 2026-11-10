#!/usr/bin/env python3
"""Build the pilot dataset for the Risk/Dividend scorer.

This connects three things:
  1. Yahoo Finance "info" fields (coverage_check.py showed which ones are usable),
  2. one year of daily prices, run through price_metrics.compute_price_risk_metrics
     to get volatility_1y and max_drawdown_1y,
  3. the dictionary's column names and units (docs/fields_and_definitions.csv).

The output is one row per ticker, written to pilot_metrics.csv. Column names match
the dictionary, and ratios are stored as fractions (0.05 = 5%). Missing values stay
empty. Nothing is ever filled with 0.

Usage, from the repo root:
    pip install yfinance pandas numpy requests lxml
    python3 loaders/build_pilot_dataset.py --limit 20       # quick test run
    python3 loaders/build_pilot_dataset.py                  # full S&P 500
    python3 loaders/build_pilot_dataset.py --resume         # continue after an interruption
    python3 loaders/build_pilot_dataset.py --tickers KO,JNJ,TSLA
    python3 loaders/build_pilot_dataset.py --tickers-file my_tickers.csv

A full run takes a while (two Yahoo calls per ticker plus a pause). If you see
rate-limit errors, rerun with --resume and a larger --pause.
"""
import argparse
import io
import math
import os
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yfinance as yf

# Dylan's function. This works because the script lives in loaders/ next to it.
from price_metrics import compute_price_risk_metrics

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
CHECKPOINT_EVERY = 25

COLUMNS = [
    "ticker", "sector", "price", "flag_pays_dividend",
    "dividend_rate", "dividend_yield", "five_year_avg_dividend_yield", "payout_ratio",
    "ex_dividend_date", "shares_outstanding", "free_cashflow", "fcf_dividend_coverage",
    "beta", "debt_to_equity", "current_ratio", "governance_overall_risk",
    "trailing_pe", "forward_pe",
    "volatility_1y", "max_drawdown_1y", "price_days", "error",
]

# the metrics the scorer uses. Used only for the report at the end.
SCORED = ["volatility_1y", "beta", "debt_to_equity", "dividend_yield", "fcf_dividend_coverage"]


# small helpers
# returns a float, or NaN if the value isn’t a real number
def num(x):
    """float(x) if x is a real number, otherwise NaN. Never 0."""
    if isinstance(x, bool) or not isinstance(x, (int, float, np.integer, np.floating)):
        return np.nan
    x = float(x)
    return x if math.isfinite(x) else np.nan

# uppercases a ticker and swaps . for -
def clean_symbol(s):
    """Yahoo writes share classes with a dash (BRK-B). Wikipedia uses a dot (BRK.B)."""
    return str(s).strip().upper().replace(".", "-")

# turns Yahoo’s Unix timestamp (seconds since 1970) into YYYY-MM-DD
def epoch_to_date(ts):
    """Yahoo's exDividendDate is a Unix timestamp in seconds. Returns 'YYYY-MM-DD' or ''."""
    ts = num(ts)
    if np.isnan(ts):
        return ""
    try:
        return datetime.fromtimestamp(ts, timezone.utc).date().isoformat()
    except (OverflowError, OSError, ValueError):
        return ""

# where the tickers come from
def load_sp500_from_wikipedia():
    import requests  # installed together with yfinance

    resp = requests.get(
        WIKI_URL,
        headers={"User-Agent": "Mozilla/5.0 (CSE4095 class project)"},
        timeout=30,
    )
    resp.raise_for_status()
    table = pd.read_html(io.StringIO(resp.text))[0]  # needs lxml
    return [clean_symbol(s) for s in table["Symbol"]]


# loads tickers from a CSV file
def load_tickers_file(path):
    df = pd.read_csv(path)
    for name in df.columns:
        if str(name).strip().lower() in ("symbol", "ticker"):
            return [clean_symbol(s) for s in df[name].dropna()]
    return [clean_symbol(s) for s in df.iloc[:, 0].dropna()]

# fetching from Yahoo
def fetch_info(symbol, retries=1, pause=2.0):
    """Return (info_dict, error_message). Retries once after a longer pause."""
    err = "unknown error"
    for _ in range(retries + 1):
        try:
            info = yf.Ticker(symbol).info
            if info and len(info) > 2:  # a blocked or bad request returns almost no keys
                return info, ""
            err = "info: empty response"
        except Exception as exc:
            err = f"info: {type(exc).__name__}: {exc}"
        time.sleep(pause)
    return {}, err

def fetch_prices(symbol, retries=1, pause=2.0):
    """One year of daily prices as a DataFrame: ticker, date, close, adj_close."""
    err = "unknown error"
    for _ in range(retries + 1):
        try:
            hist = yf.Ticker(symbol).history(period="1y", auto_adjust=False)
            if hist is not None and not hist.empty and "Close" in hist.columns:
                adj = hist["Adj Close"] if "Adj Close" in hist.columns else hist["Close"]
                out = pd.DataFrame({
                    "ticker": symbol,
                    "date": [d.date() for d in hist.index],
                    "close": hist["Close"].values,
                    "adj_close": adj.values,
                })
                return out.dropna(subset=["close"]), ""
            err = "prices: empty history"
        except Exception as exc:
            err = f"prices: {type(exc).__name__}: {exc}"
        time.sleep(pause)
    return pd.DataFrame(columns=["ticker", "date", "close", "adj_close"]), err

def price_risk(prices, min_days):
    """volatility_1y and max_drawdown_1y from Dylan's function.

    His function accepts any history of 2 or more days. We require at least
    min_days, so a recent listing is left empty instead of getting a number
    computed from a few weeks of data.
    """
    n = len(prices)
    if n < min_days:
        return np.nan, np.nan, n
    res = compute_price_risk_metrics(prices[["ticker", "date", "close"]]).iloc[0]
    return num(res["volatility_1y"]), num(res["max_drawdown_1y"]), n

# turning Yahoo's answers into dictionary columns
def build_row(symbol, info, vol, mdd, price_days, error):
    rate = num(info.get("dividendRate"))
    shares = num(info.get("sharesOutstanding"))
    fcf = num(info.get("freeCashflow"))

    price = np.nan
    for key in ("currentPrice", "regularMarketPrice", "previousClose"):
        price = num(info.get(key))
        if not np.isnan(price):
            break

    # A blank dividendRate means non-payer (the coverage check showed this).
    pays = int((not np.isnan(rate)) and rate > 0)

    coverage = np.nan
    if pays and (not np.isnan(shares)) and shares > 0 and not np.isnan(fcf):
        coverage = fcf / (rate * shares)  # negative when free cash flow is negative

    return {
        "ticker": symbol,
        "sector": info.get("sector") or "",
        "price": price,
        "flag_pays_dividend": pays,
        "dividend_rate": rate,
        # Yahoo gives these three as percents (3.0 means 3%), so divide by 100.
        "dividend_yield": num(info.get("dividendYield")) / 100,
        "five_year_avg_dividend_yield": num(info.get("fiveYearAvgDividendYield")) / 100,
        "payout_ratio": num(info.get("payoutRatio")),  # already a fraction
        "ex_dividend_date": epoch_to_date(info.get("exDividendDate")),
        "shares_outstanding": shares,
        "free_cashflow": fcf,
        "fcf_dividend_coverage": coverage,
        "beta": num(info.get("beta")),
        "debt_to_equity": num(info.get("debtToEquity")) / 100,  # percent-style
        "current_ratio": num(info.get("currentRatio")),
        "governance_overall_risk": num(info.get("overallRisk")),
        "trailing_pe": num(info.get("trailingPE")),
        "forward_pe": num(info.get("forwardPE")),
        "volatility_1y": vol,
        "max_drawdown_1y": mdd,
        "price_days": price_days,
        "error": error,
    }


# ---------------------------------------------------------------------------
# saving and reporting
# ---------------------------------------------------------------------------
def save(rows, path):
    pd.DataFrame(rows, columns=COLUMNS).to_csv(path, index=False)


def print_summary(df):
    ok = df[df["error"] == ""]
    payers = ok[ok["flag_pays_dividend"] == 1]
    print(f"\n=== SUMMARY ===")
    print(f"{len(df)} tickers: {len(ok)} fetched cleanly, {len(df) - len(ok)} with errors, "
          f"{len(payers)} pay a dividend")

    print(f"\n{'field':30} {'%present':>9} {'%payers':>8}")
    for col in COLUMNS[2:-2]:
        if col in ("flag_pays_dividend", "ex_dividend_date"):
            continue
        pct_all = 100 * ok[col].notna().mean() if len(ok) else float("nan")
        pct_pay = 100 * payers[col].notna().mean() if len(payers) else float("nan")
        print(f"{col:30} {pct_all:9.1f} {pct_pay:8.1f}")

    if len(payers):
        incomplete = int(payers[SCORED].isna().any(axis=1).sum())
        print(f"\nPayers missing at least one scored metric ({', '.join(SCORED)}): "
              f"{incomplete} of {len(payers)}")

    print(f"\n{'sector':28} {'stocks':>7} {'payers':>7}")
    by_sector = ok[ok["sector"] != ""].groupby("sector")["flag_pays_dividend"].agg(["size", "sum"])
    for sector, row in by_sector.sort_values("size", ascending=False).iterrows():
        small = "   <- small, z-scores unreliable" if row["sum"] < 10 else ""
        print(f"{sector:28} {int(row['size']):7d} {int(row['sum']):7d}{small}")
    no_sector = int((ok["sector"] == "").sum())
    if no_sector:
        print(f"{'(no sector from Yahoo)':28} {no_sector:7d}")

    failed = df[df["error"] != ""]["ticker"].tolist()
    if failed:
        print(f"\nTickers with errors: {', '.join(failed)}")
        print("Rerun with --resume to retry them.")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(description="Build pilot_metrics.csv for the scorer")
    parser.add_argument("--tickers", help="comma-separated tickers")
    parser.add_argument("--tickers-file", help="CSV with a Symbol or ticker column")
    parser.add_argument("--limit", type=int, help="only process the first N tickers (for testing)")
    parser.add_argument("--pause", type=float, default=0.7, help="seconds between tickers")
    parser.add_argument("--min-days", type=int, default=200,
                        help="minimum trading days of prices needed to compute volatility and drawdown")
    parser.add_argument("--outdir", default="data", help="where to write the CSV files")
    parser.add_argument("--resume", action="store_true", help="continue from the partial file")
    args = parser.parse_args(argv)

    if args.tickers:
        tickers = [clean_symbol(t) for t in args.tickers.split(",")]
    elif args.tickers_file:
        tickers = load_tickers_file(args.tickers_file)
    else:
        try:
            tickers = load_sp500_from_wikipedia()
        except ImportError:
            sys.exit("Reading the Wikipedia table needs lxml. Run: pip install lxml")
        except Exception as exc:
            sys.exit(f"Could not download the S&P 500 list ({exc}). "
                     "Use --tickers-file with a CSV of symbols instead.")
    tickers = list(dict.fromkeys(tickers))  # remove duplicates, keep order
    if args.limit:
        tickers = tickers[: args.limit]

    os.makedirs(args.outdir, exist_ok=True)
    final_path = os.path.join(args.outdir, "pilot_metrics.csv")
    partial_path = os.path.join(args.outdir, "pilot_metrics.partial.csv")

    rows = []
    if args.resume and os.path.exists(partial_path):
        previous = pd.read_csv(partial_path, keep_default_na=True)
        previous["error"] = previous["error"].fillna("")
        previous["sector"] = previous["sector"].fillna("")
        previous["ex_dividend_date"] = previous["ex_dividend_date"].fillna("")
        rows = [r for r in previous.to_dict("records") if r["error"] == ""]  # retry the failures
        print(f"Resuming: {len(rows)} tickers already done.")
    done = {r["ticker"] for r in rows}
    todo = [t for t in tickers if t not in done]
    print(f"{len(todo)} tickers to fetch ({len(tickers)} total).")

    try:
        for i, symbol in enumerate(todo, start=1):
            info, info_err = fetch_info(symbol)
            prices, px_err = fetch_prices(symbol)
            vol, mdd, days = price_risk(prices, args.min_days)
            error = "; ".join(e for e in (info_err, px_err) if e)
            rows.append(build_row(symbol, info, vol, mdd, days, error))

            status = f"ERROR ({error})" if error else f"{days} price days"
            print(f"[{i}/{len(todo)}] {symbol}: {status}", flush=True)

            if i % CHECKPOINT_EVERY == 0:
                save(rows, partial_path)
            time.sleep(args.pause)
    except KeyboardInterrupt:
        save(rows, partial_path)
        print(f"\nInterrupted. Progress saved to {partial_path}. Rerun with --resume to continue.")
        return 1

    save(rows, final_path)
    if os.path.exists(partial_path):
        os.remove(partial_path)
    print(f"\nWrote {final_path}")
    print_summary(pd.DataFrame(rows, columns=COLUMNS))
    return 0

if __name__ == "__main__":
    sys.exit(main())
