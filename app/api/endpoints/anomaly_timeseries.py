# app/api/endpoints/anomaly_timeseries.py

import json
import pandas as pd
from fastapi import APIRouter, HTTPException
from api.schemas.anomaly_schemas import TimeseriesAnomalyRequest, TimeseriesAnomalyResponse
from ml.anomaly import detect_timeseries_anomalies
from mcp_client.client import run_query

router = APIRouter(prefix="/anomaly", tags=["Anomaly"])



@router.post("/timeseries", response_model=TimeseriesAnomalyResponse)
async def timeseries_anomaly(request: TimeseriesAnomalyRequest):

    sql = f"SELECT {request.date_col}, {request.value_col} FROM {request.table_name} LIMIT 50000"
    try:
        raw    = await run_query(sql, limit=50000)
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        rows   = parsed if isinstance(parsed, list) else parsed.get("rows", [])
        if not rows:
            raise HTTPException(status_code=404, detail=f"No data for {request.table_name}")
        df = pd.DataFrame(rows)
        df = pd.DataFrame(rows)

# Cast value column to numeric — DB may return strings for decimal types
        df[request.value_col] = pd.to_numeric(df[request.value_col], errors="coerce")
        df = df.dropna(subset=[request.value_col])  # drop unconvertible rows
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB fetch failed: {str(e)}")

# resolve freq + period from human-readable frequency
    from api.schemas.anomaly_schemas import FREQ_MAP

    freq_key = request.frequency.lower()
    pandas_freq, period = FREQ_MAP[freq_key]

    result = detect_timeseries_anomalies(
        df,
        date_col=request.date_col,
        value_col=request.value_col,
        period=period,
        threshold=request.threshold,
        freq=pandas_freq,
    )

    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])

    explanation = None
    if request.explain and result.get("anomaly_count", 0) > 0:
        from ml.explain.llm_explain import explain_anomalies
        explanation = await explain_anomalies({
            "table":     request.table_name,
            "type":      f"Timeseries STL ({request.frequency})",
            "summary":   result["decomposition_summary"],
            "anomalies": result["anomalies"][:5],  # cap to 5
        })

    return TimeseriesAnomalyResponse(
        table_name=request.table_name,
        date_col=request.date_col,
        value_col=request.value_col,
        explanation=explanation,
        **result,
    )