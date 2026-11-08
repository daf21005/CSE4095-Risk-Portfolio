import numpy as np
import pandas as pd


def compute_price_risk_metrics(df_daily_prices: pd.DataFrame) -> pd.DataFrame:
    """Computes volatility_1y and max_drawdown_1y from historical daily close prices.

    Expected input DataFrame columns: ['ticker', 'date', 'close']
    """
    df = df_daily_prices.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["ticker", "date"])

    results = []
    for ticker, group in df.groupby("ticker"):
        # Take the last 252 trading days (approx. 1 calendar year)
        g_1y = group.tail(252).copy()

        if len(g_1y) < 2:
            results.append(
                {
                    "ticker": ticker,
                    "volatility_1y": np.nan,
                    "max_drawdown_1y": np.nan,
                }
            )
            continue

        # Daily returns
        g_1y["ret"] = g_1y["close"].pct_change()

        # Annualized Volatility
        volatility_1y = g_1y["ret"].std() * np.sqrt(252)

        # Max Drawdown (Peak to Trough)
        cummax = g_1y["close"].cummax()
        drawdown = (g_1y["close"] - cummax) / cummax
        max_drawdown_1y = drawdown.min()

        results.append(
            {
                "ticker": ticker,
                "volatility_1y": volatility_1y,
                "max_drawdown_1y": max_drawdown_1y,
            }
        )

    return pd.DataFrame(results)