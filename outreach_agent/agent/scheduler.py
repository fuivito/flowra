from __future__ import annotations

from datetime import datetime, timezone


def is_due(contact: dict, intervals_days: tuple[int, ...]) -> bool:
    followup_count = contact.get("followup_count", 0)
    if followup_count >= len(intervals_days):
        return False

    last_sent = contact.get("last_email_sent_at")
    if not last_sent:
        return False

    elapsed = days_since(last_sent)
    required = intervals_days[followup_count]
    return elapsed >= required


def days_since(timestamp: str) -> float:
    try:
        # Notion returns ISO 8601 dates — handle both date-only and datetime strings
        if "T" in timestamp:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(timestamp).replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (now - dt).total_seconds() / 86400
    except (ValueError, TypeError):
        return 0.0
