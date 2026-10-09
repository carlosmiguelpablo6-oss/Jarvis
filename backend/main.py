from datetime import date, datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from assistant import handle_message
from backup import backup_database
from briefing import build_daily_briefing
from database import (
    add_fact,
    add_message,
    add_note,
    add_reminder,
    add_task,
    claim_due_reminders,
    delete_fact,
    delete_note,
    delete_reminder,
    delete_task,
    get_recent_messages,
    get_setting,
    init_db,
    list_facts,
    list_notes,
    list_reminders,
    list_tasks,
    set_setting,
    set_task_done,
)
from reminders import parse_when

app = FastAPI(title="Jarvis")

init_db()
backup_database()


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


class NoteRequest(BaseModel):
    content: str


class ReminderRequest(BaseModel):
    text: str
    when: str


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


@app.get("/notes")
def get_notes():
    return list_notes(50)


@app.post("/notes")
def create_note(req: NoteRequest):
    note_id = add_note(req.content)
    if note_id is None:
        raise HTTPException(status_code=400, detail="Empty note")
    return {"id": note_id, "content": req.content.strip()}


@app.delete("/notes/{note_id}")
def remove_note(note_id: int):
    if not delete_note(note_id):
        raise HTTPException(status_code=404, detail="Note not found")
    return {"deleted": note_id}


@app.get("/reminders")
def get_reminders():
    return list_reminders(50)


@app.post("/reminders")
def create_reminder_endpoint(req: ReminderRequest):
    due, error = parse_when(req.when)
    if error:
        raise HTTPException(status_code=400, detail=error)
    due_at = due.strftime("%Y-%m-%d %H:%M")
    reminder_id = add_reminder(req.text, due_at)
    if reminder_id is None:
        raise HTTPException(status_code=400, detail="Empty reminder")
    return {"id": reminder_id, "text": req.text.strip(), "due_at": due_at}


@app.delete("/reminders/{reminder_id}")
def remove_reminder(reminder_id: int):
    if not delete_reminder(reminder_id):
        raise HTTPException(status_code=404, detail="Reminder not found")
    return {"deleted": reminder_id}


@app.post("/reminders/claim")
def claim_reminders():
    """Called by the desktop app every 30 seconds. Returns reminders that are due
    (including ones missed while the laptop was off) and marks them as fired."""
    now_text = datetime.now().strftime("%Y-%m-%d %H:%M")
    due = claim_due_reminders(now_text)
    for r in due:
        add_message("assistant", f"Reminder: {r['text']}")
    return due


@app.get("/briefing")
def get_briefing():
    return {"text": build_daily_briefing()}


@app.post("/briefing/auto")
def auto_briefing():
    """Called by the desktop app after startup. Returns the briefing only the first
    time each day (and saves it to the chat history). Otherwise returns text: null."""
    today = date.today().isoformat()
    if get_setting("last_briefing_date") == today:
        return {"text": None}
    text = build_daily_briefing()
    add_message("assistant", text)
    set_setting("last_briefing_date", today)
    return {"text": text}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    return ChatResponse(reply=handle_message(req.message))