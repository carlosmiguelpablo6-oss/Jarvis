# Jarvis System Documentation
## Major Topic 7: PC Control

**Status:** Complete
**Goal:** Jarvis does things on the computer (open apps, folders, and websites, search the web, find and open files, change the volume, lock the PC, tell the time) by chat or voice, safely.
**Cost:** $0
**Depends on:** Topics 1 to 6 (it builds on the pending-question mechanism and the safety net)

The source of truth for all code is the GitHub repo. This document explains the design and why.

---

## 1. Guiding principle

**The model picks a name. Our code decides what actually runs.**

A language model that controls a PC can do real damage if it misunderstands. So Jarvis can only act from fixed lists in the code. The model never writes a command, a path, or an address that is executed directly. Everything it returns is validated, looked up on an allowed list, and every reply is written by code.

---

## 2. What you can say

| Say | What happens |
|---|---|
| "Open Notepad." | Opens it from the app list |
| "Open my downloads folder." | Opens File Explorer on that folder |
| "Open YouTube." / "Go to example.com" | Opens the site in your default browser |
| "Search the web for cheap flights to Cebu." | Opens a Google search in your browser |
| "Find my resume file." then "2" | Lists up to 5 matching documents. A number opens that one |
| "Turn the volume up." / "Lower it by 20 percent." / "Mute." | Presses the Windows volume keys |
| "What time is it?" / "What is today's date?" | Answered by code from the laptop clock |
| "Lock my computer." then "Yes" | Asks first, then locks |

---

## 3. Files

```
C:\Jarvis\
  pc_config.json        optional: your own apps, folders, sites, search folders
  backend\
    pc.py               everything about PC control
    assistant.py        gets one new action (pc_command) and a few hooks
    deletion.py         (Topic 6) its number reader is reused here
```

No new Python packages are needed.

---

## 4. How a PC request flows

```
Message ---> main analysis (one call, as always)
              action = pc_command ?
                 no  -> normal flow (tasks, notes, reminders, chat...)
                 yes -> second, focused model call (pc.py):
                          returns {command, target, amount}
                        code validates it against the allowed lists
                        code performs it and writes the reply
```

- The main analysis only gained one action (`pc_command`) plus a few examples, so its prompt did not grow much (about 13,400 characters in total).
- The second call has its own small prompt (about 2,000 characters), only runs for PC requests, and adds about a second to those. Everything else is unaffected.
- If the second call fails, nothing is launched and Jarvis lists what he can do.

### Commands the second call can return

`open_app`, `open_folder`, `open_site`, `web_search`, `find_file`, `volume_up`, `volume_down`, `volume_mute`, `lock`, `time`, `unknown`.

---

## 5. Safety rules

| Rule | How it is enforced |
|---|---|
| Only listed apps, folders, and sites are opened | `load_config()` builds the lists. `_lookup()` finds a name by exact match, or by one unambiguous partial match of at least 3 characters |
| The model's text is never run | Only the value from the list is run. A target like "notepad & del *" can only ever run the plain `notepad` entry |
| No shell | Launching uses `os.startfile`, the same as typing into the Windows Run box (Win+R). No command line is built |
| Websites | A listed site, or a plain domain such as `example.org` (checked by a strict pattern). `javascript:`, `file:`, and addresses with paths or parameters are refused |
| Web searches | The words are URL-encoded and limited to 200 characters |
| Files | Only safe types open: pdf, doc, docx, xls, xlsx, ppt, pptx, txt, md, csv, png, jpg, jpeg, gif, webp, mp3, wav, mp4, mkv. Programs and scripts are never listed or opened |
| File location | Only inside the search folders. `pick_file` re-checks that the file is inside them, still exists, and has a safe type, so a forged path is refused |
| Locking | Asks yes or no first (pending type `pc_lock`). The question lives for one message only |
| Not offered at all | Shutdown, restart, closing programs, typing or clicking for you, moving or deleting files |
| Honest replies | Every reply is written by code. A launch failure says "I couldn't open ...". The false-claim safety net also catches the model saying "I've opened ..." or "I'll lock ..." |

---

## 6. The commands in detail

### Apps, folders, and websites
- Names are cleaned first: "the", "my", and trailing words like "app", "folder", "website" are dropped.
- Default apps: Notepad, Calculator, Paint, File Explorer, Task Manager, Snipping Tool, Settings, Chrome, Edge, Firefox, Word, Excel, PowerPoint, VS Code, XAMPP (`C:\xampp\xampp-control.exe`).
- Default folders: Downloads, Documents, Desktop, Pictures, Music, Videos, and `C:\Jarvis`.
- Default sites: YouTube, Google, Gmail, GitHub, Facebook.
- An app or folder that is not on the list gets a reply saying so and where to add it. A folder that does not exist is reported, not opened.

### Finding files
- Searches the search folders (default: Documents, Downloads, Desktop), up to 4 levels deep, for a name containing every word you said (generic words like "file" and "my" are ignored). A word like "pdf" matches the extension too.
- Hidden folders (starting with a dot), `node_modules`, `__pycache__`, `AppData`, and the recycle bin are skipped.
- Gives up after 4 seconds. Shows the 5 newest matches, numbered.
- The next message can be a number ("2", "two", "the first one"). It is read by code (`parse_choice` from `deletion.py`) with no model call. Any other message cancels the choice (pending type `file_choice`).

