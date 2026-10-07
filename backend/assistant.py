import json
import random

import ollama

from database import (
    add_fact,
    add_message,
    add_note,
    add_task,
    get_recent_messages,
    list_facts,
    list_notes,
    list_tasks,
    set_task_done,
)

MODEL = "qwen2.5:7b"

SYSTEM_PROMPT = (
    "You are Jarvis, a personal AI assistant running on the user's own laptop. "
    "Be concise, helpful, and calm. Address the user politely. "
    "Keep replies short, at most three sentences, unless the user asks for detail. "
    "If you don't know something, say so instead of guessing. "
    "Never invent personal details about the user. If asked about the user's "
    "preferences, history, relationships, or personal life, answer only from your "
    "long-term memory notes or this conversation. If the answer is not there, say you "
    "don't know yet and invite them to tell you. "
    "Long-term memory, the task list, and notes are managed automatically by the system. "
    "Only say you remembered, saved, added, or completed something if a note below "
    "says you just did it. If the user asks you to add or complete a task and no note "
    "says it was done, say it was not done and ask them to rephrase, for example: "
    "Add a task to buy rice. "
    "If the user asks you to save a note and no note below says it was saved, say it "
    "was not saved and ask them to rephrase, for example: Take a note: the meeting "
    "moved to Thursday. "
    "Never ask the user whether to add a task or a note. The system does that itself."
)

ANALYSIS_PROMPT = """You read one message from the user and return JSON with these fields:
- facts: lasting facts about the user (name, age, job, location, preferences, routines, important people, goals). One short sentence each, starting with "The user". Ignore questions, requests, small talk, and temporary things. Never include passwords, API keys, or card or ID numbers.
- action, one of:
  "add_task": the user clearly asks to add something to their task or to-do list (for example "add a task to..." or "put ... on my to-do list").
  "suggest_task": the user says they need to, have to, or ought to do something concrete (buy, check, call, finish...) but does NOT ask to add it to a list.
  "complete_task": the user says a task on the open task list is finished, or asks to mark it done.
  "list_tasks": the user asks to see, show, or list their tasks or to-do list.
  "add_note": the user clearly asks to save a note (for example "take a note...", "note that...", "jot down...").
  "list_notes": the user asks to see, show, or list their notes.
  "confirm_pending": the pending question is not "none" and the user agrees to it.
  "decline_pending": the pending question is not "none" and the user says no.
  "none": anything else.
- task_title: for add_task or suggest_task, a short title for the task. Keep any time phrase (for example "by Friday"). Otherwise an empty string.
- task_id: for complete_task, the id of the matching task from the open task list. Otherwise 0.
- note_text: for add_note, the note as one clear sentence. Otherwise an empty string.
Reply with JSON only.

Examples:

Open tasks:
none
Pending question: none
Message: My name is Maria and I work as a nurse.
{"facts": ["The user's name is Maria.", "The user works as a nurse."], "action": "none", "task_title": "", "task_id": 0, "note_text": ""}

Open tasks:
none
Pending question: none
Message: Add a task to buy rice.
{"facts": [], "action": "add_task", "task_title": "Buy rice", "task_id": 0, "note_text": ""}

Open tasks:
none
Pending question: none
Message: Please put "call the bank" on my to-do list.
{"facts": [], "action": "add_task", "task_title": "Call the bank", "task_id": 0, "note_text": ""}

Open tasks:
3: Buy rice
4: Call the bank
Pending question: none
Message: What are my tasks?
{"facts": [], "action": "list_tasks", "task_title": "", "task_id": 0, "note_text": ""}

Open tasks:
3: Buy rice
4: Call the bank
Pending question: none
Message: I finished calling the bank.
{"facts": [], "action": "complete_task", "task_title": "", "task_id": 4, "note_text": ""}

Open tasks:
none
Pending question: none
Message: What is 12 times 12?
{"facts": [], "action": "none", "task_title": "", "task_id": 0, "note_text": ""}

Open tasks:
none
Pending question: none
Message: I need to buy a cookie.
{"facts": [], "action": "suggest_task", "task_title": "Buy a cookie", "task_id": 0, "note_text": ""}

Open tasks:
none
Pending question: none
Message: I need to finish the report by Friday.
{"facts": [], "action": "suggest_task", "task_title": "Finish the report by Friday", "task_id": 0, "note_text": ""}

Open tasks:
none
Pending question: none
Message: I need to check the fridge.
{"facts": [], "action": "suggest_task", "task_title": "Check the fridge", "task_id": 0, "note_text": ""}

Open tasks:
none
Pending question: none
Message: I love hiking on weekends.
{"facts": ["The user loves hiking on weekends."], "action": "none", "task_title": "", "task_id": 0, "note_text": ""}

Open tasks:
none
Pending question: none
Message: Take a note: the meeting with Ben moved to Thursday.
{"facts": [], "action": "add_note", "task_title": "", "task_id": 0, "note_text": "The meeting with Ben moved to Thursday."}

Open tasks:
none
Pending question: none
Message: Jot down that the printer is out of ink.
{"facts": [], "action": "add_note", "task_title": "", "task_id": 0, "note_text": "The printer is out of ink."}

Open tasks:
none
Pending question: none
Message: Show me my notes.
{"facts": [], "action": "list_notes", "task_title": "", "task_id": 0, "note_text": ""}

Open tasks:
none
Pending question: Should I add the task "Buy a cookie"?
Message: Yes please.
{"facts": [], "action": "confirm_pending", "task_title": "", "task_id": 0, "note_text": ""}

Open tasks:
none
Pending question: Should I add the task "Buy a cookie"?
Message: No, never mind.
{"facts": [], "action": "decline_pending", "task_title": "", "task_id": 0, "note_text": ""}

Open tasks:
none
Pending question: Should I add the task "Buy a cookie"?
Message: What is 12 times 12?
{"facts": [], "action": "none", "task_title": "", "task_id": 0, "note_text": ""}
"""

