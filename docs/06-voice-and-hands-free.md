# Jarvis System Documentation
## Major Topic 6: Voice and Hands-Free Control

**Status:** Complete
**Goal:** Talk to Jarvis and hear him answer, fully offline, from anywhere on the laptop, with an optional hands-free mode where one hotkey press is the whole conversation. Also covers deleting tasks, notes, and reminders by chat, added at the end of this topic.
**Cost:** $0 (all voice software is free and runs locally)
**Depends on:** Topics 1 to 5

The source of truth for all code is the GitHub repo. This document explains the design and why.

---

## 1. What you can do now

| Control | Where | What it does |
|---|---|---|
| Mic button | Chat bar | Click to start recording, click again to stop. Your words appear in the chat box |
| **Ctrl+Alt+J** | Anywhere in Windows | Same as the mic button, even with the dashboard closed. Also in the tray menu as "Talk" |
| Speaker button | Chat bar | Green = Jarvis reads each chat reply aloud. Off by default |
| **Auto** button | Chat bar | Green = stops listening by itself when you stop talking, then sends your words. Off by default |

Hands-free flow (Auto on, speaker on): press **Ctrl+Alt+J** once, speak, go quiet. Jarvis sends it and answers aloud while the dashboard stays hidden.

The two switches are remembered between runs.

---

## 2. Components

| Part | Tool | Notes |
|---|---|---|
| Speech to text | faster-whisper, model `small` | Runs on the CPU (int8), English forced, so the 8 GB GPU stays free for the language model |
| Text to speech | Piper, voice `en_US-lessac-medium` | Runs on the CPU, fast, offline |
| Recording | Browser microphone API inside the dashboard page | No extra native software |
| Audio conversion | `recorder.js` (our code) | Recording to 16 kHz mono WAV |

Python packages in the backend environment: `faster-whisper`, `python-multipart` (needed by FastAPI for file uploads), `piper-tts`, and `av<19` (see Troubleshooting).

One-time downloads: the Whisper model (automatic on first use, cached) and the Piper voice (command below). Both work offline afterwards.

Piper voice setup:
```
cd C:\Jarvis\voices
python -m piper.download_voices en_US-lessac-medium
```
`voices/` is listed in `.gitignore` because the files are large.

---

## 3. Files

```
C:\Jarvis\
  voices\
    en_US-lessac-medium.onnx (and .onnx.json)     Piper voice (not in Git)
  backend\
    voice.py        POST /voice/transcribe (speech to text)
    tts.py          POST /voice/speak (text to speech)
    deletion.py     delete tasks, notes, reminders by chat (section 9)
    assistant.py    now imports deletion.py, NUM_CTX = 6144
    main.py         includes the voice and tts routers
  shell\
    recorder.js     recording to 16 kHz mono WAV
    dashboard.html  mic, speaker, and Auto buttons, silence watcher
    preload.js      voice functions for the page
    main.js         hotkey, tray item, voice message handlers
```

---

## 4. Endpoints

| Method | Address | Purpose |
|---|---|---|
| POST | `/voice/transcribe` | Upload a file in the form field `audio`, returns `{"text": "..."}` |
| POST | `/voice/speak` | `{"text": "..."}` returns a WAV file. 400 if there is nothing to say, 503 if the voice file is missing |

`voice.py` settings: model `small`, `language="en"`, `beam_size=5`, `vad_filter=True` (skips silence). The model loads on the first request, so the first transcription is slower. Later ones reuse it.

---

## 5. Listening pipeline

```
Mic click or hotkey
  -> getUserMedia (mono, echo cancellation, noise suppression)
  -> MediaRecorder
  -> stop
  -> recorder.js: decode, mix to mono, lower to 16 kHz (averaging each window), write a 16-bit WAV
  -> main.js (voice:transcribe) uploads it as speech.wav in the field "audio"
  -> backend returns text
  -> text is placed in the chat box (added after anything already typed)
```

- Recording stops after 60 seconds at most. A recording under 0.5 seconds shows "Too short".
- Messages shown instead of silent failures: microphone not available (with the Windows privacy path), "I didn't catch that", transcription error, "Could not process the recording".
- The sphere shows: green ripples while listening, purple while transcribing and thinking, bright pulse while speaking.
- Jarvis's own windows may use the microphone. Electron's permission handlers allow only the microphone and refuse every other request.
- Windows must allow it: Settings, Privacy & security, Microphone, "Let desktop apps access your microphone".

---

## 6. Global hotkey

