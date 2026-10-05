import ollama
from fastapi import FastAPI
from pydantic import BaseModel

MODEL = "qwen2.5:7b"

SYSTEM_PROMPT = (
    "You are Jarvis, a personal AI assistant running on the user's own laptop. "
    "Be concise, helpful, and calm. Address the user politely. "
    "If you don't know something, say so instead of guessing."
)

app = FastAPI(title="Jarvis")

history = [{"role": "system", "content": SYSTEM_PROMPT}]


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


@app.get("/health")
def health():
    return {"status": "Jarvis is online"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    history.append({"role": "user", "content": req.message})
    response = ollama.chat(model=MODEL, messages=history)
    reply = response.message.content
    history.append({"role": "assistant", "content": reply})
    return ChatResponse(reply=reply)