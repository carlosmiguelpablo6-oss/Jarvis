import re
from datetime import datetime

import dateparser

_SETTINGS = {"PREFER_DATES_FROM": "future", "RETURN_AS_TIMEZONE_AWARE": False}


def _normalize(text):
    t = text.lower().strip().rstrip(".!?")
    t = t.replace("half an hour", "30 minutes")
    t = t.replace("an hour", "1 hour")
    t = t.replace("tonight", "today")
    t = re.sub(r"\bnext\s+", "", t)
    t = re.sub(r"\bthis\s+", "", t)
    return t


def parse_when(text, now=None):
    """Turn a phrase like 'tomorrow at 7 am' into a datetime.

    Returns (datetime, None) on success or (None, error_message) on failure.
    """
    now = now or datetime.now()
    phrase = _normalize(text or "")
    if not phrase:
        return None, "I need a time for that reminder."

    settings = dict(_SETTINGS, RELATIVE_BASE=now)
    due = dateparser.parse(phrase, settings=settings)
    if due is None:
        return None, (
            f'I could not understand the time "{text}". '
            'Try something like "tomorrow at 7 am", "in 30 minutes", or "friday at 3 pm".'
        )

    relative = phrase.startswith("in ")
    if not relative and due.hour == now.hour and due.minute == now.minute:
        return None, (
            f'I need a clock time for "{text}". '
            'Try something like "tomorrow at 7 am".'
        )

    due = due.replace(second=0, microsecond=0)
    if due <= now:
        return None, f'That time ("{text}") has already passed. Try a time in the future.'
    return due, None


def format_due(due):
    hour = due.hour % 12 or 12
    return f"{due:%a, %b} {due.day} at {hour}:{due:%M} {due:%p}"