- `VOICE_HOTKEY = "Control+Alt+J"` at the top of `shell\main.js`. Change it there if another app owns the combination. If registration fails, PowerShell (when started with `npm start`) prints "Could not register ...".
- It is **press to start, press to stop**. Windows does not report when a global hotkey is released, so "hold to talk" is not possible. (Auto mode removes the second press, see section 8.)
- The dashboard page does the recording. If the dashboard window does not exist yet, `main.js` creates it hidden (`createDashboardWindow(false)`) and sends it `voice:toggle` when loaded. The window has `backgroundThrottling: false` so timers stay accurate while hidden.
- After a hotkey recording, the page asks `main.js` to show the dashboard so you can read the result, except in full hands-free mode (Auto on and speaker on) when it stays hidden. Errors always bring the window up.

---

## 7. Spoken replies

- The speaker button saves its state in the page's local storage under `jarvis.speak`.
- Flow: reply arrives, the page calls `window.jarvis.speak(text)`, `main.js` posts to `/voice/speak`, the WAV comes back, the page plays it, and the sphere shows "speaking" until the audio ends.
- Speech is stopped when you send a new message and when you start recording, so the microphone does not hear Jarvis.
- If speech fails, a small gray line "Voice: ..." appears in the chat and the reply is still there.
- Text is cleaned before speaking: links and markdown symbols removed, "31°C" becomes "31 degrees Celsius", "60%" becomes "60 percent", list dashes become commas, line breaks become pauses. Limit: 700 characters.
- Only chat replies are spoken. Reminder notifications and the automatic briefing are not (yet).
- The old fixed 2-second "speaking" pulse after every reply was removed. The sphere now shows "speaking" only while real audio plays.

---

## 8. Auto: stop by itself and send

Local storage key `jarvis.autosend`. When Auto is on:

| Auto | Speaker | After you stop talking |
|---|---|---|
| Off | any | Recording continues until you click or press the hotkey again. Words wait in the box for Enter |
| On | Off | Stops by itself, sends immediately, and the dashboard comes up so you can read the reply |
| On | On | Fully hands-free: stops, sends, answers aloud, dashboard stays hidden |

**How it hears you stop** (all in `dashboard.html`, watching the microphone level about 16 times a second):
1. For the first 0.4 seconds it measures the room's background noise.
2. Speech means louder than `max(0.015, noise x 3)`, lasting at least 0.2 seconds.
3. After speech, 1.3 seconds of quiet means you are finished: it stops, transcribes, and sends.
4. If no speech is heard for 7 seconds it gives up with "I didn't hear anything" and skips transcription.
5. A manual stop always transcribes, so a very soft voice is not thrown away.

Tuning constants (in the block "stop by itself when you stop talking"):

| Constant | Default | Change it when |
|---|---|---|
| `SILENCE_MS` | 1300 | It cuts you off mid-thought (raise) or waits too long (lower, try 900) |
| `NO_SPEECH_MS` | 7000 | You want it to give up sooner or later |
| `THRESHOLD_MIN` | 0.015 | It misses a quiet voice (lower, try 0.008) |
| `NOISE_FACTOR` | 3 | A noisy room triggers it falsely (raise) |

Safety: Auto is off by default because a misheard command would act on its own. Deleting always asks for a yes first (section 9).

---

## 9. Delete by chat (added at the end of this topic)

```
You:    Cancel my reminder to call mom.
Jarvis: Delete the reminder "Call mom (Thu, Oct 8 at 7:00 AM)"? (yes or no)
You:    Yes.
Jarvis: Done. I deleted the reminder "Call mom (Thu, Oct 8 at 7:00 AM)".
```

- New action `delete_item` with two new analysis fields: `item_kind` (task, note, or reminder) and `item_text` (the few words that identify the item).
- The model only describes the item. `deletion.py` searches the real list: every important word must appear in the item's text (a trailing "s" is ignored, and words like "delete", "my", "the" are skipped).
- Searched lists: all tasks (including done ones), the latest 50 notes, and the upcoming reminders (reminders that already fired are not listed).
- One match: Jarvis asks for yes or no. No match: he says so and nothing changes. Several matches: he lists up to 5 and asks for a number. A number ("2", "two", "the second one") is read by code, without the model.
- The question lives for one message only. "No", "never mind", or any other message cancels it. Nothing is deleted without a yes.
- "I finished buying rice" still completes a task. Only delete, remove, or cancel wording deletes.
- The false-claim safety net also catches "I deleted..." replies that code did not perform.
- Pending question types now: `task` (add this task?), `reminder` (when?), `delete` (delete this item?), `delete_choice` (which one?).

**Context size:** the analysis prompt grew to about 11,800 characters, which no longer fits comfortably in the model's default 4096-token window. Both model calls now use `NUM_CTX = 6144` (in `assistant.py`). It costs a few hundred MB of GPU memory. Check with `ollama ps` while Jarvis works: PROCESSOR should still say 100% GPU. If it does not, lower `NUM_CTX` and shorten the examples in the analysis prompt.

