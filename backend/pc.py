import ctypes
import json
import os
import re
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

import ollama

from deletion import parse_choice

# Optional file where you add your own apps, folders, and websites (see the documentation).
CONFIG_PATH = Path(__file__).parent.parent / "pc_config.json"
HOME = Path.home()

# Jarvis can only open what is on these lists. The model never supplies a command or a path.
DEFAULT_APPS = {
    "notepad": "notepad",
    "calculator": "calc",
    "paint": "mspaint",
    "file explorer": "explorer",
    "task manager": "taskmgr",
    "snipping tool": "snippingtool",
    "settings": "ms-settings:",
    "chrome": "chrome",
    "edge": "msedge",
    "firefox": "firefox",
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
    "vs code": "code",
    "xampp": r"C:\xampp\xampp-control.exe",
}
DEFAULT_FOLDERS = {
    "downloads": str(HOME / "Downloads"),
    "documents": str(HOME / "Documents"),
    "desktop": str(HOME / "Desktop"),
    "pictures": str(HOME / "Pictures"),
    "music": str(HOME / "Music"),
    "videos": str(HOME / "Videos"),
    "jarvis": str(Path(__file__).parent.parent),
}
DEFAULT_SITES = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
    "facebook": "https://www.facebook.com",
}
DEFAULT_SEARCH_FOLDERS = [
    str(HOME / "Documents"),
    str(HOME / "Downloads"),
    str(HOME / "Desktop"),
]

# Only these file types can be opened. Programs and scripts are never opened.
SAFE_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".md", ".csv",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp3", ".wav", ".mp4", ".mkv",
}
SKIP_DIRS = {"node_modules", "__pycache__", "appdata", "$recycle.bin"}
MAX_DEPTH = 4
MAX_RESULTS = 5
SEARCH_SECONDS = 4.0
GENERIC_FILE_WORDS = {"file", "files", "my", "the", "a", "an", "named", "called", "for"}

KEY_VOLUME_MUTE, KEY_VOLUME_DOWN, KEY_VOLUME_UP = 0xAD, 0xAE, 0xAF
DEFAULT_VOLUME_STEPS = 5  # each key press is about 2 percent

HELP_TEXT = (
    "I can open apps, folders, and websites, search the web, find files, change the "
    "volume, lock the PC, and tell the time. Try: Open Notepad."
)

PC_COMMANDS = (
    "open_app", "open_folder", "open_site", "web_search", "find_file",
    "volume_up", "volume_down", "volume_mute", "lock", "time", "unknown",
)

PC_PROMPT = """You read one message from the user asking Jarvis to do something on the computer. Return JSON with:
- command, one of: open_app, open_folder, open_site, web_search, find_file, volume_up, volume_down, volume_mute, lock, time, unknown.
- target: for open_app the app name, for open_folder the folder name, for open_site the website name or domain, for web_search the search words, for find_file the words in the file name. Otherwise an empty string.
- amount: for volume_up and volume_down, the percent if the user gave one. Otherwise 0.
Use unknown if the request does not fit. Reply with JSON only.

Examples:
"""


def _pc_example(message, command, target="", amount=0):
    result = {"command": command, "target": target, "amount": amount}
    return f"Message: {message}\n{json.dumps(result)}"


PC_PROMPT += "\n\n".join(
    [
        _pc_example("Open Notepad.", "open_app", "notepad"),
        _pc_example("Launch Chrome please.", "open_app", "chrome"),
        _pc_example("Open my downloads folder.", "open_folder", "downloads"),
        _pc_example("Open YouTube.", "open_site", "youtube"),
        _pc_example("Go to github.com", "open_site", "github.com"),
        _pc_example("Search the web for cheap flights to Cebu.", "web_search", "cheap flights to Cebu"),
        _pc_example("Google how to center a div.", "web_search", "how to center a div"),
        _pc_example("Find my resume file.", "find_file", "resume"),
        _pc_example("Look for the invoice pdf.", "find_file", "invoice pdf"),
        _pc_example("Turn the volume up.", "volume_up"),
        _pc_example("Lower the volume by 20 percent.", "volume_down", "", 20),
        _pc_example("Mute the sound.", "volume_mute"),
        _pc_example("Lock my computer.", "lock"),
        _pc_example("What time is it?", "time"),
        _pc_example("What is today's date?", "time"),
        _pc_example("Do the thing with the stuff.", "unknown"),
    ]
)

