import numpy as np
import pandas as pd


def build_prototype_scores(df_metrics: pd.DataFrame) -> pd.DataFrame:
    """Builds safety_composite, income_composite, sector_rank, and risk_level labels.

    Handles missing metrics gracefully, caps z-scores at +/- 3.0, and flags
    partial data.
    """
    df = df_metrics.copy()

    # 1. Fundamental Safety & Income Flags
    if "dividend_yield" in df.columns:
        df["flag_pays_dividend"] = (df["dividend_yield"] > 0).astype(int)
    else:
        df["flag_pays_dividend"] = 0

    if "payout_ratio" in df.columns:
        df["flag_payout_ok"] = (
            (df["payout_ratio"] >= 0) & (df["payout_ratio"] <= 1.0)
        ).astype(int)
    else:
        df["flag_payout_ok"] = 0

    if "free_cashflow" in df.columns:
        df["flag_fcf_positive"] = (df["free_cashflow"] > 0).astype(int)
    else:
        df["flag_fcf_positive"] = 0

    df["safety_flags_passed"] = (
        df["flag_pays_dividend"]
        + df["flag_payout_ok"]
        + df["flag_fcf_positive"]
    )

    # 2. Metrics Mapping Configuration
    safety_metrics = {
        "volatility_1y": {
            "z_name": "z_volatility",
            "weight": 0.40,
            "invert": True,
        },
        "beta": {"z_name": "z_beta", "weight": 0.30, "invert": True},
        "debt_to_equity": {
            "z_name": "z_debt_to_equity",
            "weight": 0.30,
            "invert": True,
        },
    }

    income_metrics = {
        "dividend_yield": {
            "z_name": "z_dividend_yield",
            "weight": 0.50,
            "invert": False,
        },
        "fcf_dividend_coverage": {
            "z_name": "z_fcf_coverage",
            "weight": 0.50,
            "invert": False,
        },
    }

    all_metrics = {**safety_metrics, **income_metrics}

    # 3. Sector-Relative Z-Scores with Capping at +/- 3.0
    active_safety_cols, active_safety_weights = [], []
    active_income_cols, active_income_weights = [], []

    for col, cfg in all_metrics.items():
        if col not in df.columns or df[col].dropna().empty:
            continue

        z_col = cfg["z_name"]

        # Calculate sector-relative z-score skipping NA
        sector_mean = df.groupby("sector")[col].transform(
            lambda x: x.mean(skipna=True)
        )
        sector_std = (
            df.groupby("sector")[col]
            .transform(lambda x: x.std(skipna=True))
            .replace(0, np.nan)
        )

        z_raw = (df[col] - sector_mean) / sector_std
        if cfg["invert"]:
            z_raw = -z_raw

        # Cap Z-scores at +/- 3.0
        df[z_col] = z_raw.clip(lower=-3.0, upper=3.0)

        if col in safety_metrics:
            active_safety_cols.append(z_col)
            active_safety_weights.append(cfg["weight"])
        elif col in income_metrics:
            active_income_cols.append(z_col)
            active_income_weights.append(cfg["weight"])

    # 4. Compute Weighted Composites (skipna)
    def calc_weighted_composite(row, z_cols, w_arr):
        vals = row[z_cols].values
        valid_mask = ~np.isnan(vals)
        if not np.any(valid_mask):
            return np.nan
        return np.sum(vals[valid_mask] * w_arr[valid_mask]) / np.sum(
            w_arr[valid_mask]
        )

    if active_safety_cols:
        expected_safety_count = len(
            [m for m in safety_metrics if m in df.columns]
        )
        available_safety_count = df[active_safety_cols].notna().sum(axis=1)
        weights_array = np.array(active_safety_weights)

        df["safety_composite"] = df.apply(
            lambda r: calc_weighted_composite(
                r, active_safety_cols, weights_array
            ),
            axis=1,
        )
    else:
        df["safety_composite"] = np.nan
        available_safety_count = 0
        expected_safety_count = len(safety_metrics)

    if active_income_cols:
        income_weights_array = np.array(active_income_weights)
        df["income_composite"] = df.apply(
            lambda r: calc_weighted_composite(
                r, active_income_cols, income_weights_array
            ),
            axis=1,
        )
    else:
        df["income_composite"] = np.nan

    # 5. Partial Data Flag & Risk Level Categorization
    df["partial_data"] = (available_safety_count < expected_safety_count).astype(
        int
    )

    df["sector_rank"] = df.groupby("sector")["safety_composite"].rank(
        ascending=False, method="min", na_option="bottom"
    )
    df["safety_sector_pct"] = df.groupby("sector")["safety_composite"].rank(
        pct=True, na_option="keep"
    )

    def assign_risk_level(row):
        if pd.isna(row["safety_composite"]):
            return "Unknown"
        pct = row["safety_sector_pct"]
        if pd.isna(pct):
            return "Unknown"
        elif pct >= 0.67:
            return "Low"
        elif pct >= 0.33:
            return "Medium"
        else:
            return "High"

    df["risk_level"] = df.apply(assign_risk_level, axis=1)

    return df