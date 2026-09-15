# app/ml/anomaly/isolation_forest.py

import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
from typing import Optional


def detect_outliers(
    df: pd.DataFrame,
    numeric_cols: Optional[list[str]] = None,
    contamination: float = 0.05,    # assume 5% of data is anomalous
    random_state: int = 42,
) -> dict:
    """
    Run IsolationForest on numeric columns of a DataFrame.
    Returns anomaly rows with scores.

    Args:
        df:              Input DataFrame
        numeric_cols:    Columns to analyze (auto-detects if None)
        contamination:   Expected proportion of anomalies (0.01–0.5)
        random_state:    Reproducibility seed

    Returns:
        {
            "anomaly_count": int,
            "total_rows": int,
            "anomaly_pct": float,
            "anomalies": [ { row data + anomaly_score } ],
            "columns_analyzed": [str]
        }
    """

    if df.empty:
        return {"error": "Empty DataFrame passed to IsolationForest"}

    # Auto-detect numeric columns if not specified
    if numeric_cols is None:
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    if not numeric_cols:
        return {"error": "No numeric columns found for anomaly detection"}

    # Drop rows with all NaN in selected columns
    df_clean = df[numeric_cols].dropna(how="all").fillna(df[numeric_cols].median())

    # Fit IsolationForest
    clf = IsolationForest(
        contamination=contamination,
        random_state=random_state,
        n_estimators=100,
    )
    predictions = clf.fit_predict(df_clean)       # -1 = anomaly, 1 = normal
    scores      = clf.decision_function(df_clean) # lower = more anomalous

    # Attach results back to original df
    result_df = df.loc[df_clean.index].copy()
    result_df["_anomaly_flag"]  = predictions
    result_df["_anomaly_score"] = scores.round(4)

    anomalies = result_df[result_df["_anomaly_flag"] == -1].copy()
    anomalies = anomalies.sort_values("_anomaly_score")  # worst first

    return {
        "anomaly_count":     len(anomalies),
        "total_rows":        len(df_clean),
        "anomaly_pct":       round(len(anomalies) / len(df_clean) * 100, 2),
        "columns_analyzed":  numeric_cols,
        "anomalies":         anomalies.drop(columns=["_anomaly_flag"])
                                      .to_dict(orient="records"),
    }