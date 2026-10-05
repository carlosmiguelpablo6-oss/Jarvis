# Jarvis System Documentation
## Major Topic 3: The Sphere, the Dashboard, and Auto-Start

**Status:** Complete
**Goal:** Jarvis appears on its own after Windows login as a floating sphere. Clicking the sphere opens a dashboard with chat. The whole system runs as one program and can be quit from a tray icon.
**Cost:** $0
**Depends on:** Major Topic 1 (Local Brain Setup), Major Topic 2 (Backend and Permanent Memory)

The source of truth for all code is the GitHub repo (`C:\Jarvis\shell`). This document explains how the pieces fit together and why.

---

## 1. Components added

| Item | Version | Purpose |
|---|---|---|
| Node.js | v24.18.0 | Runs Electron's tooling |
| npm | 11.16.0 | Package installer for the shell |
| Electron | dev dependency | Builds the desktop app (sphere and dashboard) from HTML, CSS, JavaScript |

---

## 2. Folder structure

```
C:\Jarvis\
  .gitignore                (includes logs/ since Task 3.6)
  backend\                  (Topic 2: FastAPI and SQLite)
  shell\
    main.js                 (app brain: windows, tray, backend manager, IPC)
    preload.js              (safe bridge between pages and main.js)
    sphere.html             (the animated sphere)
    dashboard.html          (the chat window)
    icon.png                (tray icon)
    package.json
    package-lock.json
    node_modules\           (ignored by Git)
  logs\
    backend.log             (backend output, ignored by Git)
  docs\
    01-local-brain-setup.md
    02-backend-and-memory.md
    03-sphere-and-dashboard.md   (this file)
```

---

## 3. Architecture

```
Dashboard page --> preload bridge --> main.js --> FastAPI /chat --> Ollama
                                         |
                                         +--> tells the sphere: thinking / speaking / idle

Windows login --> Startup shortcut --> electron.exe --> main.js --> starts backend (hidden)
```

Design decisions:
- **Pages never call the backend directly.** `main.js` makes the requests. This keeps the backend closed to web pages, avoids browser CORS problems, and lets `main.js` control the sphere at the same time.
- **Preload bridge.** Pages are sandboxed and cannot control the computer. `preload.js` exposes only a few approved functions as `window.jarvis`. Pages call them and `main.js` does the real work (this messaging is called IPC).
- **One program.** Electron starts and stops the backend, so nothing is started by hand.

---

## 4. The sphere (`sphere.html`)

A 140x140 pixel transparent window with an 80 pixel sphere inside (the extra space holds the glow).

Window options in `main.js`: `frame: false` (no borders), `transparent: true`, `hasShadow: false`, `skipTaskbar: true`, `alwaysOnTop: true`, `resizable: false`. Placed 24 pixels from the bottom-right corner of the primary display's work area.

**States.** The state is one attribute, `data-state`, on the orb. CSS variables (`--glow` for color, `--breathe` for speed) are redefined per state.

| State | Look | When it is used |
|---|---|---|
| idle | Slow blue breathing | Default |
| listening | Green-teal with ripples | Reserved for voice input (later topic) |
| thinking | Purple, spinning ring, faster breathing | While the model is answering |
| speaking | Bright blue, fast pulsing | For 2 seconds after a reply arrives (placeholder until real voice) |

`window.setOrbState(state)` changes the look. `main.js` calls it through the `orb:state` event.

**Click vs drag.** Pointer events with pointer capture. If the mouse moves less than 5 pixels between press and release, it is a click and the dashboard opens. Otherwise it is a drag and the window follows the mouse using `setBounds` with a fixed size (`setPosition` can stretch windows on Windows with display scaling).

---

## 5. The dashboard (`dashboard.html`)

- Header, scrolling message area, input bar (Enter sends, Shift+Enter adds a line).
- Messages are built with `textContent`, so message text is never treated as HTML.
- Input is locked while Jarvis answers, with a "thinking" line.
- On load it fetches `/history` through `main.js` and shows saved messages.
- Closing the window (X) **hides** it instead of destroying it, so it reopens instantly. The `isQuitting` flag lets the app still exit.

---

## 6. IPC channels (page and `main.js`)

| Channel | Direction | Purpose |
|---|---|---|
| `dashboard:open` | page to main | Open or focus the dashboard |
| `sphere:get-position` | page to main (request and reply) | Get the sphere window position |
| `sphere:move` | page to main | Move the sphere window |
| `chat:send` | page to main (request and reply) | Send a message, get `{ok, reply}` or `{ok:false, error}` |
| `chat:history` | page to main (request and reply) | Fetch saved messages |
| `orb:state` | main to sphere | Change the sphere state |

Functions exposed to pages as `window.jarvis`: `openDashboard`, `getSpherePosition`, `moveSphere`, `onOrbState`, `sendChat`, `getHistory`.

