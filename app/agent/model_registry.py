MODEL_REGISTRY = {
    "intent_router": {
        "runner": "ollama",
        "model": "qwen2.5:1.5b",
        "keep_alive": -1,          # always pinned
        "temperature": 0.0,
        "max_tokens": 128,
    },
    "nl_to_sql": {
        "runner": "ollama",
        "model": "qwen2.5-coder:7b",
        "keep_alive": "5m",
        "temperature": 0.0,
        "max_tokens": 512,
    },
    "code_gen": {
        "runner": "ollama",
        "model": "qwen2.5-coder:7b",
        "keep_alive": "5m",
        "temperature": 0.2,
        "max_tokens": 1024,
    },
    "reasoning": {
        "runner": "ollama",
        "model": "phi4",           # ← swapped from qwen2.5:14b
        "keep_alive": "5m",
        "temperature": 0.3,
        "max_tokens": 2048,
    },
    "anomaly_ml": {
        "runner": "sklearn",
        "model": "IsolationForest",
        "keep_alive": None,
        "temperature": None,
        "max_tokens": None,
    },
    "timeseries_ml": {
        "runner": "statsmodels",
        "model": "STL",
        "keep_alive": None,
        "temperature": None,
        "max_tokens": None,
    },
    "lineage_graph": {
        "runner": "networkx",
        "model": "DAG",
        "keep_alive": None,
        "temperature": None,
        "max_tokens": None,
    },
    "dq_rules": {
        "runner": "native",
        "model": "rule_engine",
        "keep_alive": None,
        "temperature": None,
        "max_tokens": None,
    },
}


def get_model(task: str) -> dict:
    """Fetch model config by task name."""
    config = MODEL_REGISTRY.get(task)
    if not config:
        # fallback to intent router
        return MODEL_REGISTRY["intent_router"]
    return config