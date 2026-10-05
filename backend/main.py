from fastapi import FastAPI

app = FastAPI(title="Jarvis")


@app.get("/health")
def health():
    return {"status": "Jarvis is online"}