# Jarvis System Documentation
## Major Topic 5: Daily Assistant Tools

**Status:** Complete
**Goal:** Jarvis does useful things, not just chat: tasks, notes, reminders with desktop notifications, a daily briefing with weather, and dashboard panels to see and edit everything.
**Cost:** $0 (the weather service is free for non-commercial use and needs no key)
**Depends on:** Topics 1 to 4

The source of truth for all code is the GitHub repo. This document explains the design, how the pieces fit, and why.

---

## 1. Guiding principle

**Code produces anything that must be exactly right. The model only converses.**

The 7B model proved unreliable at three things: calling tools, reciting data (it invented a task list), and honest confirmations (it claimed to save things it had not). So the model never touches the database, the clock, or the weather. It reads the user's message and fills in a structured form. Our code performs the action and writes the exact reply.

---

## 2. Files

```
C:\Jarvis\
  backend\
    main.py         endpoints only (the doors into Jarvis)
    assistant.py    the brain logic: prompts, message analysis, actions, replies
    database.py     all SQLite code (6 tables)
    reminders.py    time parsing and time formatting
    weather.py      Open-Meteo weather
    briefing.py     builds the daily briefing text
    backup.py       daily database backup (Topic 4)
  shell\
    main.js         windows, tray, backend manager, reminder and briefing checks, message handlers
    preload.js      the safe bridge between pages and main.js
    dashboard.html  chat plus four panels
    sphere.html     the animated sphere
  docs\
    01 to 05        this documentation set
```

