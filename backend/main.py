import ollama
from fastapi import FastAPI
from pydantic import BaseModel

from database import add_message, get_recent_messages, init_db

MODEL = "qwen2.5:7b"

SYSTEM_PROMPT = (
    "You are Jarvis, a personal AI assistant running on the user's own laptop. "
    "Be concise, helpful, and calm. Address the user politely. "
    "If you don't know something, say so instead of guessing."
)

app = FastAPI(title="Jarvis")

init_db()


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


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    add_message("user", req.message)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + get_recent_messages(20)
    response = ollama.chat(model=MODEL, messages=messages)
    reply = response.message.content
    add_message("assistant", reply)
    return ChatResponse(reply=reply)