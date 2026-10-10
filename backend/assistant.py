import json
import random
import re
from datetime import date, datetime

import ollama

from database import (
    add_fact,
    add_message,
    add_note,
    add_reminder,
    add_task,
    get_recent_messages,
    list_facts,
    list_notes,
    list_reminders,
    list_tasks,
    set_setting,
    set_task_done,
)
from briefing import build_daily_briefing
from deletion import KINDS, begin_delete, choose_item, confirm_delete, parse_choice
from reminders import format_due, parse_when
from weather import format_weather, get_weather

MODEL = "qwen2.5:7b"
NUM_CTX = 6144  # room for the long analysis prompt (the default of 4096 is too tight)

SYSTEM_PROMPT = (
    "You are Jarvis, a personal AI assistant running on the user's own laptop. "
    "Be concise, helpful, and calm. Address the user politely. "
    "Keep replies short, at most three sentences, unless the user asks for detail. "
    "If you don't know something, say so instead of guessing. "
    "Never invent personal details about the user. If asked about the user's "
    "preferences, history, relationships, or personal life, answer only from your "
    "long-term memory notes or this conversation. If the answer is not there, say you "
    "don't know yet and invite them to tell you. "
    "Long-term memory, the task list, notes, and reminders are managed automatically "
    "by the system. "
    "Only say you remembered, saved, added, or completed something if a note below "
    "says you just did it. If the user asks you to add or complete a task and no note "
    "says it was done, say it was not done and ask them to rephrase, for example: "
    "Add a task to buy rice. "
    "If the user asks you to save a note and no note below says it was saved, say it "
    "was not saved and ask them to rephrase, for example: Take a note: the meeting "
    "moved to Thursday. "
    "You cannot set reminders yourself. If the user asks to be reminded and no note "
    "below says it was set, say it was not set and ask them to rephrase, for example: "
    "Remind me to call mom tomorrow at 7 am. "
    "You cannot delete anything yourself. If the user asks to delete, remove, or cancel "
    "something and no note below says it was deleted, say it was not deleted and ask "
    "them to rephrase, for example: Cancel my reminder to call mom. "
    "Never ask the user whether to add a task or a note. The system does that itself."
)

ANALYSIS_INSTRUCTIONS = """You read one message from the user and return JSON with these fields:
- facts: lasting facts about the user (name, age, job, location, preferences, routines, important people, goals). One short sentence each, starting with "The user". Ignore questions, requests, small talk, and temporary things. Never include passwords, API keys, or card or ID numbers.
- action, one of:
  "add_task": the user clearly asks to add something to their task or to-do list (for example "add a task to..." or "put ... on my to-do list").
  "suggest_task": the user says they need to, have to, or ought to do something concrete (buy, check, call, finish...) but does NOT ask to add it to a list or to be reminded.
  "complete_task": the user says a task on the open task list is finished, or asks to mark it done.
  "list_tasks": the user asks to see, show, or list their tasks or to-do list.
  "add_note": the user clearly asks to save a note (for example "take a note...", "note that...", "jot down...").
  "list_notes": the user asks to see, show, or list their notes.
  "add_reminder": the user asks to be reminded of something (for example "remind me to...").
  "list_reminders": the user asks to see, show, or list their reminders.
  "daily_briefing": the user asks for their daily briefing, a summary of their day, or what is on today.
  "weather": the user asks about the weather or whether it will rain.
  "delete_item": the user asks to delete, remove, or cancel ONE task, note, or reminder (not "finished": that is complete_task).
  "confirm_pending": the pending question asks whether to add a task or delete an item, and the user agrees.
  "give_reminder_time": the pending question asks when to remind the user, and the user gives a time. Put the time in when_text, written clearly (for example "4 pm" or "tomorrow at 8 am").
  "decline_pending": the pending question is not "none" and the user says no, never mind, or cancels.
  "none": anything else.
- task_title: for add_task or suggest_task, a short title for the task. Keep any time phrase (for example "by Friday"). Otherwise an empty string.
- task_id: for complete_task, the id of the matching task from the open task list. Otherwise 0.
- note_text: for add_note, the note as one clear sentence. Otherwise an empty string.
- reminder_text: for add_reminder, what to be reminded of, short, starting with a verb (for example "Call mom"). Otherwise an empty string.
- when_text: for add_reminder, the time phrase exactly as the user said it (for example "tomorrow at 7 am" or "in 10 minutes"). Empty if the user gave no time. Otherwise an empty string.
- item_kind: for delete_item, "task", "note", or "reminder". Otherwise an empty string.
- item_text: for delete_item, the few words that identify the item, without words like delete, my, or the. Empty if the user did not say which one. Otherwise an empty string.
Reply with JSON only."""