New Python package: `dateparser` (installed with `pip install dateparser` in the backend's virtual environment).

---

## 3. Database (SQLite, `jarvis.db`)

| Table | Columns | Purpose |
|---|---|---|
| messages | id, role, content, created_at | Chat history |
| facts | id, fact (unique, case-insensitive), created_at | Long-term memory (Topic 4) |
| tasks | id, title, done (0 or 1), created_at, completed_at | To-do list |
| notes | id, content, created_at | Free-text notes |
| reminders | id, text, due_at, done, created_at | Reminders. `due_at` is local time text `YYYY-MM-DD HH:MM`, so it sorts correctly. `done` means "already fired" |
| settings | key, value | Small flags. Currently `last_briefing_date` |

New tables are created automatically at startup. Existing data is untouched.

---

## 4. API endpoints

| Method | Address | Purpose |
|---|---|---|
| GET | `/health` | Server check |
| GET | `/history` | Last 50 chat messages |
| POST | `/chat` | `{"message": "..."}` returns `{"reply": "..."}` |
| GET, POST, DELETE | `/facts`, `/facts/{id}` | Long-term memory |
| GET, POST | `/tasks` | List (`?include_done=true` for all) and add |
| PATCH, DELETE | `/tasks/{id}` | Mark done or open (`{"done": true}`), delete |
| GET, POST | `/notes` | List (newest first) and add |
| DELETE | `/notes/{id}` | Delete |
| GET, POST | `/reminders` | List upcoming, add (`{"text": "...", "when": "tomorrow at 7 am"}`) |
| DELETE | `/reminders/{id}` | Delete |
| POST | `/reminders/claim` | Return due reminders and mark them fired. Called by the desktop app every 30 seconds |
| GET | `/briefing` | Build a briefing now |
| POST | `/briefing/auto` | Return the briefing only the first time each day, else `{"text": null}` |

Testing in `/docs`: the box takes raw JSON, so quote marks inside a message must be written `\"` or the server returns 422. The dashboard builds the JSON for you, so it has no such problem.

---

## 5. How a chat message flows

```
1. Save the user's message
2. ONE analysis call (structured output, temperature 0) returns:
   facts, action, task_title, task_id, note_text, reminder_text, when_text
3. Save any new facts (Topic 4)
4. Act on the action (our code, never the model)
5. Reply: written by code for most actions; otherwise written by the model
   with a note about what was done
6. Save the reply
```

### Analysis call
- Sees the open tasks (with ids) and the **pending question** (if any), plus the message.
- The prompt is the instructions plus worked examples. Examples are written with a small helper (`_example(...)`) in `assistant.py`, so adding one is a single call.
- Output is forced into a JSON schema. Every field is validated, and a bad answer falls back to "do nothing".
- It sees only the current message, not the conversation.

### Actions

| Action | Meaning | Reply written by |
|---|---|---|
| add_task | User clearly asks to add a task | Model, with a truthful note |
| suggest_task | "I need to...", "I have to..." with no request | Code: asks "Would you like me to add it?" |
| complete_task | User says a listed task is finished | Model, with a truthful note. The id is checked against the open tasks |
| list_tasks | Show tasks | Code (database list) |
| add_note | "Take a note...", "Jot down..." | Model, with a truthful note |
| list_notes | Show notes (latest 10) | Code |
| add_reminder | "Remind me to..." | Code |
| list_reminders | Show reminders (soonest 10) | Code |
| daily_briefing | "Give me my daily briefing" | Code |
| weather | "Will it rain today?" | Code |
| confirm_pending | Yes, to a pending task question | Code |
| give_reminder_time | The user answers a pending "When?" question | Code |
| decline_pending | No, never mind | Code |
| none | Everything else | Model |

### Pending questions (ask first, then act)
When Jarvis asks a question (add this task? when should I remind you?), the system remembers it as `pending`, a small dictionary `{"type": "task" or "reminder", "value": ...}`. It is shown to the analysis call on the **next message only**, so "Yes", "Around 4pm", or "No, never mind" can be understood. Any other message clears it. A reminder time that cannot be understood keeps the question alive so the user can try again. The pending state lives in memory, so a restart clears it.

### Layers that stop false claims
1. Data questions are answered by code from the database.
2. When something was done, the model gets a note saying exactly what. When nothing was done, it gets a note saying so.
3. The system prompt forbids claiming a save, add, or reminder without a note, and forbids the model from asking whether to add a task (the code owns that question).
4. A safety-net pattern (`FALSE_CLAIM`) replaces any model reply that claims it saved, added, or set something when code did nothing.
5. Ids are checked before completing a task. Times are checked before saving a reminder.

---

## 6. Tasks and notes

- Explicit requests ("Add a task to buy rice", "Put \"call the bank\" on my to-do list", "Take a note: ...") act immediately.
- Statements like "I need to buy a cookie" trigger the ask-first question. Time phrases stay in the title ("Finish the report by Friday").
- Open tasks are always included in the model's prompt. Notes are not (there may be many), so the user says "Show me my notes".
- Notes are plain text. Do not store passwords or card numbers in them.

---

## 7. Reminders

- The model only extracts the **reminder text** and the **time phrase as the user said it**. The `dateparser` library turns the phrase into an exact time (`reminders.py`, `parse_when`).
- Accepted examples: "in 10 minutes", "in 2 hours", "tomorrow at 7 am", "at 5 pm", "friday at 3 pm", "october 20 at 10am", "tonight at 8 pm". A small normalizer handles "half an hour", "an hour", "tonight", "next", "this".
- Rejected with a helpful reply: unreadable phrases, date-only phrases such as "tomorrow" (a clock time is needed), and times already in the past.
- No time given: Jarvis asks "When should I remind you about ...?" and remembers the question.
- **Delivery:** the desktop app calls `POST /reminders/claim` every 30 seconds (and once 15 seconds after start). Due reminders are marked fired, a message "Reminder: ..." is added to the chat history, a Windows notification appears (clicking it opens the dashboard), and the sphere pulses for 5 seconds.
- Reminders that came due while the laptop was off fire at the next start.
- Windows notifications need `app.setAppUserModelId(process.execPath)` (set in `main.js`). Focus Assist or Do Not Disturb can hide the toast. The message in the chat history is still added.

---

## 8. Daily briefing and weather

Example output:

```
Good morning! Here is your briefing for Thu, Oct 8.

Weather in Manila: Partly cloudy, 31°C now. Today: high 33°C, low 26°C, 60% chance of rain.

Reminders today:
1. Call mom - 7:00 AM

Open tasks (2):
1. Buy rice
2. Review the Jarvis docs
```

- Greeting depends on the time (morning, afternoon, evening).
- Reminders: today's with clock times. If none, the next upcoming one is shown.
- Tasks: up to 10 shown, with "...and N more".
- **Weather:** Open-Meteo (`api.open-meteo.com/v1/forecast`), free for non-commercial use, no key. Requests current temperature and weather code plus today's high, low, and rain chance. If offline, the briefing still arrives with a line saying the weather is unavailable. The location is four constants at the top of `weather.py` (`LOCATION_NAME`, `LATITUDE`, `LONGITUDE`, `TIMEZONE`), set to Manila.
- **Automatic:** the desktop app calls `POST /briefing/auto` 25 seconds after start and again at 90 seconds. The backend returns the briefing only once per day (setting `last_briefing_date`), saves it to the chat, and the app shows a notification. A briefing requested in chat also counts as today's.
- **Turn off the automatic briefing:** delete the two `setTimeout(checkDailyBriefing, ...)` lines in `shell\main.js`. Chat requests still work.

---

## 9. Dashboard panels

Four tabs share one side panel: **Tasks, Notes, Reminders, Memory**. Clicking a tab opens it, switches views, or closes the panel if it is already active.

| Panel | Shows | Actions |
|---|---|---|
| Tasks | Open tasks, then a "Done" section | Checkbox to complete or reopen, x to delete, add box |
| Notes | Newest first | x to delete, add box |
| Reminders | Text and due time, soonest first | x to delete, two-box add form (what and when). A bad time shows a red message and keeps the text |
| Memory | Long-term facts | x to delete, add box |

- The open panel refreshes after every chat reply and every 15 seconds.
- When the dashboard window is shown again, it rebuilds the chat if the history changed while it was hidden (fired reminders, briefings).
- All text is inserted with `textContent`, never as HTML.

### Message channels added (page to `main.js`)

| Channel | Purpose |
|---|---|
| `tasks:list`, `tasks:add`, `tasks:set-done`, `tasks:delete` | Tasks |
| `notes:list`, `notes:add`, `notes:delete` | Notes |
| `reminders:list`, `reminders:add`, `reminders:delete` | Reminders. `add` returns `{ok}` or `{ok: false, error}` |

Matching functions in `preload.js`: `listTasks`, `addTask`, `setTaskDone`, `deleteTask`, `listNotes`, `addNote`, `deleteNote`, `listReminders`, `addReminder`, `deleteReminder`.

---

## 10. Working method used in this topic

Large multi-file changes were delivered as downloadable files, built and tested before sending (backend logic with the model stubbed out, the dashboard with a simulated backend), instead of long copy-paste blocks. Pattern to install a file:

```
Copy-Item "$env:USERPROFILE\Downloads\<file>" C:\Jarvis\<folder>\<file> -Force
Select-String -Path C:\Jarvis\<folder>\<file> -Pattern "<a word from the new code>" | Select-Object -First 1
```

Any change to `shell` files needs a full app restart (quit from the tray, then `npm start`). Any change to `backend` files needs the backend restarted, which a full app restart also does.

---

## 11. Verification results

| Area | Result |
|---|---|
| Tasks API (add, list, mark done, hide done, empty title 400, delete) | Passed |
| Chat: add task, list tasks, complete task | Passed |
| "I need to..." asks first; yes adds, no does not, unrelated message expires the question | Passed |
| Notes: add, list, newest first | Passed |
| Reminders: relative and absolute times, missing time asks, bad time explains | Passed |
| Reminder fires: Windows notification, sphere pulse, message in history | Passed |
| Reminder time answered in a second message ("Around 4pm") | Passed after the pending-question fix |
| Tasks panel and Notes and Reminders panels | Passed (all manual tests) |
| Daily briefing: automatic once per day, on request, weather line | Passed |
| Message added while dashboard hidden appears when reopened | Passed |

---

## 12. Troubleshooting log

| Problem | Cause | Fix |
|---|---|---|
| 422 error in `/docs` | Quote marks inside the JSON message | Write `\"` in the `/docs` box. The dashboard is not affected |
| "I need to finish the report by Friday" became a task | Model treated a statement as a request | Explicit-request rule, then the ask-first flow |
| Jarvis said "Task updated" but nothing changed | Model copied earlier confirmations from history | Notes saying when nothing was done, then code-written replies |
| Essay-style replies and an invented task list | No length rule, and the model was reciting data | Brevity rule, reply length cap, task and note lists answered by code, cleared chat history |
| Reminder confirmed at "4:00 PM" but not saved | The "When?" question was not remembered, so the model improvised | Pending questions plus the `FALSE_CLAIM` safety net |
| Panel blank or "No handler registered" (Topics 4 and 5) | A handler block was only partly pasted | Verify with `Select-String`, deliver big changes as files |
| Edits to `shell` files had no effect | An old copy was still running (single-instance lock) | Quit from the tray, check Task Manager for leftover `electron.exe`, then `npm start` |
| Notification not shown | Focus Assist or Do Not Disturb | Turn it off. The reminder still appears in the chat |
| Weather says unavailable | No internet, or the service is unreachable | Check the connection and `C:\Jarvis\logs\backend.log`. Ask for the briefing again later |
| A pending "Yes" did nothing | The question expired after an unrelated message | Expected. Repeat the original request |

---

## 13. Known limitations

- **The analysis sees one message.** Follow-ups work only right after Jarvis asks a question. "Add that one too" has no context.
- **Time phrases must be English and fairly standard.** "tomorrow morning" or Filipino phrases are not understood; use a clock time.
- **Reminders** are checked every 30 seconds, only fire while Jarvis is running, and have no repeat or snooze.
- **Tasks have no due dates or priorities.** "By Friday" lives only in the title.
- **Notes** cannot be searched or edited from chat, show the latest 10 in chat (50 in the panel), and are not given to the model.
- **Weather** needs internet, uses a fixed location in `weather.py`, and is free for non-commercial use only.
- **The automatic briefing** can be missed that day if the network is not ready (ask for it in chat). It has no on/off switch in the UI.
- **The safety net can overreach.** A harmless reply containing a phrase like "I'll add" may be replaced. If you see "I haven't saved or set anything" unexpectedly, report the exact message.
- **Pending questions** are held in memory and lost on restart.
- **Latency.** Every message costs one analysis call (about 2k tokens of prompt) and often a second chat call. The analysis prompt grows with each new action, and the model's context is 4096 tokens, so examples must stay lean.
- **Times use the laptop's local clock and timezone.**

---

## 14. Next: Major Topic 6

Proposed: **voice**. Push-to-talk first (speech-to-text with Whisper, running offline), then spoken replies (Piper text-to-speech), using the sphere's existing "listening" and "speaking" states. A wake word and PC control with n8n come after that.


- **Deleting by chat** was added later (see document 06): Jarvis can delete a task, note, or reminder, but always asks yes or no first.