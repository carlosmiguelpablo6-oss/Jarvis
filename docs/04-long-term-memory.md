# Jarvis System Documentation
## Major Topic 4: Long-Term Memory

**Status:** Complete
**Goal:** Jarvis remembers durable facts about the user (name, preferences, routines) no matter how long ago they were said, saves them automatically from conversation, lets the user see and edit them, and protects them with backups.
**Cost:** $0
**Depends on:** Topics 1 to 3

The source of truth for all code is the GitHub repo. This document explains the design and why it was built this way.

---

## 1. Two kinds of memory

| Memory | Holds | Mechanism | Limit |
|---|---|---|---|
| Short-term | Recent conversation | Last 20 messages from the `messages` table, sent with every call | Older messages scroll out of view of the model |
| Long-term | Durable facts | `facts` table, **all** facts added to the system prompt on every call | Each fact uses part of the 4096-token context window, so facts must stay short |

---

## 2. Files added or changed

```
C:\Jarvis\
  backend\
    main.py         (extraction pass, system prompt builder, /facts endpoints)
    database.py     (facts table and functions)
    backup.py       (NEW: daily backup)
  backups\          (NEW: created automatically, ignored by Git)
    jarvis-YYYY-MM-DD.db
  shell\
    main.js         (facts:list, facts:add, facts:delete handlers)
    preload.js      (listFacts, addFact, deleteFact)
    dashboard.html  (Memory panel)
  docs\
    04-long-term-memory.md   (this file)
```

---

## 3. Database: facts table

| Column | Type | Notes |
|---|---|---|
| id | INTEGER, auto-increment | Used for deletion |
| fact | TEXT, UNIQUE, case-insensitive | The database itself refuses duplicates, ignoring capitalization |
| created_at | TEXT | Timestamp |

Functions in `database.py`:
- `add_fact(fact)`: returns the new id, or `None` if the fact is empty or a duplicate (`INSERT OR IGNORE`).
- `list_facts()`: all facts, oldest first.
- `delete_fact(fact_id)`: returns `True` if a row was deleted.

---

## 4. API endpoints added

| Method | Address | Purpose |
|---|---|---|
| GET | `/facts` | List all facts |
| POST | `/facts` | Add a fact (`{"fact": "..."}`), returns 400 if empty or duplicate |
| DELETE | `/facts/{id}` | Remove a fact, returns 404 if it does not exist |

---

## 5. How a chat message flows now

```
1. Save the user's message to the messages table
2. extract_facts(message): a separate, focused model call returns JSON
   {"facts": [...]} (usually empty)
3. Save any new facts (duplicates are skipped)
4. build_system_prompt(new_facts): personality text
   + all stored facts
   + a note listing facts just saved, so the confirmation is truthful
5. Chat call: system prompt + last 20 messages
6. Save the reply and return it
```

### Fact extraction (`extract_facts`)
- Uses `format=FACT_SCHEMA` (structured output) so the model must return `{"facts": [string, ...]}`.
- `temperature: 0` for consistent results.
- The prompt contains **four worked examples** (two with facts, two without). Examples made the difference. A rules-only prompt made the 7B model return an empty list for everything.
- The user's text is wrapped as `Message: ...` to match the examples.
- Any failure is logged and returns an empty list, so a failed extraction never breaks the chat.
- Cost: one extra quick model call per message, roughly 1 to 2 seconds on the RTX 4070.

### System prompt rules
- Memory is automatic. Jarvis may only say he saved something if the note says he just did.
- Jarvis must never invent personal details. If the answer is not in the long-term notes or the conversation, he says he does not know yet and invites the user to tell him.

---

## 6. Why not tool calling?

The first design gave the model a `remember_fact` tool and let it decide when to call it. With `qwen2.5:7b` this failed: the model replied "Remembered: ..." as plain text with `tool_calls: None`, a fake save. Stronger instructions did not fix it, and chat history containing earlier fake confirmations reinforced the habit.

The extraction pass is more reliable for this model because the model has one narrow job and the output shape is forced. Our code, not the model, decides what gets saved. Tool calling can be revisited later (for example with a larger model or a different routing method).

---

## 7. Memory panel (dashboard)

- Opened with the **Memory** button (top right). Shows "What Jarvis remembers" and "Stored only on this laptop."
- Lists every fact with an **x** button to delete it.
- Add box at the bottom (Enter or the Add button). A lock prevents double submits. If the backend refuses a fact (duplicate or empty), the box shows "Already remembered (or empty)."
- Refreshes automatically after each chat reply while open, so new facts appear live.
- All text is inserted with `textContent`, never as HTML.

IPC channels added:

