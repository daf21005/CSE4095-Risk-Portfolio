#!/usr/bin/env python3
"""Field-coverage check for the Risk/Dividend project.

Pulls Yahoo Finance data (via yfinance) for a mixed sample of tickers and
reports, for every field in our data dictionary:
  - how often the field comes back at all,
  - how often it comes back for dividend payers,
  - the min / median / max, so we can see units and outliers,
  - unit checks for the dividend yield fields (percent or fraction?).

This does NOT touch the database. It only reads from Yahoo and writes two CSV
files, so it can run on your laptop or in Cloud Shell.

Usage:
    pip install yfinance
    python3 loaders/coverage_check.py
    python3 loaders/coverage_check.py --outdir docs
    python3 loaders/coverage_check.py --tickers KO,JNJ,TSLA --pause 2

If you see rate-limit errors (429), rerun with a larger --pause.
"""
import argparse
import csv
import math
import os
import statistics
import time

import yfinance as yf

# Yahoo keys that appear in docs/fields_and_definitions.csv
FIELDS = [
    "dividendRate",
    "dividendYield",
    "trailingAnnualDividendYield",
    "trailingAnnualDividendRate",
    "fiveYearAvgDividendYield",
    "payoutRatio",
    "exDividendDate",
    "sharesOutstanding",
    "beta",
    "debtToEquity",
    "currentRatio",
    "freeCashflow",
    "overallRisk",
    "auditRisk",
    "boardRisk",
    "compensationRisk",
    "shareHolderRightsRisk",
    "trailingPE",
    "forwardPE",
]

# Fields where min / median / max would be meaningless (dates, text)
NO_STATS = {"exDividendDate"}

# A mixed sample on purpose: steady payers, banks, REITs, utilities, a very
# high yielder, non-payers, a company with negative equity (BA), and one that
# suspended its dividend (INTC). Edit freely.
DEFAULT_TICKERS = [
    # consumer / staples / retail
    "KO", "PEP", "PG", "MCD", "WMT", "HD", "PM", "MO",
    # energy
    "XOM", "CVX", "COP", "KMI",
    # telecom / tech / health
    "VZ", "T", "IBM", "MSFT", "AAPL", "CSCO", "TXN", "JNJ", "ABBV", "PFE",
    # industrials / materials
    "MMM", "UPS", "CAT", "LIN",
    # utilities
    "DUK", "SO", "NEE",
    # REITs
    "O", "PLD", "AMT", "VICI",
    # banks / financials
    "JPM", "BAC", "WFC", "GS", "BLK",
    # non-payers or tiny payers
    "TSLA", "AMZN", "NFLX", "BRK-B", "UBER", "AMD", "NVDA", "GOOGL",
    # special cases
    "BA", "INTC", "CCL",
]


def is_num(x):
    """True for a real number (not None, not bool, not NaN, not inf)."""
    return (
        isinstance(x, (int, float))
        and not isinstance(x, bool)
        and not math.isnan(x)
        and not math.isinf(x)
    )


def is_present(x):
    return x is not None and x != "" and not (isinstance(x, float) and math.isnan(x))


def fetch_info(symbol, retries=1, pause=2.0):
    """Return (info_dict, error_message). Retries once after a longer pause."""
    err = "unknown error"
    for _ in range(retries + 1):
        try:
            info = yf.Ticker(symbol).info
            # A bad or blocked request often comes back with almost no keys.
            if info and len(info) > 2:
                return info, ""
            err = "empty response"
        except Exception as exc:  # network errors, rate limits, parse errors
            err = f"{type(exc).__name__}: {exc}"
        time.sleep(pause)
    return {}, err


def build_row(symbol, info, err):
    row = {"ticker": symbol, "error": err}
    for field in FIELDS:
        row[field] = info.get(field)
    price = info.get("currentPrice")
    if not is_num(price):
        price = info.get("regularMarketPrice")
    if not is_num(price):
        price = info.get("previousClose")
    row["price"] = price if is_num(price) else None
    row["is_payer"] = int(is_num(info.get("dividendRate")) and info["dividendRate"] > 0)

    # Unit checks: compare Yahoo's yield with dividendRate / price.
    # ratio near 1   -> the yield is a fraction (0.03 = 3%)
    # ratio near 100 -> the yield is a percent  (3.0 = 3%)
    expected = None
    if is_num(row["dividendRate"]) and is_num(row["price"]) and row["price"] > 0:
        expected = row["dividendRate"] / row["price"]
    for field, col in (("dividendYield", "chk_dividendYield_ratio"),
                       ("trailingAnnualDividendYield", "chk_trailingYield_ratio")):
        value = row[field]
        row[col] = round(value / expected, 3) if (expected and is_num(value)) else None
    return row