---

## 7. Backend lifecycle (`main.js`)

- **Start:** runs `python -m uvicorn main:app --host 127.0.0.1 --port 8000` using `C:\Jarvis\backend\.venv\Scripts\python.exe`, hidden (`windowsHide: true`). Output goes to `C:\Jarvis\logs\backend.log`.
- **Stop:** `taskkill /pid <pid> /T /F` on quit. `/T` is required because on Windows a virtual environment's `python.exe` launches the real Python as a child process, so a plain kill would leave the server running.
- **Single instance:** `requestSingleInstanceLock()`. A second launch exits immediately and the first copy opens its dashboard.
- **Tray icon:** left-click opens the dashboard. Right-click menu: Open Dashboard, Quit Jarvis. Quit triggers `before-quit`, which stops the backend.

---

## 8. Auto-start at login

A shortcut in the Windows Startup folder runs Electron on the shell project (equivalent to `npm start`). Electron then starts the backend.

Setup (PowerShell):
```
$startup = [Environment]::GetFolderPath("Startup")
$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut("$startup\Jarvis.lnk")
$shortcut.TargetPath = "C:\Jarvis\shell\node_modules\electron\dist\electron.exe"
$shortcut.Arguments = '"C:\Jarvis\shell"'
$shortcut.WorkingDirectory = "C:\Jarvis\shell"
$shortcut.Description = "Jarvis AI assistant"
$shortcut.Save()
```

Prerequisite check: `Test-Path C:\Jarvis\shell\node_modules\electron\dist\electron.exe` must print `True`.

To undo: delete `Jarvis.lnk` from the Startup folder (`explorer shell:startup`) or disable it in Task Manager, Startup apps.

The shortcut lives in the Windows profile, not in the repo, so it must be recreated on a new machine.

---

## 9. Day-to-day commands

| Task | How |
|---|---|
| Normal use | Do nothing. Jarvis starts at login |
| Development run | `cd C:\Jarvis\shell` then `npm start` (quit any running copy first) |
| Quit Jarvis | Tray icon, right-click, Quit Jarvis |
| Check backend log | Open `C:\Jarvis\logs\backend.log` |
| Check backend is up | Browse to `http://127.0.0.1:8000/health` |
| Reset Jarvis's memory | Quit Jarvis, delete `C:\Jarvis\backend\jarvis.db` |

Do not run a manual `uvicorn` while the app is running. Both would use port 8000.

---

## 10. Verification results

| Test | Result |
|---|---|
| Transparent always-on-top sphere | Works |
| Four sphere states | All distinct |
| Click opens dashboard, close and reopen | Works |
| Drag moves sphere without opening dashboard, size stays fixed | Works |
| Dashboard chat, history loads, memory continues | Works |
| Sphere shows thinking then speaking then idle | Works |
| Error shown when backend is down | "Can't reach the Jarvis server. Is it running?" |
| Electron starts backend by itself | Works, uvicorn lines in `backend.log` |
| Tray icon opens dashboard, Quit Jarvis | Works |
| Quit stops the backend | `/health` fails to load afterward |
| Second launch | No second sphere |
| Sign out and sign in | Jarvis starts automatically |

---

## 11. Troubleshooting log

| Problem | Cause | Fix |
|---|---|---|
| `Unable to move the cache` and `Gpu Cache Creation failed` when launching a second copy | Second copy tries to use the cache folder held by the first, then exits because of the single-instance lock | Harmless, no action needed |
| Jarvis forgets the user's name after many messages | Only the last 20 messages are sent to the model | Expected. Fixed by long-term memory (Major Topic 4) |
| Jarvis forgets everything after deleting `jarvis.db` | All memory lives in that file | Expected. Only delete for a full reset |
| Chat says server unreachable right after launch | Backend still starting (about 10 seconds) | Wait and retry; check `backend.log` if it persists |

---

## 12. Known limitations

- **Backend start delay.** Takes about 10 seconds after launch. The app does not wait for or retry the connection, and the dashboard history may be empty if opened too early.
- **Speaking pulse is a placeholder.** It lasts a fixed 2 seconds. Real speaking and listening states arrive with voice.
- **Replies are not streamed.** The full answer appears at once. The model call is not streamed to the dashboard yet.
- **Log file grows forever.** `backend.log` has no rotation.
- **Hard-coded paths.** Everything assumes the project lives in `C:\Jarvis`.
- **Sphere position is not remembered.** It returns to the bottom-right corner of the primary display on each launch.
- **Short-term memory only.** The model sees the last 20 messages. Durable facts are not stored separately yet.
- **No backup of `jarvis.db`.** It is private and ignored by Git, so deleting it is permanent.

---

## 13. Next: Major Topic 4

Long-term memory: a separate store of durable facts (name, preferences, routines) that is always included in the model's context no matter how long ago it was said, plus a database backup option.
