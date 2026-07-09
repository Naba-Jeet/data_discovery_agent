import json

def format_output(data: str, fmt: str = "json") -> str:
    """
    Formats the output as JSON or Markdown.
    """
    try:
        parsed = json.loads(data)
    except Exception:
        return data

    if fmt == "json":
        return json.dumps(parsed, indent=2)

    if fmt == "markdown":
        return _to_markdown(parsed)

    return data

def _to_markdown(data: dict) -> str:
    lines = []

    if "error" in data:
        return f"❌ **Error:** {data['error']}"

    # Anomaly report
    if "anomalies_found" in data:
        lines.append(f"## 🔍 Anomaly Report — `{data['schema']}.{data['table']}`")
        lines.append(f"- **Total rows:** {data['total_rows']}")
        lines.append(f"- **Anomalies found:** {data['anomalies_found']}")
        lines.append("")

        if not data["findings"]:
            lines.append("✅ No anomalies detected.")
        else:
            lines.append("| Check | Column | Severity | Detail |")
            lines.append("|---|---|---|---|")
            for f in data["findings"]:
                severity_icon = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡"}.get(f["severity"], "⚪")
                lines.append(
                    f"| {f['check']} | {f.get('column', '-')} | {severity_icon} {f['severity']} | {f['detail']} |"
                )
        return "\n".join(lines)

    # Generic dict → markdown
    lines.append("## Query Result")
    if isinstance(data, list):
        if data:
            headers = list(data[0].keys())
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
            for row in data[:50]:
                lines.append("| " + " | ".join(str(v) for v in row.values()) + " |")
    else:
        for k, v in data.items():
            lines.append(f"- **{k}:** {v}")

    return "\n".join(lines)