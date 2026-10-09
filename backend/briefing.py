from datetime import datetime

from database import list_reminders, list_tasks
from reminders import format_due
from weather import format_weather, get_weather

MAX_TASKS_SHOWN = 10


def greeting(now):
    if now.hour < 12:
        return "Good morning"
    if now.hour < 18:
        return "Good afternoon"
    return "Good evening"


def _clock(due):
    return f"{due.hour % 12 or 12}:{due:%M} {due:%p}"


def build_briefing(now, tasks, reminders, weather_text):
    """Assemble the briefing text. Pure function: everything it needs is passed in."""
    lines = [f"{greeting(now)}! Here is your briefing for {now:%a, %b} {now.day}.", ""]
    lines += [weather_text, ""]

    upcoming = [
        (datetime.strptime(r["due_at"], "%Y-%m-%d %H:%M"), r["text"]) for r in reminders
    ]
    today = [(due, text) for due, text in upcoming if due.date() == now.date()]
    later = [(due, text) for due, text in upcoming if due.date() > now.date()]

    if today:
        lines.append("Reminders today:")
        lines += [f"{i}. {text} - {_clock(due)}" for i, (due, text) in enumerate(today, 1)]
    else:
        lines.append("Reminders today: none.")
        if later:
            due, text = later[0]
            lines.append(f"Next reminder: {text} - {format_due(due)}.")
    lines.append("")

    if tasks:
        lines.append(f"Open tasks ({len(tasks)}):")
        shown = tasks[:MAX_TASKS_SHOWN]
        lines += [f"{i}. {t['title']}" for i, t in enumerate(shown, 1)]
        if len(tasks) > len(shown):
            lines.append(f"...and {len(tasks) - len(shown)} more.")
    else:
        lines.append("Open tasks: none. Enjoy your day!")

    return "\n".join(lines)


def build_daily_briefing():
    return build_briefing(
        datetime.now(),
        list_tasks(),
        list_reminders(50),
        format_weather(get_weather()),
    )