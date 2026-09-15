# app/ml/anomaly/stl_decomposition.py

import pandas as pd
import numpy as np
from statsmodels.tsa.seasonal import STL
from typing import Optional


def detect_timeseries_anomalies(
    df: pd.DataFrame,
    date_col: str,
    value_col: str,
    period: int = 12,              # 12 = monthly seasonality
    threshold: float = 2.5,        # residual z-score threshold
    freq: Optional[str] = "ME",    # ME=month-end, W=weekly, D=daily
) -> dict:
    """
    STL decomposition-based time-series anomaly detection.

    Splits series into:
      Trend + Seasonality + Residual
    Flags rows where residual z-score > threshold.

    Args:
        df:         DataFrame with date and value columns
        date_col:   Name of date column
        value_col:  Name of numeric value column
        period:     Seasonality period (12=monthly, 7=daily, 52=weekly)
        threshold:  Z-score cutoff for residual anomalies
        freq:       Pandas resample frequency

    Returns:
        {
            "anomaly_count": int,
            "total_points": int,
            "anomalies": [ {date, value, residual, z_score} ],
            "decomposition_summary": {trend_mean, seasonal_strength}
        }
    """

    if df.empty:
        return {"error": "Empty DataFrame"}

    # Prepare time series
    ts = df[[date_col, value_col]].copy()
    ts[date_col] = pd.to_datetime(ts[date_col])
    ts = ts.set_index(date_col).sort_index()
    ts = ts[value_col].resample(freq).sum().fillna(0)

# Replace the "Not enough data points" error block with:
    min_required = period * 2
    if len(ts) < min_required:
        # auto-reduce period to fit available data
        period = max(2, len(ts) // 2)
        if len(ts) < period * 2:
            return {"error": f"Not enough data points. Need at least {period * 2}, got {len(ts)}"}

    # STL decomposition
    stl    = STL(ts, period=period, robust=True)
    result = stl.fit()

    residuals = pd.Series(result.resid, index=ts.index)
    mean_r    = residuals.mean()
    std_r     = residuals.std()

    if std_r == 0:
        return {"error": "Zero variance in residuals — constant series"}

    z_scores     = ((residuals - mean_r) / std_r).abs()
    anomaly_mask = z_scores > threshold

    anomalies = pd.DataFrame({
        "date":     ts.index[anomaly_mask],
        "value":    ts[anomaly_mask].values,
        "residual": residuals[anomaly_mask].round(4).values,
        "z_score":  z_scores[anomaly_mask].round(2).values,
    }).sort_values("z_score", ascending=False)

    # Seasonal strength metric
    var_resid    = np.var(result.resid)
    var_seasonal = np.var(result.seasonal + result.resid)
    seasonal_strength = round(max(0, 1 - var_resid / var_seasonal), 4)

    return {
        "anomaly_count":   len(anomalies),
        "total_points":    len(ts),
        "anomaly_pct":     round(len(anomalies) / len(ts) * 100, 2),
        "anomalies":       anomalies.to_dict(orient="records"),
        "decomposition_summary": {
            "trend_mean":        round(result.trend.mean(), 4),
            "seasonal_strength": seasonal_strength,
        },
    }