import numpy as np
import pandas as pd
from scipy.stats.mstats import winsorize


def winsorize_series(s: pd.Series, limits=(0.01, 0.01)) -> pd.Series:
    valid = s.dropna()
    if len(valid) == 0:
        return s
    clipped = winsorize(valid, limits=limits)
    s_out = s.copy()
    s_out.loc[valid.index] = clipped
    return s_out


def build_prototype_scores(df_metrics: pd.DataFrame) -> pd.DataFrame:
    df = df_metrics.copy()

    # Sector-relative z-scoring configuration (Invert risk metrics so higher Z = safer)
    metrics_config = {
        "volatility_1y": {"z_name": "z_volatility", "invert": True},
        "beta": {"z_name": "z_beta", "invert": True},
        "debt_to_equity": {"z_name": "z_debt_to_equity", "invert": True},
        "dividend_yield": {"z_name": "z_dividend_yield", "invert": False},
        "payout_ratio": {"z_name": "z_payout_ratio", "invert": True},
    }

    for col in metrics_config.keys():
        if col in df.columns:
            df[f"{col}_clean"] = df.groupby("sector")[col].transform(
                winsorize_series
            )

    for col, cfg in metrics_config.items():  # type: ignore
        clean_col = f"{col}_clean"
        z_col = cfg["z_name"]
        if clean_col not in df.columns:
            continue

        sector_mean = df.groupby("sector")[clean_col].transform("mean")
        sector_std = df.groupby("sector")[clean_col].transform("std").replace(0, 1)
        z = (df[clean_col] - sector_mean) / sector_std
        df[z_col] = -z if cfg["invert"] else z

    # Composite Scores
    df["safety_score"] = (
        0.40 * df.get("z_volatility", 0).fillna(0)
        + 0.30 * df.get("z_beta", 0).fillna(0)
        + 0.30 * df.get("z_debt_to_equity", 0).fillna(0)
    )

    df["income_score"] = (
        0.60 * df.get("z_dividend_yield", 0).fillna(0)
        + 0.40 * df.get("z_payout_ratio", 0).fillna(0)
    )

    # Risk Level Categorization (Low, Medium, High ranked within sector)
    df["safety_sector_pct"] = df.groupby("sector")["safety_score"].rank(
        pct=True
    )

    def classify_risk(pct):
        if pd.isna(pct):
            return "Unknown"
        elif pct >= 0.67:
            return "Low"
        elif pct >= 0.33:
            return "Medium"
        else:
            return "High"

    df["risk_level"] = df["safety_sector_pct"].apply(classify_risk)
    return df