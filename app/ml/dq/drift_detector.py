# app/ml/dq/drift_detector.py

import pandas as pd
import numpy as np
from scipy import stats
from typing import Optional


def detect_drift(
    df_reference: pd.DataFrame,    # baseline / historical window
    df_current: pd.DataFrame,      # current / latest window
    numeric_cols: Optional[list[str]] = None,
    pvalue_threshold: float = 0.05,  # below this = drift detected
) -> dict:
    """
    KS-Test based drift detection between two DataFrames.

    Compares column distributions using Kolmogorov-Smirnov test.
    p-value < threshold → distribution has significantly changed → drift.

    Args:
        df_reference:     Historical/baseline data window
        df_current:       Current data window
        numeric_cols:     Columns to test (auto-detects if None)
        pvalue_threshold: Significance level (default 0.05)

    Returns:
        {
            "drift_detected": bool,
            "drifted_columns": [str],
            "column_results": {
                "col_name": {
                    "ks_statistic": float,
                    "p_value": float,
                    "drift": bool,
                    "ref_mean": float,
                    "cur_mean": float,
                    "mean_shift_pct": float
                }
            }
        }
    """

    if df_reference.empty or df_current.empty:
        return {"error": "One or both DataFrames are empty"}

    if numeric_cols is None:
        ref_num = set(df_reference.select_dtypes(include=[np.number]).columns)
        cur_num = set(df_current.select_dtypes(include=[np.number]).columns)
        numeric_cols = list(ref_num & cur_num)   # only common columns

    if not numeric_cols:
        return {"error": "No common numeric columns found"}

    column_results = {}
    drifted_columns = []

    for col in numeric_cols:
        ref_series = df_reference[col].dropna()
        cur_series = df_current[col].dropna()

        if len(ref_series) < 5 or len(cur_series) < 5:
            continue   # not enough data for KS test

        ks_stat, p_value = stats.ks_2samp(ref_series, cur_series)
        drift = p_value < pvalue_threshold

        ref_mean = ref_series.mean()
        cur_mean = cur_series.mean()
        mean_shift_pct = round(
            abs(cur_mean - ref_mean) / ref_mean * 100, 2
        ) if ref_mean != 0 else None

        if drift:
            drifted_columns.append(col)

        column_results[col] = {
            "ks_statistic":    round(ks_stat, 4),
            "p_value":         round(p_value, 4),
            "drift":           drift,
            "ref_mean":        round(ref_mean, 4),
            "cur_mean":        round(cur_mean, 4),
            "mean_shift_pct":  mean_shift_pct,
        }

    return {
        "drift_detected":  len(drifted_columns) > 0,
        "drifted_columns": drifted_columns,
        "column_results":  column_results,
    }