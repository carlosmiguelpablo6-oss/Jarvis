import json

import ollama
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from backup import backup_database
from database import (
    add_fact,
    add_message,
    add_task,
    delete_fact,
    delete_task,
    get_recent_messages,
    init_db,
    list_facts,
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
    "Long-term memory and the task list are managed automatically by the system. "
    "Only say you remembered, saved, added, or completed something if a note below "
    "says you just did it. If the user asks you to add or complete a task and no note "
    "says it was done, say it was not done and ask them to rephrase, for example: "
    "Add a task to buy rice. "
    "If the user says they need to do something, acknowledge briefly and offer to add "
    "it as a task."
)

ANALYSIS_PROMPT = """You read one message from the user and return JSON with these fields:
- facts: lasting facts about the user (name, age, job, location, preferences, routines, important people, goals). One short sentence each, starting with "The user". Ignore questions, requests, small talk, and temporary things. Never include passwords, API keys, or card or ID numbers.
- action: "add_task" only if the user clearly asks to add something to their task or to-do list (for example "add a task to..." or "put ... on my to-do list"). Statements like "I need to..." or "I have to..." are NOT requests, so use "none" for them. "complete_task" only if the user says a task on the open task list is finished, or asks to mark it done. "list_tasks" if the user asks to see, show, or list their tasks or to-do list. Otherwise "none".
- task_title: for add_task, a short title for the task. Otherwise an empty string.
- task_id: for complete_task, the id of the matching task from the open task list. Otherwise 0.
Reply with JSON only.

Examples:

Open tasks:
none
Message: My name is Maria and I work as a nurse.
{"facts": ["The user's name is Maria.", "The user works as a nurse."], "action": "none", "task_title": "", "task_id": 0}

Open tasks:
none
Message: Add a task to buy rice.
{"facts": [], "action": "add_task", "task_title": "Buy rice", "task_id": 0}

Open tasks:
none
Message: Please put "call the bank" on my to-do list.
{"facts": [], "action": "add_task", "task_title": "Call the bank", "task_id": 0}

Open tasks:
3: Buy rice
4: Call the bank
Message: What are my tasks?
{"facts": [], "action": "list_tasks", "task_title": "", "task_id": 0}

Open tasks:
3: Buy rice
4: Call the bank
Message: I finished calling the bank.
{"facts": [], "action": "complete_task", "task_title": "", "task_id": 4}

Open tasks:
none
Message: What is 12 times 12?
{"facts": [], "action": "none", "task_title": "", "task_id": 0}

Open tasks:
none
Message: I need to finish the report by Friday.
{"facts": [], "action": "none", "task_title": "", "task_id": 0}

Open tasks:
none
Message: I love hiking on weekends.
{"facts": ["The user loves hiking on weekends."], "action": "none", "task_title": "", "task_id": 0}
"""

ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {"type": "array", "items": {"type": "string"}},
        "action": {
            "type": "string",
            "enum": ["none", "add_task", "complete_task", "list_tasks"],
        },
        "task_title": {"type": "string"},
        "task_id": {"type": "integer"},
    },
    "required": ["facts", "action", "task_title", "task_id"],
}

VALID_ACTIONS = ("none", "add_task", "complete_task", "list_tasks")
EMPTY_ANALYSIS = {"facts": [], "action": "none", "task_title": "", "task_id": 0}

app = FastAPI(title="Jarvis")

init_db()
backup_database()


def analyze_message(user_message):
    open_tasks = list_tasks()
    tasks_text = "\n".join(f"{t['id']}: {t['title']}" for t in open_tasks) or "none"
    try:
        response = ollama.chat(
            model=MODEL,
            messages=[
                {"role": "system", "content": ANALYSIS_PROMPT},
                {
                    "role": "user",
                    "content": f"Open tasks:\n{tasks_text}\nMessage: {user_message}",
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
    return {"facts": facts, "action": action, "task_title": title, "task_id": task_id}


def run_task_action(analysis):
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

    return None


def format_task_list(tasks):
    if not tasks:
        return "You have no open tasks."
    lines = "\n".join(f"{i}. {t['title']}" for i, t in enumerate(tasks, start=1))
    return "Here are your open tasks:\n" + lines


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
            "\n\nNo task was added or completed during this message. "
            "Do not say that any task was added, updated, or completed. "
            "If you mention tasks, list only the open tasks given above."
        )

    return prompt


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


class FactRequest(BaseModel):
    fact: str


class TaskRequest(BaseModel):
    title: str


class TaskUpdate(BaseModel):
    done: bool


@app.get("/health")
def health():
    return {"status": "Jarvis is online"}


@app.get("/history")
def history():
    return get_recent_messages(50)


@app.get("/facts")
def get_facts():
    return list_facts()


@app.post("/facts")
def create_fact(req: FactRequest):
    fact_id = add_fact(req.fact)
    if fact_id is None:
        raise HTTPException(status_code=400, detail="Empty or duplicate fact")
    return {"id": fact_id, "fact": req.fact.strip()}


@app.delete("/facts/{fact_id}")
def remove_fact(fact_id: int):
    if not delete_fact(fact_id):
        raise HTTPException(status_code=404, detail="Fact not found")
    return {"deleted": fact_id}


@app.get("/tasks")
def get_tasks(include_done: bool = False):
    return list_tasks(include_done)


@app.post("/tasks")
def create_task(req: TaskRequest):
    task_id = add_task(req.title)
    if task_id is None:
        raise HTTPException(status_code=400, detail="Empty task")
    return {"id": task_id, "title": req.title.strip(), "done": False}


@app.patch("/tasks/{task_id}")
def update_task(task_id: int, req: TaskUpdate):
    if not set_task_done(task_id, req.done):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"id": task_id, "done": req.done}


@app.delete("/tasks/{task_id}")
def remove_task(task_id: int):
    if not delete_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"deleted": task_id}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    add_message("user", req.message)

    analysis = analyze_message(req.message)
    new_facts = [f for f in analysis["facts"] if add_fact(f)]
    action_note = run_task_action(analysis)

    if analysis["action"] == "list_tasks":
        # Data questions are answered by code, not by the model.
        reply = format_task_list(list_tasks())
    else:
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
    return ChatResponse(reply=reply)