| Channel | Purpose |
|---|---|
| `facts:list` | Fetch all facts |
| `facts:add` | Add a fact (checked to be non-empty text) |
| `facts:delete` | Delete by id (checked to be a whole number) |

Exposed to the page as `window.jarvis.listFacts`, `addFact`, `deleteFact`.

---

## 8. Backups (`backup.py`)

- Runs at every backend start, after `init_db()`.
- Creates **one backup per day**: `C:\Jarvis\backups\jarvis-YYYY-MM-DD.db`.
- Keeps the **newest 7**, deletes older ones.
- Uses SQLite's built-in backup function, which gives a consistent copy even while the database is in use.
- **Skips empty databases**, so resetting Jarvis cannot push good backups out.
- A failed backup is logged and never stops Jarvis.
- A backup holds the state as of the day's first start, so the worst case is losing about one day of new memories.
- Backups are private. `*.db` in `.gitignore` keeps them out of Git.

### Restore procedure
1. Quit Jarvis (tray icon, Quit Jarvis).
2. `dir C:\Jarvis\backups` to see the file names.
3. `Copy-Item C:\Jarvis\backups\jarvis-YYYY-MM-DD.db C:\Jarvis\backend\jarvis.db -Force` (use the real date).
4. Start Jarvis. Check the Memory panel.

The restore was rehearsed: a test fact added after the backup disappeared after restoring, proving the procedure works.

---

## 9. Verification results

| Test | Result |
|---|---|
| Add, list, duplicate rejected (400), delete via `/docs` | Passed |
| Fact added by hand appears in the model's answer | Passed (name and favorite color) |
| Extraction: "My favorite drink is calamansi juice." | Fact saved |
| Extraction: question ("What is 12 times 12?") | No fact saved |
| Extraction: "Please remember that I wake up at 6 AM." | Fact saved |
| Memory panel: list, add, duplicate feedback, delete, live refresh | Passed |
| Unknown personal detail ("What is my favourite animal?") | Says it does not know yet |
| Daily backup file created at startup | Passed |
| Restore from backup | Passed |

---

## 10. Troubleshooting log

| Problem | Cause | Fix |
|---|---|---|
| `NameError: name 'TOOLS' is not defined` | Tool code was indented inside `build_system_prompt`, making it local | Module-level code must start at the left margin (resolved by removing tools, see section 6) |
| Jarvis said "Remembered" but nothing saved | 7B model skipped the tool call and faked the confirmation | Switched to the extraction pass |
| Extraction returned `[]` for a clear fact | Rules-only prompt made the model overly cautious | Added worked examples to the prompt |
| Replies identical to old version after editing | Server on port 8000 was stale | Fully restart (quit from tray, stop manual `uvicorn`, start again) |
| Memory panel blank, console said "No handler registered for 'facts:list'" | The `facts:list` block was missing from `main.js` after a partial paste | Add the handler, then fully restart |
| `POST /facts` returned 400 from the panel | Duplicate request (double submit) | Added a submit lock and a "Already remembered" message |
| Jarvis invented "favorite animals" | Soft instructions, plus old fake "Remembered:" replies in history | Stricter prompt, optional history clear (`DELETE FROM messages`, facts untouched) |
| Edits to `main.js` had no effect | Single-instance lock: an old copy kept running | Quit from the tray (check Task Manager for leftover `electron.exe`), then `npm start` |

Reminder: any change to `shell` files needs a full app restart. Any change to `backend` files needs the backend restarted, which a full app restart also does.

---

## 11. Known limitations

- **Context cost.** Every fact is sent with every message and shares the 4096-token window. Very long fact lists will crowd out conversation. A later improvement is to send only relevant facts.
- **Extra latency.** About 1 to 2 seconds per message for extraction.
- **Wording drift.** The same information may be saved with different wording ("favorite drink is X" versus "likes X"). Delete near-duplicates in the Memory panel.
- **No fact editing.** To change a fact, delete it and add a new one.
- **Extraction reads the user's message only**, not Jarvis's replies.
- **A 7B model can still slip.** It may occasionally invent a detail or save something borderline. The Memory panel is the check.
- **Backups share the disk** with the original. Copy `C:\Jarvis\backups` to a USB drive or trusted cloud storage occasionally to survive a laptop failure.
- **Reset behavior.** Deleting `jarvis.db` wipes everything (restore from `backups` if needed).

---

## 12. Next: Major Topic 5

Daily assistant tools: reminders, tasks, notes, and a daily briefing. Because tool calling proved unreliable with this model, the plan is to route requests in a way suited to a 7B model (focused, structured model calls with our code deciding the action), the same approach that fixed fact saving.
