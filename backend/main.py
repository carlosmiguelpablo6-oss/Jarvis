import ollama
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from database import (
    add_fact,
    add_message,
    delete_fact,
    get_recent_messages,
    init_db,
    list_facts,
)

MODEL = "qwen2.5:7b"

SYSTEM_PROMPT = (
    "You are Jarvis, a personal AI assistant running on the user's own laptop. "
    "Be concise, helpful, and calm. Address the user politely. "
    "If you don't know something, say so instead of guessing."
)

app = FastAPI(title="Jarvis")

init_db()

def build_system_prompt():
    facts = list_facts()
    if not facts:
        return SYSTEM_PROMPT
    lines = "\n".join(f"- {f['fact']}" for f in facts)
    return (
        SYSTEM_PROMPT
        + "\n\nThings you know about the user (long-term memory). "
        + "Use them naturally when relevant, and never mention that you were given a list:\n"
        + lines
    )

class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


@app.get("/health")
def health():
    return {"status": "Jarvis is online"}


@app.get("/history")
def history():
    return get_recent_messages(50)

class FactRequest(BaseModel):
    fact: str


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


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    add_message("user", req.message)
    messages = [{"role": "system", "content": build_system_prompt()}] + get_recent_messages(20)
    response = ollama.chat(model=MODEL, messages=messages)
    reply = response.message.content
    add_message("assistant", reply)
    return ChatResponse(reply=reply)