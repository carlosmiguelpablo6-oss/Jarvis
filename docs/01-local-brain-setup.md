# Jarvis System Documentation
## Major Topic 1: Local Brain Setup

**Status:** Complete
**Goal:** Run an AI model fully offline on the laptop and talk to it from Python, with a personality and in-session memory.
**Cost:** $0 (all software is free or open-source)

---

## 1. Environment

| Item | Value |
|---|---|
| Machine | ASUS ROG Strix G18 |
| OS | Windows 11 |
| GPU | RTX 4070 (8 GB VRAM) |
| RAM | 16 GB |
| Python | 3.12.10 (default `python`); 3.14.7 also installed, not used |
| Ollama | 0.35.1 |
| Model | `qwen2.5:7b` (about 5.1 GB loaded, 100% GPU) |
| Python library | `ollama` (installed in the project virtual environment) |

---

## 2. Components and why they exist

- **Python 3.12:** runs the Jarvis backend. 3.12 was chosen over 3.14 because the voice and AI libraries planned for later (Whisper, wake word) support it more reliably.
- **Ollama:** the engine that runs the model locally. It starts automatically with Windows and listens on `http://localhost:11434`. It unloads the model from VRAM after about 5 minutes idle, freeing the GPU.
- **qwen2.5:7b:** the offline "brain". Fits in 8 GB VRAM, follows instructions well, and supports tool use (needed in later topics).
- **Virtual environment (`.venv`):** an isolated set of Python packages for Jarvis only, so it never conflicts with other projects.

---

## 3. Folder structure

```
C:\Jarvis\
  backend\
    .venv\            (virtual environment, do not edit)
    test_chat.py      (Task 1.4: one-shot connection test)
    jarvis_chat.py    (Task 1.5: chat with personality and memory)
  docs\
    01-local-brain-setup.md   (this file)
```

---

## 4. Setup procedure (to rebuild from scratch)

1. Install Python 3.12 (64-bit). Install the 3.12 build alongside any newer version; leave "Add to PATH" ticked only if it should be the default `python`.
2. Install Ollama from ollama.com/download. Confirm with `ollama --version` and by opening `http://localhost:11434` (shows "Ollama is running").
3. Download the model: `ollama pull qwen2.5:7b`
4. Test it: `ollama run qwen2.5:7b`, then `ollama ps` and confirm PROCESSOR shows **100% GPU**.
5. Create the project:
   ```
   mkdir C:\Jarvis\backend
   cd C:\Jarvis\backend
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install ollama
   ```
6. Create `test_chat.py` and `jarvis_chat.py` (see section 5).

---

## 5. Code reference

### test_chat.py
Sends one message to the model and prints the reply. Purpose: prove Python can reach Ollama.

```python
import ollama

response = ollama.chat(
    model="qwen2.5:7b",
    messages=[{"role": "user", "content": "Say hello in one sentence."}],
)

print(response.message.content)
```

### jarvis_chat.py
A terminal chat with a personality and conversation memory.

```python
import ollama

MODEL = "qwen2.5:7b"

SYSTEM_PROMPT = (
    "You are Jarvis, a personal AI assistant running on the user's own laptop. "
    "Be concise, helpful, and calm. Address the user politely. "
    "If you don't know something, say so instead of guessing."
)

history = [{"role": "system", "content": SYSTEM_PROMPT}]

print("Jarvis online. Type 'exit' to quit.\n")

while True:
    user_input = input("You: ").strip()
    if not user_input:
        continue
    if user_input.lower() in ("exit", "quit"):
        print("Jarvis: Goodbye.")
        break

    history.append({"role": "user", "content": user_input})

    print("Jarvis: ", end="", flush=True)
    reply = ""
    for chunk in ollama.chat(model=MODEL, messages=history, stream=True):
        piece = chunk.message.content
        print(piece, end="", flush=True)
        reply += piece
    print("\n")

    history.append({"role": "assistant", "content": reply})
```

**Key concepts**

| Concept | Meaning |
|---|---|
| Roles | `system` = hidden instructions, `user` = your message, `assistant` = the model's reply |
| System prompt | Defines Jarvis's identity and manners. Edit `SYSTEM_PROMPT` to change his personality |
| History list | The model has no memory by itself. We resend the whole conversation each turn so it can "remember" |
| Streaming | `stream=True` returns the reply in small pieces so text appears as it is generated |

---

## 6. Verification results

| Test | Result |
|---|---|
| `ollama --version` | 0.35.1 |
| Browser check at `localhost:11434` | "Ollama is running" |
| `ollama ps` | qwen2.5:7b, 5.1 GB, 100% GPU, context 4096 |
| `test_chat.py` | Returned a one-sentence greeting |
| `jarvis_chat.py` memory test | Correctly recalled the user's name and job in a later message |

---

## 7. Known limitations

- **Memory is temporary.** Conversation history lives only while the script runs. Closing it erases it. Permanent memory is planned for Major Topic 2 (SQLite).
- **Terminal only.** No interface yet. The dashboard and sphere come in a later topic.
- **Context window is 4096 tokens** by default. Very long conversations will exceed it and lose the oldest content. We will revisit this when we build memory.

---

## 8. Troubleshooting log

| Problem | Cause | Fix |
|---|---|---|
| `python --version` showed 3.14 | Newest version was installed by default | Installed Python 3.12 alongside; `python` now points to 3.12.10 |
| `Activate.ps1` blocked ("running scripts is disabled") | Windows blocks PowerShell scripts by default | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, answer `Y` |
| `ollama` not recognized | PATH not refreshed in the old window | Close PowerShell and open a new window |

---

## 9. Next: Major Topic 2

FastAPI backend and SQLite memory: turn the terminal chat into a background service with a `/chat` endpoint and permanent memory.
