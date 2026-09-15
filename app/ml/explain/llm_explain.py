# app/ml/explain/llm_explain.py

import httpx
from config import OLLAMA_BASE_URL

EXPLAIN_MODEL = "phi3.5"


async def explain_anomalies(context: dict) -> str:
    try:
        async with httpx.AsyncClient(timeout=500) as client:
            resp = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": EXPLAIN_MODEL,
                    "prompt": _build_prompt(context),
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": 150},
                },
            )
            resp.raise_for_status()
            return resp.json().get("response", "").strip()
    except httpx.ReadTimeout:
        return "Explanation unavailable: model timed out. Try again or use a smaller model."
    except Exception as e:
        return f"Explanation unavailable: {str(e)}"


def _build_prompt(ctx: dict) -> str:
    return f"""You are a data quality analyst. Analyze the following anomaly detection results and provide a concise business-readable explanation.

Table: {ctx['table']}
Detection Type: {ctx['type']}
Summary: {ctx['summary']}
Anomalies Found: {ctx['anomalies']}

Respond in 3-5 sentences. Focus on:
1. What the anomaly means in business terms
2. Severity assessment
3. Recommended next action

Do not repeat raw numbers excessively. Be direct."""