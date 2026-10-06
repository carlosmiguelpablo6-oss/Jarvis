import json

import ollama
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

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
from backup import backup_database

MODEL = "qwen2.5:7b"

SYSTEM_PROMPT = (
    "You are Jarvis, a personal AI assistant running on the user's own laptop. "
    "Be concise, helpful, and calm. Address the user politely. "
    "If you don't know something, say so instead of guessing. "
    "Never invent personal details about the user. If asked about the user's "
    "preferences, history, relationships, or personal life, answer only from your "
    "long-term memory notes or this conversation. If the answer is not there, say you "
    "don't know yet and invite them to tell you. "
    "Long-term memory is handled automatically by the system. "
    "Only say you have remembered or saved something if a note below says you just saved it."
)

FACT_EXTRACTION_PROMPT = """Extract long-term facts about the user from the message.

A long-term fact is something lasting about the user: their name, age, job, location, preferences (favorite things), routines, important people, or goals.
Write each fact as one short sentence starting with "The user".
Do NOT extract questions, requests, small talk, or temporary things.
Never include passwords, API keys, or card or ID numbers.
Reply with JSON only.

Examples:

Message: My name is Maria and I work as a nurse.
{"facts": ["The user's name is Maria.", "The user works as a nurse."]}

Message: I love hiking on weekends.
{"facts": ["The user loves hiking on weekends."]}

Message: What is 12 times 12?
{"facts": []}

Message: Can you open the dashboard for me?
{"facts": []}
"""

FACT_SCHEMA = {
    "type": "object",
    "properties": {"facts": {"type": "array", "items": {"type": "string"}}},
    "required": ["facts"],
}

app = FastAPI(title="Jarvis")

init_db()
backup_database()


def extract_facts(user_message):
    try:
        response = ollama.chat(
            model=MODEL,
            messages=[
                {"role": "system", "content": FACT_EXTRACTION_PROMPT},
                {"role": "user", "content": f"Message: {user_message}"},
            ],
            format=FACT_SCHEMA,
            options={"temperature": 0},
        )
        data = json.loads(response.message.content)
        return [f.strip() for f in data.get("facts", []) if isinstance(f, str) and f.strip()]
    except Exception as err:
        print("Fact extraction failed:", err, flush=True)
        return []


def build_system_prompt(new_facts=None):
    prompt = SYSTEM_PROMPT

    facts = list_facts()
    if facts:
        lines = "\n".join(f"- {f['fact']}" for f in facts)
        prompt += (
            "\n\nThings you know about the user (long-term memory). "
            "Use them naturally when relevant, and never mention that you were given a list:\n"
            + lines
        )

    if new_facts:
        saved = "\n".join(f"- {f}" for f in new_facts)
        prompt += (
            "\n\nYou just saved these new facts to long-term memory "
            "from the user's latest message. Confirm briefly and naturally:\n"
            + saved
        )

    return prompt


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


class FactRequest(BaseModel):
    fact: str


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

class TaskRequest(BaseModel):
    title: str


class TaskUpdate(BaseModel):
    done: bool


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

    new_facts = [f for f in extract_facts(req.message) if add_fact(f)]

    messages = [
        {"role": "system", "content": build_system_prompt(new_facts)}
    ] + get_recent_messages(20)

    response = ollama.chat(model=MODEL, messages=messages)
    reply = response.message.content or "Done."
    add_message("assistant", reply)
    return ChatResponse(reply=reply)