BLANK_RESULT = {
    "facts": [],
    "action": "none",
    "task_title": "",
    "task_id": 0,
    "note_text": "",
    "reminder_text": "",
    "when_text": "",
    "item_kind": "",
    "item_text": "",
}


def _example(message, tasks="none", pending="none", **fields):
    result = dict(BLANK_RESULT, **fields)
    return (
        f"Open tasks:\n{tasks}\nPending question: {pending}\n"
        f"Message: {message}\n{json.dumps(result)}"
    )


_COOKIE = 'Should I add the task "Buy a cookie"?'
_TRASH = 'When should I remind the user about "Take out the trash"?'
_DELETE = 'Should I delete the reminder "Call mom (Thu, Oct 8 at 7:00 AM)"?'
_OPEN = "3: Buy rice\n4: Call the bank"

EXAMPLES = [
    _example(
        "My name is Maria and I work as a nurse.",
        facts=["The user's name is Maria.", "The user works as a nurse."],
    ),
    _example("Add a task to buy rice.", action="add_task", task_title="Buy rice"),
    _example(
        'Please put "call the bank" on my to-do list.',
        action="add_task",
        task_title="Call the bank",
    ),
    _example("What are my tasks?", tasks=_OPEN, action="list_tasks"),
    _example(
        "I finished calling the bank.", tasks=_OPEN, action="complete_task", task_id=4
    ),
    _example("What is 12 times 12?"),
    _example(
        "I need to buy a cookie.", action="suggest_task", task_title="Buy a cookie"
    ),
    _example(
        "I need to finish the report by Friday.",
        action="suggest_task",
        task_title="Finish the report by Friday",
    ),
    _example(
        "I need to check the fridge.", action="suggest_task", task_title="Check the fridge"
    ),
    _example(
        "I love hiking on weekends.", facts=["The user loves hiking on weekends."]
    ),
    _example(
        "Take a note: the meeting with Ben moved to Thursday.",
        action="add_note",
        note_text="The meeting with Ben moved to Thursday.",
    ),
    _example(
        "Jot down that the printer is out of ink.",
        action="add_note",
        note_text="The printer is out of ink.",
    ),
    _example("Show me my notes.", action="list_notes"),
    _example(
        "Remind me to call mom tomorrow at 7 am.",
        action="add_reminder",
        reminder_text="Call mom",
        when_text="tomorrow at 7 am",
    ),
    _example(
        "Remind me in 10 minutes to check the oven.",
        action="add_reminder",
        reminder_text="Check the oven",
        when_text="in 10 minutes",
    ),
    _example(
        "Remind me to take out the trash.",
        action="add_reminder",
        reminder_text="Take out the trash",
    ),
    _example("What are my reminders?", action="list_reminders"),
    _example("Give me my daily briefing.", action="daily_briefing"),
    _example("What does my day look like?", action="daily_briefing"),
    _example("Will it rain today?", action="weather"),
    _example("Good morning Jarvis."),
    _example("Yes please.", pending=_COOKIE, action="confirm_pending"),
    _example("No, never mind.", pending=_COOKIE, action="decline_pending"),
    _example("What is 12 times 12?", pending=_COOKIE),
    _example(
        "Around 4pm.", pending=_TRASH, action="give_reminder_time", when_text="4 pm"
    ),
    _example(
        "Tomorrow morning at 8.",
        pending=_TRASH,
        action="give_reminder_time",
        when_text="tomorrow at 8 am",
    ),
    _example("Never mind.", pending=_TRASH, action="decline_pending"),
    _example("What is 12 times 12?", pending=_TRASH),

    _example(
        "Cancel my reminder to call mom.",
        action="delete_item",
        item_kind="reminder",
        item_text="call mom",
    ),
    _example(
        "Delete my note about the printer.",
        action="delete_item",
        item_kind="note",
        item_text="printer",
    ),
    _example(
        "Remove the task buy rice.",
        action="delete_item",
        item_kind="task",
        item_text="buy rice",
    ),
    _example("Delete my reminder.", action="delete_item", item_kind="reminder"),
    _example("Yes, delete it.", pending=_DELETE, action="confirm_pending"),
    _example("No, keep it.", pending=_DELETE, action="decline_pending"),
]

