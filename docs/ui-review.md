# UI review — Qt desktop app

A structured pass over the PySide6 interface before publishing the project.
The React/web design skills don't apply to Qt, so the same four-phase workflow
was applied by hand. Scope: **UI layer only** (`app.py`, `overlay.py`, new
`theme.py`, `theme.qss`, `widgets.py`, `pages.py`). `worker.py`, the
faster-whisper calls, the pynput hotkey and the pycaw audio mute were not
touched.

---

## Phase 0 — What exists

**Stack:** Python 3.10, PySide6 6.11 (Qt 6), default Windows style, no theme,
no icon set. Inline `setStyleSheet()` calls with hard-coded colours.

**Windows and states**

| Surface | Before | States |
|---|---|---|
| Main window | `QTabWidget`: Home / History / Vocabulary / Settings (labels in Italian) | — |
| Home | coloured state label, 4 equal buttons (Start, Stop, Open log, Log folder), 2 checkboxes, always-visible log console | idle, listening, recording, processing |
| History | search + list (`[timestamp] preview`) + editable detail + "add to vocabulary" | empty, results, no match |
| Vocabulary | grey help text, add row, list, remove button | empty, list |
| Settings | form (Whisper model, language, Ollama model, autostart), italic note, save | — |
| Overlay | frameless pill, red border, red dot + `REC...` | recording only |
| Tray | megaphone PNG with coloured badge, menu Show / Start / Stop / Quit | 4 icon states |

**Data flow (unchanged):** `DictationWorker` runs its own threads (hotkey
listener, PortAudio callback, STT). It reports through three callbacks →
`WorkerBridge` re-emits them as Qt signals → slots on the UI thread update
widgets, write to SQLite (`history.py`) and show/hide the overlay.

**Must not change:** worker API (`start/stop/state`, `use_llm_cleanup`,
`mute_audio_while_recording`, `vocabulary`), `TranscriptionResult`, history
schema, vocabulary JSON, `config` keys, the hotkey, the bridge signals.

---

## Phase 1 — Problems found

1. **No single source of style.** Colours (`#2a2a2a`, `#a02020`, `#2d5a2d`,
   `#8a6a00`, `#1e1e1e`, `#aaa`, `#888`) are repeated across widgets as inline
   styles; the overlay hard-codes `QColor(220, 50, 50)`. No light/dark story:
   a dark console sits inside a light native window.
2. **Weak hierarchy on Home.** Start, Stop, Open log and Log folder are four
   buttons with the same weight in one row; the diagnostic actions compete with
   the primary action. The raw log console takes most of the screen.
3. **The hotkey is almost invisible.** "Ctrl+Win" appears only inside the state
   text and in an italic footnote on the Settings tab — but it is *the* way to
   use the product.
4. **The result is not on the main screen.** The last transcription is only
   visible by switching to the History tab.
5. **Missing state feedback.** Loading the Whisper model (several seconds on
   first start) shows nothing but a disabled button; the overlay disappears
   during "processing", so after releasing the keys there is no feedback until
   the text is pasted; the tray menu always enables both Start and Stop.
6. **Contrast / readability.** `#888` italic text on the default background is
   below AA for small text; state colours are dark (`#2d5a2d`) with white bold
   text — readable but heavy; all-caps "REGISTRAZIONE…".
7. **History rows are hard to scan.** `[2026-10-28 04:50:12]  text…` puts the
   timestamp first and truncates the text at 80 characters.
8. **No empty states.** Empty history / vocabulary show a blank white list.
9. **Inconsistent iconography.** Emoji (▶ ■ 📄 📁 💾 ⟳) render differently per
   Windows version; the megaphone logo doesn't say "dictation", and
   `assets/logo.png` has a fake transparency checkerboard baked into the pixels.
10. **Mixed language.** UI in Italian, logs half Italian — not readable by the
    people who will look at the screenshots.

---

## Phase 2 — Changes

**Structure**

- Sidebar navigation (brand, tagline, 4 items with icons, "runs 100% offline"
  footer) instead of tabs — the privacy message is always visible.
