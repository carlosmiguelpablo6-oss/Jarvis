import re
from datetime import datetime

from database import (
    delete_note,
    delete_reminder,
    delete_task,
    list_notes,
    list_reminders,
    list_tasks,
)
from reminders import format_due

KINDS = ("task", "note", "reminder")
MAX_CHOICES = 5

# Words that describe the request itself, not the item.
IGNORED_WORDS = {
    "the", "a", "an", "my", "to", "of", "about", "for", "on", "in", "at", "that",
    "this", "it", "one", "please", "called", "named", "with", "and",
    "reminder", "reminders", "note", "notes", "task", "tasks",
    "delete", "remove", "cancel",
}

ORDINALS = {
    "1": 0, "one": 0, "first": 0,
    "2": 1, "two": 1, "second": 1,
    "3": 2, "three": 2, "third": 2,
    "4": 3, "four": 3, "fourth": 3,
    "5": 4, "five": 4, "fifth": 4,
}
FILLER_WORDS = {"number", "the", "please", "item", "option", "a", "no", "num"}

_DELETERS = {"task": delete_task, "note": delete_note, "reminder": delete_reminder}


def _items(kind):
    """Everything of one kind as {"id", "label", "search"}."""
    if kind == "task":
        return [
            {"id": t["id"], "label": t["title"], "search": t["title"]}
            for t in list_tasks(include_done=True)
        ]
    if kind == "note":
        return [
            {"id": n["id"], "label": n["content"], "search": n["content"]}
            for n in list_notes(50)
        ]
    items = []
    for r in list_reminders(50):
        due = datetime.strptime(r["due_at"], "%Y-%m-%d %H:%M")
        items.append(
            {
                "id": r["id"],
                "label": f"{r['text']} ({format_due(due)})",
                "search": r["text"],
            }
        )
    return items


def query_words(text):
    words = re.findall(r"[a-z0-9']+", (text or "").lower())
    return [w for w in words if w not in IGNORED_WORDS]


def find_matches(kind, query):
    """Items whose text contains every important word of the query."""
    items = _items(kind)
    words = query_words(query)
    if not words:
        return items

    def has(text, word):
        stem = word[:-1] if word.endswith("s") and len(word) > 3 else word
        return stem in text

    return [i for i in items if all(has(i["search"].lower(), w) for w in words)]


def _ask_to_confirm(kind, item):
    pending = {"type": "delete", "kind": kind, "id": item["id"], "label": item["label"]}
    return f'Delete the {kind} "{item["label"]}"? (yes or no)', pending


def begin_delete(analysis):
    """Returns (reply, pending). Nothing is deleted here. Jarvis always asks first."""
    kind = analysis["item_kind"]
    query = analysis["item_text"]
    if kind not in KINDS:
        return (
            "Do you want me to delete a task, a note, or a reminder? "
            "Try: Cancel my reminder to call mom.",
            None,
        )
    if not _items(kind):
        return f"You have no {kind}s to delete.", None

    matches = find_matches(kind, query)
    if not matches:
        return (
            f'I couldn\'t find a {kind} matching "{query}". '
            f'Say "show my {kind}s" to see them.',
            None,
        )
    if len(matches) == 1:
        return _ask_to_confirm(kind, matches[0])

    shown = matches[:MAX_CHOICES]
    lines = "\n".join(f"{i}. {m['label']}" for i, m in enumerate(shown, start=1))
    more = (
        f" (showing the first {MAX_CHOICES}; be more specific to narrow it down)"
        if len(matches) > MAX_CHOICES
        else ""
    )
    reply = (
        f"I found {len(matches)} {kind}s that match{more}:\n{lines}\n"
        'Which one should I delete? Say the number, or "never mind".'
    )
    return reply, {"type": "delete_choice", "kind": kind, "items": shown}


def parse_choice(message, count):
    """Read 'two', '2', 'the second one', '#3'. Returns a 0-based index or None."""
    words = [w for w in re.sub(r"[^a-z0-9 ]", " ", message.lower()).split() if w not in FILLER_WORDS]
    if not words or len(words) > 3:
        return None
    found = [ORDINALS[w] for w in words if w in ORDINALS]
    if len(found) > 1:  # "the second one": ignore the filler "one"
        found = [ORDINALS[w] for w in words if w in ORDINALS and w != "one"] or found
    if not found or found[0] >= count:
        return None
    return found[0]


def choose_item(pending, index):
    return _ask_to_confirm(pending["kind"], pending["items"][index])


def confirm_delete(pending):
    if _DELETERS[pending["kind"]](pending["id"]):
        return f'Done. I deleted the {pending["kind"]} "{pending["label"]}".'
    return f'That {pending["kind"]} was already gone.'