VALID_ACTIONS = (
    "none",
    "add_task",
    "suggest_task",
    "complete_task",
    "list_tasks",
    "add_note",
    "list_notes",
    "confirm_pending",
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
    },
    "required": ["facts", "action", "task_title", "task_id", "note_text"],
}

EMPTY_ANALYSIS = {
    "facts": [],
    "action": "none",
    "task_title": "",
    "task_id": 0,
    "note_text": "",
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

# A task title waiting for the user's yes or no. It lives for one message only.
pending_task = None


def analyze_message(user_message):
    open_tasks = list_tasks()
    tasks_text = "\n".join(f"{t['id']}: {t['title']}" for t in open_tasks) or "none"
    pending_text = f'Should I add the task "{pending_task}"?' if pending_task else "none"
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
            options={"temperature": 0},
        )
        data = json.loads(response.message.content)
    except Exception as err:
        print("Message analysis failed:", err, flush=True)
        return dict(EMPTY_ANALYSIS)

    facts = [f.strip() for f in data.get("facts", []) if isinstance(f, str) and f.strip()]
    action = data.get("action")
    if action not in VALID_ACTIONS:
        action = "none"
    title = data.get("task_title")
    title = title.strip() if isinstance(title, str) else ""
    task_id = data.get("task_id")
    task_id = task_id if isinstance(task_id, int) else 0
    note_text = data.get("note_text")
    note_text = note_text.strip() if isinstance(note_text, str) else ""
    return {
        "facts": facts,
        "action": action,
        "task_title": title,
        "task_id": task_id,
        "note_text": note_text,
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
            "\n\nNo task or note was added or completed during this message. "
            "Do not say that any task or note was added, updated, or completed. "
            "If you mention tasks, list only the open tasks given above."
        )

    return prompt


def handle_message(user_message):
    """The whole chat flow: analyze, act, reply, and save both sides."""
    global pending_task

    add_message("user", user_message)

    analysis = analyze_message(user_message)
    action = analysis["action"]

    # A pending question lives for one message only: take it, then clear it.
    previous_pending, pending_task = pending_task, None

    new_facts = [f for f in analysis["facts"] if add_fact(f)]
    action_note = None
    reply = None

    if action == "suggest_task" and analysis["task_title"]:
        pending_task = analysis["task_title"]
        reply = random.choice(SUGGESTION_REPLIES).format(title=pending_task)
    elif action == "confirm_pending" and previous_pending:
        if add_task(previous_pending):
            reply = random.choice(CONFIRM_REPLIES).format(title=previous_pending)
    elif action == "decline_pending" and previous_pending:
        reply = random.choice(DECLINE_REPLIES)
    elif action == "list_tasks":
        # Data questions are answered by code, not by the model.
        reply = format_task_list(list_tasks())
    elif action == "list_notes":
        reply = format_note_list(list_notes(10))
    else:
        action_note = run_action(analysis)

    if reply is None:
        messages = [
            {"role": "system", "content": build_system_prompt(new_facts, action_note)}
        ] + get_recent_messages(20)
        response = ollama.chat(
            model=MODEL,
            messages=messages,
            options={"temperature": 0.5, "num_predict": 400},
        )
        reply = response.message.content or "Done."

    add_message("assistant", reply)
    return reply