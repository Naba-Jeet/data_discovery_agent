# app/ml/anomaly/zscore.py

import pandas as pd
import numpy as np
from typing import Optional


def detect_zscore_outliers(
    df: pd.DataFrame,
    numeric_cols: Optional[list[str]] = None,
    threshold: float = 2.0,
) -> dict:

    if df.empty:
        return {"error": "Empty DataFrame"}

    if numeric_cols is None:
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    column_results = {}

    for col in numeric_cols:
        series = df[col].dropna()
        median = series.median()
        mad    = (series - median).abs().median()

        if mad == 0:
            continue

        modified_z   = (0.6745 * (series - median) / mad).abs()
        outlier_mask = modified_z > threshold

        outliers = df.loc[outlier_mask.index[outlier_mask], col].reset_index()
        outliers.columns = ["row_index", "value"]
        outliers["z_score"] = modified_z[outlier_mask].round(2).values

        column_results[col] = {
            "median":        round(median, 4),
            "mad":           round(mad, 4),
            "outlier_count": int(outlier_mask.sum()),
            "outliers":      outliers.to_dict(orient="records"),
        }

    return {"column_results": column_results}