PC_SCHEMA = {
    "type": "object",
    "properties": {
        "command": {"type": "string", "enum": list(PC_COMMANDS)},
        "target": {"type": "string"},
        "amount": {"type": "integer"},
    },
    "required": ["command", "target", "amount"],
}


# ---------- things that touch Windows (kept tiny so they are easy to replace in tests) ----------
def open_target(target):
    """Same as typing it into the Windows Run box (Win+R)."""
    os.startfile(target)


def press_key(virtual_key, times=1):
    user32 = ctypes.windll.user32
    for _ in range(times):
        user32.keybd_event(virtual_key, 0, 0, 0)  # key down
        user32.keybd_event(virtual_key, 0, 2, 0)  # key up
        time.sleep(0.01)


def lock_workstation():
    ctypes.windll.user32.LockWorkStation()


# ---------- configuration ----------
def load_config():
    config = {
        "apps": dict(DEFAULT_APPS),
        "folders": dict(DEFAULT_FOLDERS),
        "sites": dict(DEFAULT_SITES),
        "search_folders": list(DEFAULT_SEARCH_FOLDERS),
    }
    try:
        if CONFIG_PATH.exists():
            user = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            for key in ("apps", "folders", "sites"):
                if isinstance(user.get(key), dict):
                    config[key].update({str(k).lower(): str(v) for k, v in user[key].items()})
            if isinstance(user.get("search_folders"), list):
                config["search_folders"] = [str(p) for p in user["search_folders"]]
    except Exception as err:
        print("pc_config.json problem:", err, flush=True)
    return config


def _lookup(table, name):
    """Find a name on a list: exact, or one unambiguous partial match."""
    name = (name or "").lower().strip()
    name = re.sub(r"^(the|my)\s+", "", name)
    name = re.sub(r"\s+(app|application|folder|website|site)$", "", name)
    if not name:
        return None, None
    if name in table:
        return name, table[name]
    hits = [k for k in table if len(name) >= 3 and (name in k or (len(k) >= 3 and k in name))]
    if len(hits) == 1:
        return hits[0], table[hits[0]]
    return None, None


# ---------- the commands ----------
def _try_open(label, target):
    try:
        open_target(target)
        return f"Opening {label}."
    except Exception:
        return f"I couldn't open {label}. Is it installed?"


def _open_app(name, config):
    label, target = _lookup(config["apps"], name)
    if not label:
        return (
            f'I don\'t have "{name}" on my app list. '
            f"You can add it in {CONFIG_PATH} (see the documentation)."
        )
    return _try_open(label.title() if label != "vs code" else "VS Code", target)


def _open_folder(name, config):
    label, path = _lookup(config["folders"], name)
    if not label:
        return f'I don\'t know a folder called "{name}". I know: {", ".join(sorted(config["folders"]))}.'
    if not Path(path).is_dir():
        return f"The {label} folder does not exist at {path}."
    return _try_open(f"your {label} folder", path)


def _open_site(name, config):
    label, url = _lookup(config["sites"], name)
    if label:
        return _try_open(label.title(), url)
    domain = (name or "").lower().strip().removeprefix("https://").removeprefix("http://").rstrip("/")
    if re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}", domain):
        return _try_open(domain, f"https://{domain}")
    return f'I don\'t know a website called "{name}". Try a web address like example.com, or ask me to search the web.'


def _web_search(query):
    query = (query or "").strip()[:200]
    if not query:
        return "What should I search for?"
    url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)
    try:
        open_target(url)
        return f'Searching the web for "{query}".'
    except Exception:
        return "I couldn't open the browser."


def _time_reply(now=None):
    now = now or datetime.now()
    hour = now.hour % 12 or 12
    return f"It's {hour}:{now:%M} {now:%p} on {now:%A}, {now:%B} {now.day}."


