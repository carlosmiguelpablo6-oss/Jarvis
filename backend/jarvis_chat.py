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