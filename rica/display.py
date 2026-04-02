"""Display functions for Rica CLI output formatting."""

def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _langs(session: dict) -> str:
    import json
    raw = session.get("languages", [])
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw or "—"
    if not raw:
        return "—"
    return " / ".join(str(lang) for lang in raw)