def search_files(query, roots, limit=MAX_RESULTS, max_seconds=SEARCH_SECONDS):
    """Newest-first list of safe-type files whose name contains every word of the query."""
    words = [w for w in re.findall(r"[a-z0-9]+", (query or "").lower()) if w not in GENERIC_FILE_WORDS]
    if not words:
        return []
    deadline = time.monotonic() + max_seconds
    found = []
    for root in roots:
        root = Path(root)
        if not root.is_dir():
            continue
        base_depth = len(root.parts)
        for dirpath, dirnames, filenames in os.walk(root):
            depth = len(Path(dirpath).parts) - base_depth
            dirnames[:] = [
                d for d in dirnames
                if not d.startswith(".") and d.lower() not in SKIP_DIRS and depth < MAX_DEPTH
            ]
            for name in filenames:
                low = name.lower()
                if Path(low).suffix in SAFE_EXTENSIONS and all(w in low for w in words):
                    path = Path(dirpath) / name
                    try:
                        found.append((path.stat().st_mtime, str(path)))
                    except OSError:
                        pass
            if time.monotonic() > deadline:
                break
        if time.monotonic() > deadline:
            break
    found.sort(reverse=True)
    return [p for _, p in found[:limit]]


def _find_file(query, config):
    files = search_files(query, config["search_folders"])
    if not files:
        return f'I couldn\'t find a file matching "{query}" in your Documents, Downloads, or Desktop.', None
    lines = "\n".join(
        f"{i}. {Path(p).name}  ({Path(p).parent.name})" for i, p in enumerate(files, start=1)
    )
    reply = f"I found:\n{lines}\nSay the number to open one, or \"never mind\"."
    return reply, {"type": "file_choice", "files": files}


def _volume(command, amount):
    if command == "volume_mute":
        press_key(KEY_VOLUME_MUTE)
        return "Muting (or unmuting) the sound."
    steps = DEFAULT_VOLUME_STEPS
    if isinstance(amount, int) and amount > 0:
        steps = max(1, min(25, round(amount / 2)))
    press_key(KEY_VOLUME_UP if command == "volume_up" else KEY_VOLUME_DOWN, steps)
    direction = "up" if command == "volume_up" else "down"
    return f"Turning the volume {direction} by about {steps * 2} percent."


# ---------- entry points used by assistant.py ----------
def analyze_pc_command(message, model, num_ctx):
    empty = {"command": "unknown", "target": "", "amount": 0}
    try:
        response = ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": PC_PROMPT},
                {"role": "user", "content": f"Message: {message}"},
            ],
            format=PC_SCHEMA,
            options={"temperature": 0, "num_ctx": num_ctx},
        )
        data = json.loads(response.message.content)
    except Exception as err:
        print("PC command analysis failed:", err, flush=True)
        return empty
    command = data.get("command")
    target = data.get("target")
    amount = data.get("amount")
    return {
        "command": command if command in PC_COMMANDS else "unknown",
        "target": target.strip() if isinstance(target, str) else "",
        "amount": amount if isinstance(amount, int) else 0,
    }


def handle_pc_command(message, model, num_ctx):
    """Returns (reply, pending). Only items on the allowed lists are ever opened."""
    cmd = analyze_pc_command(message, model, num_ctx)
    config = load_config()
    command, target = cmd["command"], cmd["target"]

    if command == "open_app":
        return _open_app(target, config), None
    if command == "open_folder":
        return _open_folder(target, config), None
    if command == "open_site":
        return _open_site(target, config), None
    if command == "web_search":
        return _web_search(target), None
    if command == "find_file":
        return _find_file(target, config)
    if command in ("volume_up", "volume_down", "volume_mute"):
        return _volume(command, cmd["amount"]), None
    if command == "lock":
        return "Lock the computer now? (yes or no)", {"type": "pc_lock"}
    if command == "time":
        return _time_reply(), None
    return HELP_TEXT, None


def pick_file(pending, index):
    """Open one of the files from the last search."""
    path = Path(pending["files"][index])
    config = load_config()
    roots = [Path(r).resolve() for r in config["search_folders"]]
    try:
        inside = any(root in path.resolve().parents for root in roots)
    except OSError:
        inside = False
    if not inside or path.suffix.lower() not in SAFE_EXTENSIONS or not path.is_file():
        return "I can't open that one."
    return _try_open(path.name, str(path))


def confirm_pc(pending):
    if pending["type"] == "pc_lock":
        try:
            lock_workstation()
            return "Locking the computer."
        except Exception:
            return "I couldn't lock the computer."
    return "I'm not sure what to confirm."