def summarize(rows):
    """One summary row per field."""
    ok_rows = [r for r in rows if not r["error"]]
    payers = [r for r in ok_rows if r["is_payer"]]
    out = []
    for field in FIELDS:
        present = [r[field] for r in ok_rows if is_present(r[field])]
        present_payers = [r[field] for r in payers if is_present(r[field])]
        nums = [v for v in present if is_num(v)]
        entry = {
            "field": field,
            "tickers_ok": len(ok_rows),
            "n_present": len(present),
            "pct_present": round(100 * len(present) / len(ok_rows), 1) if ok_rows else None,
            "payers": len(payers),
            "pct_present_payers": round(100 * len(present_payers) / len(payers), 1) if payers else None,
            "min": None, "median": None, "max": None,
        }
        if nums and field not in NO_STATS:
            entry["min"] = round(min(nums), 4)
            entry["median"] = round(statistics.median(nums), 4)
            entry["max"] = round(max(nums), 4)
        out.append(entry)
    return out


def interpret_ratio(rows, col):
    values = [r[col] for r in rows if r.get(col) is not None]
    if not values:
        return "no data to check"
    med = statistics.median(values)
    if 0.5 <= med <= 2:
        return f"median ratio {med:.2f}: looks like a FRACTION (0.03 = 3%)"
    if 50 <= med <= 200:
        return f"median ratio {med:.1f}: looks like a PERCENT (3.0 = 3%)"
    return f"median ratio {med:.2f}: unclear, inspect the raw values"


def write_csv(path, rows, columns):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Yahoo field-coverage check")
    parser.add_argument("--tickers", help="comma-separated tickers (default: built-in sample)")
    parser.add_argument("--pause", type=float, default=0.7, help="seconds between tickers")
    parser.add_argument("--outdir", default=".", help="where to write the two CSV files")
    args = parser.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",")] if args.tickers else DEFAULT_TICKERS
    os.makedirs(args.outdir, exist_ok=True)

    rows = []
    for i, symbol in enumerate(tickers, start=1):
        info, err = fetch_info(symbol)
        row = build_row(symbol, info, err)
        rows.append(row)
        status = f"ERROR ({err})" if err else f"payer={bool(row['is_payer'])}"
        print(f"[{i}/{len(tickers)}] {symbol}: {status}")
        time.sleep(args.pause)

    report_cols = ["ticker", "error", "is_payer", "price"] + FIELDS + [
        "chk_dividendYield_ratio", "chk_trailingYield_ratio"]
    summary = summarize(rows)
    summary_cols = ["field", "tickers_ok", "n_present", "pct_present",
                    "payers", "pct_present_payers", "min", "median", "max"]

    write_csv(os.path.join(args.outdir, "coverage_report.csv"), rows, report_cols)
    write_csv(os.path.join(args.outdir, "coverage_summary.csv"), summary, summary_cols)

    print("\n=== COVERAGE SUMMARY ===")
    print(f"{'field':30} {'%present':>9} {'%payers':>8} {'min':>12} {'median':>12} {'max':>14}")
    for s in summary:
        def fmt(v):
            return "-" if v is None else str(v)
        print(f"{s['field']:30} {fmt(s['pct_present']):>9} {fmt(s['pct_present_payers']):>8} "
              f"{fmt(s['min']):>12} {fmt(s['median']):>12} {fmt(s['max']):>14}")

    print("\n=== UNIT CHECKS (payers only) ===")
    payer_rows = [r for r in rows if r["is_payer"]]
    print("dividendYield:              ", interpret_ratio(payer_rows, "chk_dividendYield_ratio"))
    print("trailingAnnualDividendYield:", interpret_ratio(payer_rows, "chk_trailingYield_ratio"))

    failed = [r["ticker"] for r in rows if r["error"]]
    if failed:
        print(f"\nTickers that failed: {', '.join(failed)} (rerun them with --tickers and a larger --pause)")
    print(f"\nWrote coverage_report.csv and coverage_summary.csv to {os.path.abspath(args.outdir)}")


if __name__ == "__main__":
    main()