### Volume
- Sends the Windows media keys (mute, down, up). Each press is about 2 percent.
- Default is 5 presses (about 10 percent). "By 20 percent" means 10 presses. The limit is 25 presses (about 50 percent) per request.
- There is no exact "set to 30 percent". Mute toggles.

### Time and date
Answered by code from the laptop clock. The model never guesses the time.

### Lock
Asks "Lock the computer now? (yes or no)". Yes locks the workstation. No, or any other message, cancels it.

---

## 7. Your own apps, folders, and websites (`C:\Jarvis\pc_config.json`)

Optional. Names are lowercase. **Every backslash in a path must be written twice.**

```json
{
  "apps": {
    "spotify": "C:\\Users\\Asus\\AppData\\Roaming\\Spotify\\Spotify.exe",
    "canva": "https://www.canva.com"
  },
  "folders": { "projects": "C:\\Jarvis" },
  "sites": { "n8n": "http://localhost:5678" },
  "search_folders": [
    "C:\\Users\\Asus\\Documents",
    "C:\\Users\\Asus\\Downloads",
    "C:\\Users\\Asus\\Desktop"
  ]
}
```

- `apps`, `folders`, and `sites` are **added to** the defaults. `search_folders` **replaces** the default list.
- The file is re-read on every request, so no restart is needed.
- A typo in the JSON prints a warning in `C:\Jarvis\logs\backend.log`, and the defaults keep working.
- Only add things you trust, because anything on these lists can be launched by voice or chat.

---

## 8. Pending questions now

| Type | Asked when | Answer |
|---|---|---|
| `task` | "I need to buy a cookie" | Yes or no |
| `reminder` | A reminder with no time | A time |
| `delete` | Delete a task, note, or reminder | Yes or no |
| `delete_choice` | Several items match | A number |
| `file_choice` | A file search finds matches | A number |
| `pc_lock` | Lock the computer | Yes or no |

Each lives for one message only and is held in memory, so a restart clears it.

---

## 9. Context size

The main analysis prompt is about 13,400 characters and both model calls use `NUM_CTX = 6144`. After any change that makes the prompt longer, check `ollama ps` while Jarvis works: PROCESSOR should say 100% GPU. Quick check that `assistant.py` loaded all its pieces:

```
cd C:\Jarvis\backend
python -c "import assistant; print(len(assistant.ANALYSIS_PROMPT))"
```

It should print about 13397.

---

## 10. Verification results

| Area | Result |
|---|---|
| Automated checks with the model and Windows calls simulated (28) | All passed |
| Includes: every command, injection text, blocked web addresses, forged file paths, search skip rules, volume limits, lock flow and expiry, failure of the second call, the safety net, earlier delete and task features | Passed |
| Real tests on the laptop (14): open an app, a folder, a site, a web search, the time, volume up, mute, find a file and open it by number, an app that is not listed, locking with no and with yes, an app added in `pc_config.json` | All passed |

---

## 11. Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| "I don't have X on my app list" | X is not on the lists | Add it in `pc_config.json` |
| "I couldn't open X. Is it installed?" | The path or name is wrong | Check the path in `pc_config.json` (doubled backslashes) |
| The app opened but is not visible | Windows opened it behind the current window | Check the taskbar |
| Added entries are ignored | A typo in the JSON, or the entry is lowercase-sensitive | Look for "pc_config.json problem" in `C:\Jarvis\logs\backend.log`. Use lowercase names |
| "I couldn't find a file matching ..." | The file is outside the search folders, deeper than 4 levels, or an unsafe type | Add the folder to `search_folders`, or use a more exact name |
| Volume changes by the wrong amount | Each key press is about 2 percent | Ask for a percentage, or say it again |
| PC requests answered like normal chat | The analysis did not choose `pc_command` | Rephrase with a clear verb ("Open...", "Find...", "Turn the volume...") |
| Everything slower after adding examples | The analysis prompt grew | Keep examples lean and re-check `ollama ps` |

---

## 12. Known limitations

- **Small action set by design.** Jarvis cannot close or quit programs, shut down or restart, type or click for you, or move, rename, or delete files.
- **One step at a time.** "Open Notepad and then search the web" is not understood as two steps.
- **Filename search only.** It does not read file contents, and only looks in the search folders.
- **No exact volume level**, no per-app volume. Only relative changes and mute.
- **Windows only**, and it opens things in your default browser and apps.
- **The model can pick the wrong command** (for example search instead of open). Every command is low-risk or confirmed, but you may need to rephrase.
- **Two model calls for PC requests**, so they take about a second longer than other requests.
- **The XAMPP path is a guess** (`C:\xampp\xampp-control.exe`). Override it in `pc_config.json` if yours differs.

---

## 13. Next: Major Topic 8

Candidates:
1. **Speak reminders and the briefing aloud**, so notifications are heard too.
2. **A settings page** (voice, hotkey, auto briefing on or off, silence sensitivity) instead of editing code.
3. **Multi-turn follow-ups** ("add that too", "make it 8 am"), so Jarvis understands what you were just talking about.
4. **A wake word** ("Hey Jarvis"), so the hotkey is not needed.