ANALYSIS_PROMPT = ANALYSIS_INSTRUCTIONS + "\n\nExamples:\n\n" + "\n\n".join(EXAMPLES)

VALID_ACTIONS = (
    "none",
    "add_task",
    "suggest_task",
    "complete_task",
    "list_tasks",
    "add_note",
    "list_notes",
    "add_reminder",
    "list_reminders",
    "daily_briefing",
    "weather",
    "delete_item",
    "confirm_pending",
    "give_reminder_time",
    "decline_pending",
)

ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {"type": "array", "items": {"type": "string"}},
        "action": {"type": "string", "enum": list(VALID_ACTIONS)},
        "task_title": {"type": "string"},
        "task_id": {"type": "integer"},
        "note_text": {"type": "string"},
        "reminder_text": {"type": "string"},
        "when_text": {"type": "string"},
        "item_kind": {"type": "string"},
        "item_text": {"type": "string"},
    },
    "required": list(BLANK_RESULT.keys()),
}

SUGGESTION_REPLIES = [
    '"{title}" sounds like a task. Would you like me to add it to your task list?',
    'That looks like a task to me: "{title}". Want me to add it to your list?',
    'Would you mind if I add "{title}" to your tasks?',
]
CONFIRM_REPLIES = [
    'Done. I added "{title}" to your tasks.',
    'Added "{title}" to your task list.',
]
DECLINE_REPLIES = [
    "Okay, I won't add it.",
    "No problem, I'll leave it off your list.",
]

# A question waiting for the user's answer, for example
# {"type": "task", "value": "Buy a cookie"} or {"type": "reminder", "value": "Call mom"}.
# It lives for one message only.
pending = None

# Safety net: the model sometimes claims it saved or set something when our code did not.
FALSE_CLAIM = re.compile(
    r"\b(i('ll| will| have|'ve| am going to)\s+(remind|set|add|save|remember|delete|remove|cancel)\b"
    r"|(reminder|task|note)\s+(has been|is now|was|is)\s+(set|added|saved|created|deleted|removed|cancelled)\b"
    r"|(added|saved|set|deleted|removed|cancelled)\b.{0,40}\b(task|note|reminder|to-do)\b)",
    re.IGNORECASE,
)
FALSE_CLAIM_REPLY = (
    "I haven't saved or set anything from that message. You can say, for example: "
    "Remind me to call mom tomorrow at 7 am, or Add a task to buy rice, "
    "or Take a note: the meeting moved to Thursday."
)