Sanity check that `assistant.py` loaded all its pieces:
```
cd C:\Jarvis\backend
python -c "import assistant; print(len(assistant.ANALYSIS_PROMPT))"
```
It should print about 11778.

---

## 10. Message channels added (page to `main.js`)

| Channel | Direction | Purpose |
|---|---|---|
| `voice:transcribe` | page to main (request and reply) | Send WAV bytes, get `{ok, text}` or `{ok: false, error}` |
| `voice:speak` | page to main (request and reply) | Send text, get `{ok, audio}` or `{ok: false, error}` |
| `voice:state` | page to main | Set the sphere to listening, speaking, or idle |
| `voice:toggle` | main to page | Start or stop recording (hotkey and tray item). Carries `{fromHotkey: true}` |

Matching functions in `preload.js`: `transcribeAudio`, `speak`, `setVoiceState`, `onVoiceToggle`.

---

## 11. Verification results

| Area | Result |
|---|---|
| Whisper transcription of a recorded clip, endpoint `/voice/transcribe` | Passed |
| Mic button: start, stop, text in the box, too short, silence, errors, appends to typed text | Passed |
| Hotkey from another app, hidden dashboard, tray item, dashboard appears with the text | Passed |
| Piper test sound, spoken replies, interrupt on send and on mic start, setting remembered | Passed |
| Auto: send after transcription, hands-free with speaker, dashboard stays hidden | Passed |
| Stops by itself after you finish talking, gives up when silent, ignores steady noise, keeps listening through short pauses | Passed |
| Delete by chat: confirm, decline, several matches, no match, numbers, expiry, does not touch "finished" | Passed |

---

## 12. Troubleshooting log

| Problem | Cause | Fix |
|---|---|---|
| Transcription failed with a PyAV error about `metadata_errors` | A newer PyAV (19) was incompatible with faster-whisper | `pip install "av<19"` in the backend environment |
| "Microphone not available" | Windows blocks desktop apps from the microphone | Settings, Privacy & security, Microphone, turn on "Let desktop apps access your microphone" |
| First transcription is slow | The Whisper model loads on first use | Expected. Later ones are faster |
| Hotkey does nothing | Another app owns the combination | Change `VOICE_HOTKEY` in `shell\main.js` and restart |
| Gray line "Voice: Voice file not found" | The Piper voice is not at `C:\Jarvis\voices\en_US-lessac-medium.onnx` | Download it with `python -m piper.download_voices en_US-lessac-medium` in that folder |
| Jarvis hears himself | Speaker audio picked up by the microphone | Speech already stops when recording starts. Headphones fix the rest |
| Recording cuts off early or never stops | Silence detection thresholds do not match the room or voice | Tune the constants in section 8 |
| Wrong words transcribed | Recognition is not perfect, especially with background noise or accents | Speak closer to the microphone. Leave Auto off to review text before sending |
| Analysis answers got worse after adding more examples | The prompt no longer fit in 4096 tokens | `NUM_CTX = 6144`, and keep examples lean |
| Edits to `shell` files did nothing | An old copy was still running | Quit from the tray, check Task Manager for leftover `electron.exe`, then `npm start` |

---

## 13. Known limitations

- **English only.** Whisper is forced to English and the Piper voice is English. Filipino or mixed-language speech will be transcribed poorly.
- **Press to start, press to stop** for the global hotkey (Auto removes the second press). There is no wake word yet.
- **Silence detection uses loudness only.** A TV or other voices in the room can keep it recording until the 60-second limit. A very quiet voice may need a lower `THRESHOLD_MIN`.
- **Auto trusts the transcript.** A misheard command will be acted on, except deletions, which always ask first.
- **Only chat replies are spoken**, up to 700 characters. Reminder notifications and the automatic briefing are silent.
- **No streaming.** Jarvis finishes writing the whole reply, then speaks it, so the delay is generation time plus synthesis time.
- **Whisper runs on the CPU.** It is fast enough for short phrases but slower than a GPU would be.
- **Delete matching is simple word matching.** Synonyms are not understood, and at most 5 matches are shown.
- **Voice and the two switches are not configurable in the UI** (voice file and constants are edited in code).

---

## 14. Next: Major Topic 7

Candidates, in the order I would suggest:
1. **PC control** with a confirmation step: open apps, find files, volume and similar actions.
2. **Speak reminders and the briefing aloud**, so notifications are heard too.
3. **A wake word** ("Hey Jarvis"), so the hotkey is not needed.