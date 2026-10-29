"""Screenshot / demo mode:  python app.py --screenshot [OUTDIR]

Renders every window and state with fake content and saves PNGs, then exits.
No manual interaction, nothing shown on screen (WA_DontShowOnScreen), and
no real data touched:
- app.py points DICTATION_DATA_DIR at a fresh temp folder before history /
  vocabulary are imported, so the demo writes its fake rows there;
- the worker is created but never started (no microphone, no hotkey hook,
  no model download);
- the tray icon is not shown and autostart is never written.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

import config
import history
import theme
import vocabulary
from pages import format_meta

DEFAULT_OUT = Path(__file__).parent / "docs" / "screenshots" / "portfolio"

DEMO_TRANSCRIPTS = [
    # (minutes ago, text, stt seconds, used_llm, llm seconds)
    (2, "Hi Sarah, thanks for the quick review. I've pushed the fix for the login redirect "
        "and added a regression test, so it should be ready to merge this afternoon.", 0.9, True, 0.6),
    (18, "Reminder for tomorrow's stand-up: the overlay now shows a transcribing state, and "
         "history search is about twice as fast after adding the index.", 0.8, False, 0.0),
    (55, "Note to self: try the small model on the laptop with int8 compute and compare "
         "accuracy against large-v3 on the same recording.", 0.7, False, 0.0),
    # Italian on purpose: shows the it/en auto-detection ("Remind me to call the dentist...")
    (130, "Ricordami di chiamare il dentista lunedì mattina per spostare l'appuntamento.", 0.6, False, 0.0),
    (60 * 26, "Can you send me the slides from the onboarding session? I'd like to share them "
              "with the two new starters on Monday.", 0.8, True, 0.5),
    (60 * 50, "Book a table for four at seven thirty on Friday and ask whether they have a "
              "vegetarian tasting menu.", 0.6, False, 0.0),
]
DEMO_VOCAB = ["PySide6", "faster-whisper", "CTranslate2", "Ollama", "SQLite", "Kubernetes", "Leicester"]
DEMO_LOG = [
    "[model] loading large-v3 on cuda (float16)…",
    "[model] ready in 3.4s",
    "[audio] input device: Microphone (USB Audio) — 16000 Hz mono",
    "[ready] Hold Ctrl+Win to dictate.",
    "[rec] start",
    "[rec] stop — 4.2s of audio",
    "[lang] detected en (p=0.97)",
    "[stt] 0.91s segments=2",
    "[paste] 168 chars",
]


def _seed():
    """Fill the TEMP data dir (never the real one) with demo rows."""
    assert "dictation-demo-" in str(config.DATA_DIR), "demo must run on a temp data dir"
    history.init_db()
    now = time.time()
    with sqlite3.connect(str(history.DB_PATH)) as c:
        for mins, text, stt, llm, llm_s in reversed(DEMO_TRANSCRIPTS):
            c.execute(
                "INSERT INTO transcriptions (ts, text_raw, text_final, used_llm, stt_seconds, llm_seconds) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (now - mins * 60, text, text, int(llm), stt, llm_s),
            )
    vocabulary.save(DEMO_VOCAB)


def _settle(app: QApplication, n: int = 4):
    for _ in range(n):
        app.processEvents()


def _save(pm: QPixmap, out: Path, name: str, saved: list):
    path = out / f"{name}.png"
    pm.save(str(path), "PNG")
    saved.append(path)


def _prepare(w: QWidget):
    w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    w.show()


def _hero(app_pm: QPixmap, overlay_pm: QPixmap) -> QPixmap:
    """Main window + overlay composited on a soft backdrop (README header)."""
    dpr = app_pm.devicePixelRatio()
    pad = int(48 * dpr)
    w = app_pm.width() + pad * 2
    h = app_pm.height() + pad * 2
    out = QPixmap(w, h)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    g = QLinearGradient(0, 0, w, h)
    g.setColorAt(0, QColor("#0e3b38"))
    g.setColorAt(1, QColor("#121417"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawRoundedRect(QRect(0, 0, w, h), 24 * dpr, 24 * dpr)
    # window shadow
    for i in range(12, 0, -1):
        c = QColor(0, 0, 0, 10)
        p.setBrush(c)
        p.drawRoundedRect(QRect(pad - i, pad - i + 6, app_pm.width() + 2 * i, app_pm.height() + 2 * i),
                          12 + i, 12 + i)
    p.drawPixmap(QPoint(pad, pad), app_pm)
    ox = pad + app_pm.width() - overlay_pm.width() - int(24 * dpr)
    oy = pad + app_pm.height() - overlay_pm.height() - int(56 * dpr)
    p.drawPixmap(QPoint(ox, oy), overlay_pm)
    p.end()
    out.setDevicePixelRatio(1)
    return out


def _capture_window(app, MainWindow, out: Path, saved: list, suffix: str = "", full: bool = True):
    w = MainWindow(demo=True)
    w.resize(980, 700)
    # state changes call overlay.show_*(): keep it off the real screen
    w.overlay.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    # never toggle the real autostart entry from the demo
    w.settings_tab.autostart_check.blockSignals(True)
    w.settings_tab.autostart_check.setChecked(True)
    for line in DEMO_LOG:
        w.home.append_log(line)
    last = DEMO_TRANSCRIPTS[0]
    w.home.set_last_transcription(
        last[1], format_meta(time.time() - last[0] * 60, last[2], last[3], last[4]))
    _prepare(w)

    # Home — ready
    w.on_state_changed("listening")
    w.nav.setCurrentRow(0)
    _settle(app)
    home_ready = w.grab()
    _save(home_ready, out, f"01-home-ready{suffix}", saved)
    if not full:
        w.close()
        return

    # Home — recording (status card + overlay)
    w.on_state_changed("recording")
    w.overlay.hide_recording()
    _settle(app)
    _save(w.grab(), out, "02-home-recording", saved)

    # Home — transcribing, activity log open
    w.on_state_changed("processing")
    w.overlay.hide_recording()
    w.home._toggle_log()
    _settle(app)
    _save(w.grab(), out, "03-home-transcribing-log", saved)
    w.home._toggle_log()

    # Home — paused / first run
    w.on_state_changed("idle")
    _settle(app)
    _save(w.grab(), out, "04-home-paused", saved)

    # History with a selected item
    w.on_state_changed("listening")
    w.nav.setCurrentRow(1)
    w.history_tab.list_widget.setCurrentRow(0)
    _settle(app)
    _save(w.grab(), out, "05-history", saved)

    # Vocabulary
    w.nav.setCurrentRow(2)
    w.vocab_tab.list_widget.setCurrentRow(1)
    _settle(app)
    _save(w.grab(), out, "06-vocabulary", saved)

    # Settings
    w.nav.setCurrentRow(3)
    _settle(app)
    _save(w.grab(), out, "07-settings", saved)

    # Overlay states (transparent PNGs)
    ov = w.overlay
    ov.freeze_frame("recording", 3.37, "horizontal")
    _prepare(ov)
    _settle(app)
    overlay_rec = ov.grab()
    _save(overlay_rec, out, "08-overlay-recording", saved)
    ov.freeze_frame("processing", 0.42, "horizontal")
    _settle(app)
    _save(ov.grab(), out, "09-overlay-transcribing", saved)
    ov.freeze_frame("recording", 2.1, "vertical")
    _settle(app)
    _save(ov.grab(), out, "10-overlay-vertical", saved)
    ov.freeze_frame("recording", 3.37, "horizontal")
    ov.hide()

    # Tray menu (as it looks while the engine is running)
    menu = w.tray_menu
    menu.ensurePolished()
    menu.adjustSize()
    _prepare(menu)
    _settle(app)
    _save(menu.grab(), out, "11-tray-menu", saved)
    menu.hide()

    # App icon states
    from widgets import app_pixmap
    strip = QPixmap(4 * 72, 64)
    strip.fill(Qt.GlobalColor.transparent)
    p = QPainter(strip)
    for i, s in enumerate(["idle", "listening", "recording", "processing"]):
        p.drawPixmap(i * 72 + 4, 0, app_pixmap(s, 64))
    p.end()
    _save(strip, out, "12-tray-icons", saved)

    # README hero: ready window + recording overlay
    _save(_hero(home_ready, overlay_rec), out, "00-hero", saved)
    w.close()


def run(app: QApplication, MainWindow, out_dir: str | None = None) -> int:
    out = Path(out_dir) if out_dir else DEFAULT_OUT
    out.mkdir(parents=True, exist_ok=True)
    _seed()
    saved: list[Path] = []

    theme.apply(app, "dark")
    _capture_window(app, MainWindow, out, saved, full=True)

    theme.apply(app, "light")
    _capture_window(app, MainWindow, out, saved, suffix="-light", full=False)

    for pth in saved:
        print(f"[screenshot] {pth}")
    _cleanup_temp_data()
    return 0


def _cleanup_temp_data():
    """Best effort: close our log handlers and delete the temp data dir."""
    import logging
    import shutil
    if "dictation-demo-" not in str(config.DATA_DIR):
        return  # paranoia: never delete anything else
    for name in list(logging.root.manager.loggerDict) + [""]:
        lg = logging.getLogger(name)
        for h in list(getattr(lg, "handlers", [])):
            try:
                h.close()
                lg.removeHandler(h)
            except Exception:
                pass
    try:
        import faulthandler
        import logging_setup
        faulthandler.disable()
        if logging_setup._fault_file_handle:
            logging_setup._fault_file_handle.close()
    except Exception:
        pass
    shutil.rmtree(config.DATA_DIR, ignore_errors=True)
