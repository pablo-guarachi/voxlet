"""Desktop GUI (PySide6). Product name: config.APP_NAME.

Main window with a sidebar (Home / History / Vocabulary / Settings), tray
icon tinted by engine state, floating overlay. The DictationWorker runs its
own threads (hotkey listener, audio callback, STT); it talks to the UI only
through Qt signals on WorkerBridge, so widgets are touched on the UI thread.

    python app.py                    normal start
    python app.py --screenshot [DIR] demo mode: render every window/state
                                     with fake data to PNGs and exit
"""
from __future__ import annotations

import os
import sys
import tempfile

# Demo/screenshot mode must be decided BEFORE config/history are imported:
# it redirects the data folder to a throw-away temp dir so the real history
# and vocabulary are never read or written.
DEMO_MODE = "--screenshot" in sys.argv
if DEMO_MODE:
    os.environ["DICTATION_DATA_DIR"] = tempfile.mkdtemp(prefix="dictation-demo-")
    os.environ["DICTATION_DEMO"] = "1"

from pathlib import Path

import logging_setup  # init as early as possible
log = logging_setup.init()

from PySide6.QtCore import QObject, QSize, Qt, Signal, Slot
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMainWindow, QMenu, QMessageBox, QStackedWidget, QSystemTrayIcon,
    QVBoxLayout, QWidget,
)

import autostart
import config
import history
import theme
import vocabulary
from overlay import RecordingOverlay
from pages import STATE_LABEL, HistoryTab, HomeTab, SettingsTab, VocabTab, format_meta
from widgets import app_icon, app_pixmap, icon
from worker import DictationWorker, TranscriptionResult

APP_NAME = config.APP_NAME
ROOT = Path(__file__).parent


class WorkerBridge(QObject):
    state_changed = Signal(str)
    log_received = Signal(str)
    transcription_received = Signal(object)

    def emit_state(self, s: str):
        self.state_changed.emit(s)

    def emit_log(self, m: str):
        # everything shown in the panel also goes to the log file
        log.info("[ui] %s", m)
        self.log_received.emit(m)

    def emit_transcription(self, r: TranscriptionResult):
        self.transcription_received.emit(r)


def _list_ollama_models() -> list[str]:
    try:
        import requests
        r = requests.get("http://localhost:11434/api/tags", timeout=2)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []


# =====================================================================
# SIDEBAR
# =====================================================================
NAV = [("Home", "home"), ("History", "history"), ("Vocabulary", "book"), ("Settings", "gear")]


