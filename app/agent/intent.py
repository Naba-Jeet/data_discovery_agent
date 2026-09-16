"""
Intent classifier — keyword/regex based (no LLM call needed).
Returns one of: schema | query | anomaly | nl_to_sql | unknown
"""
import re

# _RULES = [
#     ("schema",    r"\b(schema|tables?|columns?|metadata|describe|structure)\b"),
#     ("anomaly",   r"\b(anomal|outlier|spike|unusual|drift|detect)\b"),
#     ("dq",        r"\b(dq|data.?quality|quality.?check|validate|null.?check|duplicates?|freshness|dq.?rule|add.?rule|list.?rules?|run.?checks?)\b"),
#     ("nl_to_sql", r"\b(how many|what is|list|find|give me|top \d+|average|count|sum|total)\b"),
#     ("query",     r"\b(run|execute|select|fetch|show me the data)\b"),
# ]

_RULES = [
    ("volume_anomaly", r"\b(volume|trend|surge|spike|dip|drop|record.?count|row.?count|duplicates?\s+by|grain)\b"),
    ("row_anomaly", r"\b(row.?count|row.?anomaly|frequency|daily|weekly|monthly|quarterly|yearly|period.?count|count.?per|volume.?trend)\b"),
    ("anomaly", r"\b(anomal|outlier|unusual|drift|detect)\b"),
    ("explain_anomaly", r"\b(explain|why|reason|insight|finding|interpret)\b"),
    ("dq", r"\b(dq|data.?quality|quality.?check|validate|null.?check|duplicates?|freshness|dq.?rule|add.?rule|list.?rules?|run.?checks?)\b"),
    ("nl_to_sql", r"\b(how many|what is|list|find|give me|show me|top \d+|average|count|sum|total)\b"),
    ("query", r"\b(run|execute|select|fetch|display|get me|pull)\b"),
    ("schema", r"\b(schema|columns?|metadata|describe|structure)\b"),
]

_COMPILED = [(intent, re.compile(pattern, re.IGNORECASE)) for intent, pattern in _RULES]

_TABLE_PATTERN = re.compile(
    r'\b(?:in|for|on|table|from)\s+([a-zA-Z_][a-zA-Z0-9_]*)\b',
    re.IGNORECASE
)

_GRANULARITY_PATTERN = re.compile(
    r'\b(day|daily|week|weekly|month|monthly|quarter|quarterly)\b',
    re.IGNORECASE
)

_THRESHOLD_PATTERN = re.compile(r'(\d+)\s*%')

_GRAIN_PATTERN = re.compile(
    r'\b(?:by|grain\s+columns?|grain|grouped?\s+by|on\s+columns?)\s+([\w,\s]+?)(?:\s+in|\s+from|\s+table|on\b|$)',
    re.IGNORECASE
)

_FREQ_PATTERN = re.compile(
    r"\b(daily|weekly|monthly|quarterly|yearly)\b", re.IGNORECASE
)

def extract_frequency(text: str) -> str | None:
    """Extract frequency keyword from user message."""
    m = _FREQ_PATTERN.search(text)
    return m.group(1).lower() if m else None

def extract_granularity(user_message: str) -> str:
    """Normalise user granularity hint → day/week/month/quarter."""
    match = _GRANULARITY_PATTERN.search(user_message)
    if not match:
        return "week"
    val = match.group(1).lower()
    return {
        "daily": "day", "weekly": "week",
        "monthly": "month", "quarterly": "quarter"
    }.get(val, val)

def extract_threshold(user_message: str) -> float:
    """Extract variance threshold % from message, default 30.0."""
    match = _THRESHOLD_PATTERN.search(user_message)
    return float(match.group(1)) if match else 30.0

def extract_grain_cols(user_message: str) -> str:
    """Extract grain column names if user specifies 'by col1, col2'."""
    match = _GRAIN_PATTERN.search(user_message)
    if not match:
        return ""
    raw = match.group(1)
    cols = [c.strip() for c in re.split(r'[,\s]+', raw) if c.strip()]
    return ",".join(cols)

def extract_table(message: str) -> str:
    # Match full dotted table names: catalog.schema.table or schema.table
    match = re.search(r'\b([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*){1,2})\b', message)
    if match:
        return match.group(1)
    # Fallback: single word after FROM/table/in
    match = re.search(r'\b(?:from|table|in|of)\s+([a-zA-Z_][a-zA-Z0-9_]*)\b', message, re.IGNORECASE)
    return match.group(1) if match else ""

def classify(user_message: str) -> str:
    """Return the intent label that matches first, or 'unknown'."""
    for intent, pattern in _COMPILED:
        if pattern.search(user_message):
            return intent
    return "unknown"
