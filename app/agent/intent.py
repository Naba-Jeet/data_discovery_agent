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
    ("anomaly",   r"\b(anomal|outlier|spike|unusual|drift|detect)\b"),
    ("dq",        r"\b(dq|data.?quality|quality.?check|validate|null.?check|duplicates?|freshness|dq.?rule|add.?rule|list.?rules?|run.?checks?)\b"),
    ("nl_to_sql", r"\b(how many|what is|list|find|give me|top \d+|average|count|sum|total)\b"),
    ("query",     r"\b(run|execute|select|fetch|show me the data)\b"),
    ("schema",    r"\b(schema|columns?|metadata|describe|structure)\b"),
]

_COMPILED = [(intent, re.compile(pattern, re.IGNORECASE)) for intent, pattern in _RULES]

_TABLE_PATTERN = re.compile(
    r'\b(?:in|for|on|table|from)\s+([a-zA-Z_][a-zA-Z0-9_]*)\b',
    re.IGNORECASE
)

def extract_table(user_message: str) -> str:
    match = _TABLE_PATTERN.search(user_message)
    return match.group(1) if match else ""

def classify(user_message: str) -> str:
    """Return the intent label that matches first, or 'unknown'."""
    for intent, pattern in _COMPILED:
        if pattern.search(user_message):
            return intent
    return "unknown"
