# Laptop variant (CPU-only)

Variant for laptops **without an NVIDIA GPU** (e.g. a Lenovo IdeaPad Slim 5 with Intel UHD Graphics + a 12-thread i5).

## Non-invasive by design

This folder **does not modify any file outside `laptop/`**. The CPU configuration is applied at runtime by the `run_laptop.py` wrapper, which monkey-patches the `config` module. The default (CUDA) setup keeps working unchanged: `python app.py` from the repo root behaves exactly as before.

## Prerequisites

1. Python 3.10 installed
2. Venv created and dependencies installed from the project root:
   ```powershell
   cd <repo-folder>
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Check that NO CUDA wheels were installed (they are not needed on CPU):
   ```powershell
   pip list | findstr nvidia
   ```
   Expected: empty. If it finds `nvidia-cublas-cu12` or `nvidia-cudnn-cu12`, uninstall them:
   ```powershell
   pip uninstall nvidia-cublas-cu12 nvidia-cudnn-cu12
   ```

## Running

Double-click `run.bat`, or from PowerShell:
```powershell
.\laptop\run.bat
```

Expected on first launch:
- Log `[init] Loading Whisper model...` (downloads `small`, ~244 MB, from Hugging Face once)
- Log `[init] Whisper ready.`
- PySide6 GUI + system tray icon
- No CUDA errors

Dictation hotkey: **Ctrl+Win** (speak while holding it, release to transcribe).

## Desktop shortcut + autostart at login

To avoid launching `run.bat` from a terminal every time:

```powershell
powershell -ExecutionPolicy Bypass -File .\laptop\install-shortcuts.ps1
```

It creates two `.lnk` shortcuts (with the `icons/app.ico` icon) that launch `pythonw.exe run_laptop.py` directly (no intermediate console window):

| Shortcut | Location | Effect |
|---|---|---|
| Desktop | `%USERPROFILE%\Desktop\<APP_NAME> (Laptop).lnk` | Double-click to launch manually |
| Startup | `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\<APP_NAME> (Laptop).lnk` | Starts automatically at Windows login |

**Idempotent**: re-running the script overwrites without errors. Handy if you move the project folder (re-run it to update the absolute target paths).

**To remove the shortcuts**:
```powershell
powershell -ExecutionPolicy Bypass -File .\laptop\install-shortcuts.ps1 -Uninstall
```

**Notes**:
- The Startup shortcut launches the app at every login. If you don't want that, simply delete it from `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\` (or run `-Uninstall`, edit `install-shortcuts.ps1` to skip the Startup entry, and re-run it).
- If you move the project, the shortcuts point to stale paths: re-run the script to recompute them.
- The shortcut target is the `pythonw.exe` of this specific venv: if you delete the venv, the shortcuts stop working until you recreate it and re-run the script.

## Model tuning

To change model, edit the 3 `config.WHISPER_*` lines in `run_laptop.py`:

| Model | Quality | Speed (12-thread CPU) | Usable for dictation? |
|---|---|---|---|
| `tiny` | low | very fast (~5x realtime) | Only if the others are too slow |
| `base` | fair | fast (~3-5x) | Yes |
| `small` (default) | good | real-time (~1-2x) | Yes, sweet spot |
| `medium` | very good | borderline (~0.5x) | Maybe, depends on CPU load |
| `large-v3` | best | too slow on CPU | No |

`compute_type = "int8"` is already the fastest option on CPU. Don't change it unless you hit a specific problem.

## Expected performance

Estimates on an i5-13420H (12 threads) + faster-whisper `small` int8:

| Audio | Transcription | Total latency (incl. paste) |
|---|---|---|
| 5s | 1.5-2.5s | ~2-3s |
| 10s | 3-5s | ~3-5s |
| 15s | 4.5-7.5s | ~5-8s |

If latency is consistently >12s for 10s of audio, try `WHISPER_MODEL = "base"`.

## Troubleshooting

**Error `Could not find or load module ...cublas...`**:
faster-whisper is looking for CUDA. Check that `run_laptop.py` sets `config.WHISPER_DEVICE = "cpu"` before `app` is run. The order in the script is already correct; make sure it hasn't been modified.

**Error `Failed to open audio device`**:
sounddevice can't find a default audio input. Check the microphone in Windows Settings → Sound → Input.

**Ctrl+Win hotkey doesn't work**:
Check that pynput is installed (`pip show pynput`). On some Windows installs you need to run as administrator to intercept the Win key.

**Transcription very slow or fails with Out Of Memory**:
- Switch to `WHISPER_MODEL = "base"` (244 MB → 145 MB)
- Still slow: `WHISPER_MODEL = "tiny"` (74 MB)
- Still OOM: close heavy apps (browser, Slack); `small` int8 needs ~600 MB of free RAM

## Technical caveats

- The monkey-patch works because `worker.py` and `app.py` use `import config` (the whole module). If those imports ever become `from config import X`, the wrapper will silently break. In that case update `run_laptop.py` (e.g. use a .pth override or a fork of the module).
- Changes to the root `config.py` (e.g. a new default model) do NOT affect the laptop variant, because the wrapper's explicit override always wins.