- **Home** becomes a dashboard, top to bottom:
  1. *Status card* (hero): big state title + one-line hint, animated dot,
     **Ctrl + Win key caps** on the right, one primary action that swaps
     between *Start engine* and *Stop*, engine summary (`large-v3 · cuda ·
     auto-detect (it/en)`) as a caption. The card is tinted with the state
     colour.
  2. *Last transcription* with timestamp, timings and a Copy button; friendly
     empty state that teaches the hotkey.
  3. *Options* (LLM cleanup, mute speakers).
  4. *Activity log*, collapsed by default; Open log / Log folder are ghost
     buttons in its header.
- **History** becomes master/detail side by side: two-line rows (text first,
  metadata muted below, accent bar on selection), read-only transcript with
  Copy and *Add selection to vocabulary*, counts and empty / no-match states.
- **Vocabulary**: explanation as page subtitle, primary Add, empty state,
  Remove enabled only with a selection.
- **Settings**: grouped cards (Transcription, LLM cleanup, Hotkey & system),
  hotkey shown as key caps, data folder shown (privacy), primary Save.
- **Overlay**: dark pill that works on any background; *recording* = pulsing
  red dot + 5 animated bars + elapsed time; new *transcribing* state = amber
  spinner. Animation runs at ~30 fps only while visible. The bars are
  decorative (the audio stream belongs to the worker thread and is not read
  by the UI) — documented in the code.
- **Tray**: microphone tile icon tinted per state (same drawing as the app icon
  and the regenerated `app.ico`), menu with a disabled status line and
  Start/Stop enabled according to state.

**Theme** (`theme.py` + `theme.qss`)

- Tokens: colour (`bg`, `surface`, `surface_alt`, `border`, `text`,
  `text_muted`, `accent`, `state_idle|loading|listening|recording|processing`,
  derived `_tint`/`_edge`), spacing (4/8/12/16/24/32), radius (6/10/14), type
  scale (11/12/13/16/24 px), font stacks (Segoe UI Variable → Segoe UI;
  Cascadia Mono → Consolas). No Inter.
- `theme.qss` uses `@token` placeholders; `theme.apply()` substitutes them,
  sets the Fusion style, a matching `QPalette` and the app font.
- Light/dark follows the Windows setting (`QStyleHints.colorScheme`), override
  with `DICTATION_THEME=light|dark`. All text tokens (including the
  faint caption colour) were checked at ≥ 4.5:1 on both `surface` and `bg`
  in both themes; primary text ≈ 14–17:1, muted ≈ 6–7:1.
- Variants via dynamic properties (`variant="primary|danger|ghost"`,
  `role="pageTitle|sectionTitle|muted|caption|empty"`,
  `StatusCard[state=…]`) instead of per-widget stylesheets.

**Responsive behaviour (window resize):** minimum 820×600. The sidebar is
fixed (208 px); pages stretch. History's splitter keeps both panes ≥ 320 px
and is user-resizable; rows elide to two lines. The log card grows only when
expanded.

**Stays identical:** every worker call, signal and slot, history/vocabulary
I/O, settings semantics (in-memory until restart, as before), close-to-tray,
overlay drag/rotate/reset and persisted position.

---

## Phase 3 — Implementation map

| File | Role |
|---|---|
| `theme.py` | tokens, light/dark detection, QSS substitution, `apply()` |
| `theme.qss` | the only stylesheet; tokens only, no hex values |
| `widgets.py` | QPainter line icons, app/tray icon, `StatusDot`, `KeyCombo`, card helpers, `HistoryItemDelegate` |
| `pages.py` | Home / History / Vocabulary / Settings (same public attributes and signals as before) |
| `app.py` | `WorkerBridge`, sidebar, `MainWindow`, tray, `--screenshot` entry |
| `overlay.py` | recording / transcribing overlay |
| `demo.py` | off-screen screenshot renderer with fake data in a temp folder |
| `scripts/make_icons.py` | regenerates `icons/app.ico` and tray PNGs from the same drawing |

Screenshots: `python scripts\portfolio_screenshots.py` →
`docs/screenshots/portfolio/`.

**Not done / next:**
- Real input level in the overlay would need a thread-safe level value from
  the worker's audio callback (worker change, out of scope here).
- The hotkey is still fixed in `worker.py`; the UI shows it from
  `config.HOTKEY_KEYS`, so a future configurable hotkey only needs the worker
  side.
- Settings are still applied in memory only (same as before); persisting them
  to a JSON next to `vocabulary.json` would be the natural follow-up.
- A short GIF of the overlay while dictating (needs a real recording session).