def _build_sidebar() -> tuple[QFrame, QListWidget]:
    side = QFrame()
    side.setObjectName("Sidebar")
    side.setFixedWidth(208)
    lay = QVBoxLayout(side)
    lay.setContentsMargins(theme.SPACE["lg"], theme.SPACE["xl"], theme.SPACE["lg"], theme.SPACE["lg"])
    lay.setSpacing(theme.SPACE["xs"])

    brand_row = QHBoxLayout()
    brand_row.setSpacing(theme.SPACE["sm"])
    logo = QLabel()
    logo.setPixmap(app_pixmap("idle", 64).scaled(
        28, 28, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
    brand_row.addWidget(logo)
    brand = QLabel(APP_NAME)
    brand.setObjectName("Brand")
    brand_row.addWidget(brand)
    brand_row.addStretch()
    lay.addLayout(brand_row)
    tagline = QLabel(config.APP_TAGLINE)
    tagline.setObjectName("BrandTagline")
    tagline.setWordWrap(True)
    lay.addWidget(tagline)
    lay.addSpacing(theme.SPACE["lg"])

    nav = QListWidget()
    nav.setObjectName("Nav")
    nav.setIconSize(QSize(18, 18))
    nav.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    for text, ic in NAV:
        it = QListWidgetItem(icon(ic), "  " + text)
        it.setSizeHint(QSize(0, 38))
        nav.addItem(it)
    nav.setFixedHeight(len(NAV) * 42 + 4)
    lay.addWidget(nav)
    lay.addStretch()

    footer = QLabel("Runs 100% offline.\nAudio never leaves this PC.")
    footer.setObjectName("SidebarFooter")
    lay.addWidget(footer)
    return side, nav


# =====================================================================
# MAIN WINDOW
# =====================================================================
class MainWindow(QMainWindow):
    def __init__(self, demo: bool = False):
        super().__init__()
        self._demo = demo
        self.setWindowTitle(APP_NAME)
        self.resize(980, 700)
        self.setMinimumSize(820, 600)
        self.setWindowIcon(app_icon("idle"))

        history.init_db()
        if not demo:
            try:
                autostart.migrate_legacy()
            except Exception:
                log.exception("autostart legacy migration failed")

        # --- Worker + bridge ---
        self.bridge = WorkerBridge()
        self.worker = DictationWorker(
            on_state_change=self.bridge.emit_state,
            on_transcription=self.bridge.emit_transcription,
            on_log=self.bridge.emit_log,
        )
        # load vocabulary at startup
        self.worker.vocabulary = vocabulary.load()

        # --- Pages ---
        self.home = HomeTab()
        self.history_tab = HistoryTab()
        self.vocab_tab = VocabTab()
        models = ["llama3.1:8b", "qwen2.5:7b", "gemma2:9b"] if demo else _list_ollama_models()
        self.settings_tab = SettingsTab(models)

        self.pages = QStackedWidget()
        for page in (self.home, self.history_tab, self.vocab_tab, self.settings_tab):
            self.pages.addWidget(page)
        sidebar, self.nav = _build_sidebar()
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.nav.setCurrentRow(0)

        central = QWidget()
        row = QHBoxLayout(central)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(sidebar)
        row.addWidget(self.pages, 1)
        self.setCentralWidget(central)

        # --- Overlay ---
        self.overlay = RecordingOverlay()

        # --- Status bar ---
        self.statusBar().showMessage("Ready")
        self.statusBar().setSizeGripEnabled(False)

        # --- Wiring ---
        self.home.start_btn.clicked.connect(self.start_worker)
        self.home.stop_btn.clicked.connect(self.stop_worker)
        self.home.open_log_btn.clicked.connect(self._open_log_file)
        self.home.open_log_dir_btn.clicked.connect(self._open_log_dir)
        self.home.llm_check.setChecked(self.worker.use_llm_cleanup)
        self.home.llm_check.stateChanged.connect(self.toggle_llm)
        self.home.mute_check.setChecked(self.worker.mute_audio_while_recording)
        self.home.mute_check.stateChanged.connect(self.toggle_mute)

        self.bridge.state_changed.connect(self.on_state_changed)
        self.bridge.log_received.connect(self.home.append_log)
        self.bridge.transcription_received.connect(self.on_transcription)

        self.history_tab.add_to_vocab_requested.connect(self.vocab_tab.add_external)
        self.vocab_tab.vocab_changed.connect(self.on_vocab_changed)
        self.settings_tab.settings_changed.connect(self.on_settings_changed)

        # --- Tray ---
        self.tray = QSystemTrayIcon(app_icon("idle"), self)
        self.tray.setToolTip(f"{APP_NAME} — {STATE_LABEL['idle']}")
        self.tray_menu = QMenu()
        self.act_status = QAction(f"●  {STATE_LABEL['idle']}", self)
        self.act_status.setEnabled(False)
        self.act_show = QAction(icon("window"), "Show window", self)
        self.act_start = QAction(icon("play"), "Start engine", self)
        self.act_stop = QAction(icon("stop"), "Stop engine", self)
        self.act_stop.setEnabled(False)
        self.act_quit = QAction(icon("power"), "Quit", self)
        self.act_show.triggered.connect(self.show_window)
        self.act_start.triggered.connect(self.start_worker)
        self.act_stop.triggered.connect(self.stop_worker)
        self.act_quit.triggered.connect(self.quit_app)
        self.tray_menu.addAction(self.act_status)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(self.act_show)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(self.act_start)
        self.tray_menu.addAction(self.act_stop)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(self.act_quit)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self.on_tray_activated)
        if not demo:
            self.tray.show()

        self._quitting = False

    # ---- worker control ----

    @Slot()
    def start_worker(self):
        self.home.start_btn.setEnabled(False)
        self.home.set_state("loading")
        self.statusBar().showMessage("Loading Whisper model…")
        QApplication.processEvents()
        try:
            self.worker.start()
            self.home.stop_btn.setEnabled(True)
        except Exception as e:
            log.exception("worker.start failed")
            self.home.set_state(self.worker.state)
            QMessageBox.critical(
                self,
                "Could not start",
                f"{e}\n\nFull details in the log:\n{logging_setup.log_file()}",
            )
        finally:
            self.home.start_btn.setEnabled(True)

    def _open_log_file(self):
        path = logging_setup.log_file()
        try:
            os.startfile(str(path))
        except Exception as e:
            QMessageBox.warning(self, "Open log", f"Cannot open {path}: {e}")

    def _open_log_dir(self):
        path = logging_setup.log_dir()
        try:
            os.startfile(str(path))
        except Exception as e:
            QMessageBox.warning(self, "Log folder", f"Cannot open {path}: {e}")

    @Slot()
    def stop_worker(self):
        self.worker.stop()
        self.home.start_btn.setEnabled(True)
        self.home.stop_btn.setEnabled(False)

    @Slot(int)
    def toggle_llm(self, state: int):
        self.worker.use_llm_cleanup = bool(state)

    @Slot(int)
    def toggle_mute(self, state: int):
        self.worker.mute_audio_while_recording = bool(state)

    # ---- bridge handlers ----

    @Slot(str)
    def on_state_changed(self, s: str):
        self.home.set_state(s)
        label = STATE_LABEL.get(s, s)
        self.statusBar().showMessage(label)
        ic = app_icon(s)
        self.tray.setIcon(ic)
        self.tray.setToolTip(f"{APP_NAME} — {label}")
        self.setWindowIcon(ic)
        self.act_status.setText(f"●  {label}")
        running = s != "idle"
        self.act_start.setEnabled(not running)
        self.act_stop.setEnabled(running)
        self.home.stop_btn.setEnabled(running)
        if s == "recording":
            self.overlay.show_recording()
        elif s == "processing":
            self.overlay.show_processing()
        else:
            self.overlay.hide_recording()

    @Slot(object)
    def on_transcription(self, r: TranscriptionResult):
        # persist
        try:
            history.insert(
                r.text_raw, r.text_final, r.used_llm,
                r.stt_seconds, r.llm_seconds,
            )
        except Exception as e:
            print(f"[history] insert error: {e}", file=sys.stderr)
        # show at the top of the list (no full reload) and on Home
        self.history_tab.add_session_transcription(r)
        self.home.set_last_transcription(
            r.text_final, format_meta(r.timestamp, r.stt_seconds, r.used_llm, r.llm_seconds))

    @Slot(list)
    def on_vocab_changed(self, items: list):
        self.worker.vocabulary = items

    @Slot(dict)
    def on_settings_changed(self, cfg: dict):
        # update in-memory config + propagate to the worker where possible
        if "OLLAMA_MODEL" in cfg:
            config.OLLAMA_MODEL = cfg["OLLAMA_MODEL"]
        if "LANGUAGE" in cfg:
            config.LANGUAGE = cfg["LANGUAGE"]
        if "WHISPER_MODEL" in cfg:
            config.WHISPER_MODEL = cfg["WHISPER_MODEL"]
            # requires an app restart to reload the model
        self.home.refresh_engine_label()

    # ---- tray ----

    @Slot()
    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    @Slot()
    def quit_app(self):
        self._quitting = True
        try:
            self.worker.stop()
        except Exception:
            pass
        try:
            self.overlay.hide_recording()
            self.overlay.deleteLater()
        except Exception:
            pass
        QApplication.instance().quit()

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.show_window()

    def closeEvent(self, event):
        if self._quitting or self._demo:
            event.accept()
            return
        event.ignore()
        self.hide()
        self.tray.showMessage(
            APP_NAME,
            "Still running in the background. Right-click the tray icon to quit.",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )


def main():
    # logging already initialised at import time
    log.info("creating QApplication")
    app = QApplication(sys.argv)
    logging_setup.install_qt_handler()
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    theme.apply(app)

    if DEMO_MODE:
        import demo
        idx = sys.argv.index("--screenshot")
        nxt = sys.argv[idx + 1] if len(sys.argv) > idx + 1 else ""
        out = nxt if nxt and not nxt.startswith("-") else None
        sys.exit(demo.run(app, MainWindow, out))

    # Warm up pyperclip on the main thread: the first copy() does a heavy lazy
    # init (determine_clipboard → comtypes) and doing it on a non-main thread
    # causes an access violation during GC. Force it here, on the main thread.
    try:
        import pyperclip
        pyperclip.copy(pyperclip.paste())
        log.info("pyperclip warm-up ok")
    except Exception:
        log.exception("pyperclip warm-up failed (continuing)")
    try:
        w = MainWindow()
        w.show()
    except Exception:
        log.exception("MainWindow init failed")
        raise
    log.info("entering event loop")
    rc = app.exec()
    log.info("event loop exited rc=%s", rc)
    sys.exit(rc)


if __name__ == "__main__":
    main()