def analyze_message(user_message):
    open_tasks = list_tasks()
    tasks_text = "\n".join(f"{t['id']}: {t['title']}" for t in open_tasks) or "none"
    if pending and pending["type"] == "task":
        pending_text = f'Should I add the task "{pending["value"]}"?'
    elif pending and pending["type"] == "reminder":
        pending_text = f'When should I remind the user about "{pending["value"]}"?'
    elif pending and pending["type"] == "delete":
        pending_text = f'Should I delete the {pending["kind"]} "{pending["label"]}"?'
    elif pending and pending["type"] == "delete_choice":
        pending_text = "Which item should I delete?"
    else:
        pending_text = "none"
    try:
        response = ollama.chat(
            model=MODEL,
            messages=[
                {"role": "system", "content": ANALYSIS_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Open tasks:\n{tasks_text}\n"
                        f"Pending question: {pending_text}\n"
                        f"Message: {user_message}"
                    ),
                },
            ],
            format=ANALYSIS_SCHEMA,
            options={"temperature": 0, "num_ctx": NUM_CTX},
        )
        data = json.loads(response.message.content)
    except Exception as err:
        print("Message analysis failed:", err, flush=True)
        return dict(BLANK_RESULT)

    def text_field(name):
        value = data.get(name)
        return value.strip() if isinstance(value, str) else ""

    facts = [f.strip() for f in data.get("facts", []) if isinstance(f, str) and f.strip()]
    action = data.get("action")
    if action not in VALID_ACTIONS:
        action = "none"
    task_id = data.get("task_id")
    task_id = task_id if isinstance(task_id, int) else 0
    item_kind = text_field("item_kind").lower()
    item_kind = item_kind if item_kind in KINDS else ""
    return {
        "facts": facts,
        "action": action,
        "task_title": text_field("task_title"),
        "task_id": task_id,
        "note_text": text_field("note_text"),
        "reminder_text": text_field("reminder_text"),
        "when_text": text_field("when_text"),
        "item_kind": item_kind,
        "item_text": text_field("item_text"),
    }


def run_action(analysis):
    action = analysis["action"]

    if action == "add_task":
        title = analysis["task_title"]
        if title and add_task(title):
            return f'You just added this task to the list: "{title}".'
        return None

    if action == "complete_task":
        open_tasks = {t["id"]: t["title"] for t in list_tasks()}
        task_id = analysis["task_id"]
        if task_id in open_tasks:
            set_task_done(task_id)
            return f'You just marked this task as done: "{open_tasks[task_id]}".'
        return "The user asked to complete a task, but no matching open task was found."

    if action == "add_note":
        text = analysis["note_text"]
        if text and add_note(text):
            return f'You just saved this note: "{text}".'
        return None

    return None


def set_reminder(text, when):
    """Try to set a reminder. Returns (reply, ok). The reply is written by code."""
    due, error = parse_when(when)
    if error:
        return error, False
    add_reminder(text, due.strftime("%Y-%m-%d %H:%M"))
    return f'Okay, I will remind you about "{text}" on {format_due(due)}.', True


def format_task_list(tasks):
    if not tasks:
        return "You have no open tasks."
    lines = "\n".join(f"{i}. {t['title']}" for i, t in enumerate(tasks, start=1))
    return "Here are your open tasks:\n" + lines


def format_note_list(notes):
    if not notes:
        return "You have no saved notes."
    lines = "\n".join(f"{i}. {n['content']}" for i, n in enumerate(notes, start=1))
    return "Here are your latest notes, newest first:\n" + lines


def format_reminder_list(reminders):
    if not reminders:
        return "You have no upcoming reminders."
    lines = []
    for i, r in enumerate(reminders, start=1):
        due = datetime.strptime(r["due_at"], "%Y-%m-%d %H:%M")
        lines.append(f"{i}. {r['text']} - {format_due(due)}")
    return "Your upcoming reminders:\n" + "\n".join(lines)


def build_system_prompt(new_facts=None, action_note=None):
    prompt = SYSTEM_PROMPT

    facts = list_facts()
    if facts:
        lines = "\n".join(f"- {f['fact']}" for f in facts)
        prompt += (
            "\n\nThings you know about the user (long-term memory). "
            "Use them naturally when relevant, and never mention that you were given a list:\n"
            + lines
        )

    tasks = list_tasks()
    if tasks:
        lines = "\n".join(f"- {t['title']}" for t in tasks)
        prompt += "\n\nThe user's open tasks:\n" + lines
    else:
        prompt += "\n\nThe user has no open tasks."

    if new_facts:
        saved = "\n".join(f"- {f}" for f in new_facts)
        prompt += (
            "\n\nYou just saved these new facts to long-term memory "
            "from the user's latest message. Confirm briefly and naturally:\n"
            + saved
        )
    else:
        prompt += "\n\nNothing new was saved to long-term memory during this message."

    if action_note:
        prompt += (
            "\n\nNote about what you just did: "
            + action_note
            + " Confirm briefly and naturally."
        )
    else:
        prompt += (
            "\n\nNo task, note, or reminder was added or completed during this message. "
            "Do not say that any task, note, or reminder was added, set, updated, or "
            "completed. If you mention tasks, list only the open tasks given above."
        )

    return prompt


