# app/api/schemas/anomaly_schemas.py

from pydantic import BaseModel, Field
from typing import Optional

explain: bool = False

FREQ_MAP = {
    "daily":     ("D",  7),    # period=7 (weekly seasonality within daily data)
    "weekly":    ("W",  52),   # period=52 (yearly seasonality within weekly data)
    "monthly":   ("ME", 12),   # period=12 (yearly seasonality within monthly data)
    "quarterly": ("QE", 4),    # period=4
    "yearly":    ("YE", 2),    # period=2 (min viable)
}

class ColumnAnomalyRequest(BaseModel):
    table_name:       str
    numeric_cols:     Optional[list[str]] = None
    contamination:    float = Field(default=0.05, ge=0.01, le=0.5)
    zscore_threshold: float = Field(default=2.0, ge=1.0)
    method:           str   = Field(default="both")  # "isolation", "zscore", "both"


class ColumnAnomalyResponse(BaseModel):
    table_name:          str
    method:              str
    isolation_results:   Optional[dict] = None
    zscore_results:      Optional[dict] = None
    summary:             dict


class TimeseriesAnomalyRequest(BaseModel):
    table_name:  str
    date_col:    str
    value_col:   str
    frequency:   str  = Field(default="monthly", pattern="^(daily|weekly|monthly|quarterly|yearly)$")
    threshold:   float = Field(default=2.5, ge=1.0)
    explain: bool = False                   # ME/W/D


class TimeseriesAnomalyResponse(BaseModel):
    table_name:     str
    date_col:       str
    value_col:      str
    anomaly_count:  int
    total_points:   int
    anomaly_pct:    float
    anomalies:      list
    decomposition_summary: dict
    explanation: Optional[str] = None