def handle_message(user_message):
    """The whole chat flow: analyze, act, reply, and save both sides."""
    global pending

    add_message("user", user_message)

    # "Which one?" is answered with a number. Read it directly, no model needed.
    if pending and pending["type"] == "delete_choice":
        index = parse_choice(user_message, len(pending["items"]))
        if index is not None:
            reply, pending = choose_item(pending, index)
            add_message("assistant", reply)
            return reply

    analysis = analyze_message(user_message)
    action = analysis["action"]

    # A pending question lives for one message only: take it, then clear it.
    previous, pending = pending, None
    previous_type = previous["type"] if previous else None

    new_facts = [f for f in analysis["facts"] if add_fact(f)]
    action_note = None
    reply = None

    if action == "suggest_task" and analysis["task_title"]:
        pending = {"type": "task", "value": analysis["task_title"]}
        reply = random.choice(SUGGESTION_REPLIES).format(title=analysis["task_title"])
    elif action == "confirm_pending" and previous_type == "task":
        if add_task(previous["value"]):
            reply = random.choice(CONFIRM_REPLIES).format(title=previous["value"])
    elif action == "confirm_pending" and previous_type == "delete":
        reply = confirm_delete(previous)
    elif action == "delete_item":
        reply, pending = begin_delete(analysis)
    elif action == "decline_pending" and previous:
        if previous_type in ("delete", "delete_choice"):
            reply = "Okay, I won't delete anything."
        else:
            reply = random.choice(DECLINE_REPLIES)
    elif action == "give_reminder_time" and previous_type == "reminder":
        reply, ok = set_reminder(previous["value"], analysis["when_text"])
        if not ok:
            pending = previous  # let the user try the time again
    elif action == "add_reminder":
        text = analysis["reminder_text"]
        if not text:
            reply = (
                "What should I remind you about? "
                "Try: Remind me to call mom tomorrow at 7 am."
            )
        elif not analysis["when_text"]:
            pending = {"type": "reminder", "value": text}
            reply = (
                f'When should I remind you about "{text}"? '
                "For example: tomorrow at 7 am, or in 30 minutes."
            )
        else:
            reply, ok = set_reminder(text, analysis["when_text"])
            if not ok:
                pending = {"type": "reminder", "value": text}
    elif action == "list_tasks":
        # Data questions are answered by code, not by the model.
        reply = format_task_list(list_tasks())
    elif action == "list_notes":
        reply = format_note_list(list_notes(10))
    elif action == "list_reminders":
        reply = format_reminder_list(list_reminders(10))
    elif action == "daily_briefing":
        reply = build_daily_briefing()
        set_setting("last_briefing_date", date.today().isoformat())
    elif action == "weather":
        reply = format_weather(get_weather())
    else:
        action_note = run_action(analysis)

    if reply is None:
        messages = [
            {"role": "system", "content": build_system_prompt(new_facts, action_note)}
        ] + get_recent_messages(20)
        response = ollama.chat(
            model=MODEL,
            messages=messages,
            options={"temperature": 0.5, "num_predict": 400, "num_ctx": NUM_CTX},
        )
        reply = response.message.content or "Done."
        # If the model claims it saved or set something but our code did not, correct it.
        if not (action_note or new_facts) and FALSE_CLAIM.search(reply):
            reply = FALSE_CLAIM_REPLY

    add_message("assistant", reply)
    return reply