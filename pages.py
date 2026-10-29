"""The four pages of the main window: Home, History, Vocabulary, Settings.

Pure UI layer. Public attributes, signals and methods used by MainWindow
(start_btn, stop_btn, llm_check, add_to_vocab_requested, vocab_changed,
settings_changed, ...) keep the names they had before the redesign.
"""
from __future__ import annotations

import os
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QFrame, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
    QPushButton, QSizePolicy, QSplitter, QStackedWidget, QVBoxLayout, QWidget,
)

import autostart
import config
import history
import theme
import vocabulary
from widgets import (
    HistoryItemDelegate, KeyCombo, StatusDot, card, icon, label, repolish, set_variant,
)

# Copy for every engine state. "loading" is UI-only (shown while the model loads).
STATE_TEXT = {
    "idle": ("Paused",
             "Start the engine to load the speech model and enable the hotkey."),
    "loading": ("Loading model…",
                "The Whisper model is being loaded (GPU, with CPU fallback). First start can take a while."),
    "listening": ("Ready",
                  "Hold the hotkey in any app, speak, release. The text is pasted at your cursor."),
    "recording": ("Recording",
                  "Speak now. Release the keys to transcribe."),
    "processing": ("Transcribing…",
                   "Speech-to-text is running locally on this machine."),
}
STATE_LABEL = {k: v[0] for k, v in STATE_TEXT.items()}


def _page() -> tuple[QWidget, QVBoxLayout]:
    w = QWidget()
    w.setObjectName("Page")
    lay = QVBoxLayout(w)
    lay.setContentsMargins(theme.SPACE["xxl"], theme.SPACE["xl"], theme.SPACE["xxl"], theme.SPACE["xl"])
    lay.setSpacing(theme.SPACE["lg"])
    return w, lay


def _header(title: str, subtitle: str = "") -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, theme.SPACE["xs"])
    lay.setSpacing(2)
    lay.addWidget(label(title, "pageTitle"))
    if subtitle:
        lay.addWidget(label(subtitle, "muted", wrap=True))
    return w


def _section_row(title: str) -> tuple[QHBoxLayout, QLabel]:
    row = QHBoxLayout()
    row.setSpacing(theme.SPACE["sm"])
    t = label(title.upper(), "sectionTitle")
    row.addWidget(t)
    row.addStretch()
    return row, t


def format_meta(ts: float, stt_seconds: float, used_llm: bool, llm_seconds: float = 0.0) -> str:
    when = datetime.fromtimestamp(ts).strftime("%d %b %Y · %H:%M")
    parts = [when, f"{stt_seconds:.1f} s speech-to-text"]
    if used_llm:
        parts.append(f"LLM cleanup {llm_seconds:.1f} s")
    return "  ·  ".join(parts)


def _engine_summary() -> str:
    lang = "auto-detect (" + "/".join(config.AUTO_LANGUAGES) + ")" if config.LANGUAGE == "auto" else config.LANGUAGE
    return f"faster-whisper {config.WHISPER_MODEL} · {config.WHISPER_DEVICE} · {lang}"


# =====================================================================
# HOME
# =====================================================================
class HomeTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        page, lay = _page()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page)

        # ---- status card (hero) ------------------------------------
        self.status_card = QFrame()
        self.status_card.setObjectName("StatusCard")
        sc = QVBoxLayout(self.status_card)
        sc.setContentsMargins(theme.SPACE["xl"], theme.SPACE["xl"], theme.SPACE["xl"], theme.SPACE["lg"])
        sc.setSpacing(theme.SPACE["lg"])

        top = QHBoxLayout()
        top.setSpacing(theme.SPACE["md"])
        self.dot = StatusDot(14)
        top.addWidget(self.dot, 0, Qt.AlignmentFlag.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(4)
        self.state_label = QLabel(STATE_LABEL["idle"])
        self.state_label.setObjectName("StatusTitle")
        self.state_hint = QLabel(STATE_TEXT["idle"][1])
        self.state_hint.setObjectName("StatusHint")
        self.state_hint.setWordWrap(True)
        texts.addWidget(self.state_label)
        texts.addWidget(self.state_hint)
        top.addLayout(texts, 1)

        hk = QVBoxLayout()
        hk.setSpacing(6)
        hk_caption = label("HOLD TO DICTATE", "sectionTitle")
        hk_caption.setAlignment(Qt.AlignmentFlag.AlignRight)
        hk.addWidget(hk_caption)
        hk.addWidget(KeyCombo(config.HOTKEY_KEYS))
        top.addLayout(hk)
        sc.addLayout(top)

        actions = QHBoxLayout()
        actions.setSpacing(theme.SPACE["sm"])
        self.start_btn = QPushButton("Start engine")
        self.start_btn.setIcon(icon("play", "accent_text"))
        set_variant(self.start_btn, "primary")
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setIcon(icon("stop", "danger"))
        set_variant(self.stop_btn, "danger")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setVisible(False)
        for b in (self.start_btn, self.stop_btn):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setMinimumHeight(40)
        actions.addWidget(self.start_btn)
        actions.addWidget(self.stop_btn)
        actions.addStretch()
        self.engine_label = label(_engine_summary(), "caption")
        actions.addWidget(self.engine_label)
        sc.addLayout(actions)
        lay.addWidget(self.status_card)

        # ---- last transcription ------------------------------------
        last, ll = card()
        row, _ = _section_row("Last transcription")
        self.last_meta = label("", "caption")
        row.addWidget(self.last_meta)
        self.copy_last_btn = QPushButton("Copy")
        self.copy_last_btn.setIcon(icon("copy"))
        set_variant(self.copy_last_btn, "ghost")
        self.copy_last_btn.setEnabled(False)
        self.copy_last_btn.clicked.connect(self._copy_last)
        row.addWidget(self.copy_last_btn)
        ll.addLayout(row)
        self.last_text = QLabel(
            "Nothing dictated yet. Start the engine, hold "
            f"{config.HOTKEY_LABEL} in any text field, speak, then release."
        )
        self.last_text.setObjectName("Transcript")
        self.last_text.setProperty("role", "muted")
        self.last_text.setWordWrap(True)
        self.last_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.last_text.setMinimumHeight(56)
        self.last_text.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        ll.addWidget(self.last_text)
        lay.addWidget(last)

        # ---- options ------------------------------------------------
        opts, ol = card()
        row, _ = _section_row("Options")
        ol.addLayout(row)
        self.llm_check = QCheckBox("Clean up punctuation with a local LLM (Ollama)")
        self.mute_check = QCheckBox("Mute speakers while recording")
        ol.addWidget(self.llm_check)
        ol.addWidget(self.mute_check)
        lay.addWidget(opts)

        # ---- activity log (collapsed by default) --------------------
        logc, lgl = card()
        row, _ = _section_row("Activity log")
        self.open_log_btn = QPushButton("Open log")
        self.open_log_btn.setIcon(icon("file"))
        self.open_log_dir_btn = QPushButton("Log folder")
        self.open_log_dir_btn.setIcon(icon("folder"))
        self.toggle_log_btn = QPushButton("Show")
        for b in (self.open_log_btn, self.open_log_dir_btn, self.toggle_log_btn):
            set_variant(b, "ghost")
            row.addWidget(b)
        lgl.addLayout(row)
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("LogView")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        self.log_view.setMinimumHeight(120)
        self.log_view.setVisible(False)
        self.toggle_log_btn.clicked.connect(self._toggle_log)
        lgl.addWidget(self.log_view, 1)
        self.log_card = logc
        logc.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        lay.addWidget(logc)
        lay.addStretch()

        self.set_state("idle")

    def _toggle_log(self):
        vis = not self.log_view.isVisible()
        self.log_view.setVisible(vis)
        self.log_card.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding if vis else QSizePolicy.Policy.Maximum)
        self.toggle_log_btn.setText("Hide" if vis else "Show")

    def set_state(self, s: str):
        title, hint = STATE_TEXT.get(s, (s, ""))
        self.state_label.setText(title)
        self.state_hint.setText(hint)
        self.status_card.setProperty("state", s)
        repolish(self.status_card)
        self.dot.set_state(s)
        running = s not in ("idle", "loading")
        self.start_btn.setVisible(not running)
        self.stop_btn.setVisible(running)
        if s == "loading":
            self.start_btn.setText("Loading…")
        else:
            self.start_btn.setText("Start engine")

    def refresh_engine_label(self):
        self.engine_label.setText(_engine_summary())

    def set_last_transcription(self, text: str, meta: str):
        self.last_text.setText(text)
        self.last_text.setProperty("role", None)
        repolish(self.last_text)
        self.last_meta.setText(meta)
        self.copy_last_btn.setEnabled(bool(text))

    def _copy_last(self):
        QGuiApplication.clipboard().setText(self.last_text.text())

    def append_log(self, msg: str):
        self.log_view.appendPlainText(msg)
        c = self.log_view.textCursor()
        c.movePosition(QTextCursor.MoveOperation.End)
        self.log_view.setTextCursor(c)


# =====================================================================
# HISTORY
# =====================================================================
class HistoryTab(QWidget):
    """Searchable history (master/detail). Select words in the transcript →
    "Add to vocabulary"."""
    add_to_vocab_requested = Signal(str)  # term

    def __init__(self, parent=None):
        super().__init__(parent)
        page, lay = _page()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page)

        head = QHBoxLayout()
        head.addWidget(_header("History", "Every dictation is stored locally in SQLite. Nothing leaves this PC."), 1)
        self.count_label = label("", "caption")
        head.addWidget(self.count_label, 0, Qt.AlignmentFlag.AlignBottom)
        lay.addLayout(head)

        search_row = QHBoxLayout()
        search_row.setSpacing(theme.SPACE["sm"])
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search transcriptions…")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.textChanged.connect(self.refresh)
        search_row.addWidget(self.search_box)
        self.refresh_btn = QPushButton()
        self.refresh_btn.setIcon(icon("refresh"))
        self.refresh_btn.setToolTip("Reload from disk")
        self.refresh_btn.setFixedWidth(40)
        self.refresh_btn.clicked.connect(self.refresh)
        search_row.addWidget(self.refresh_btn)
        lay.addLayout(search_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # list / empty state
        self.list_stack = QStackedWidget()
        self.list_widget = QListWidget()
        self.list_widget.setObjectName("List")
        self.list_widget.setItemDelegate(HistoryItemDelegate(self.list_widget))
        self.list_widget.setMouseTracking(True)
        self.list_widget.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_widget.setUniformItemSizes(True)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.list_widget.currentItemChanged.connect(lambda cur, _prev: cur and self._on_item_clicked(cur))
        self.empty_label = label("No transcriptions yet.\nYour dictations will appear here.", "empty", wrap=True)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.list_stack.addWidget(self.list_widget)
        self.list_stack.addWidget(self.empty_label)
        self.list_stack.setMinimumWidth(320)
        splitter.addWidget(self.list_stack)

        # detail
        detail_card, dl = card()
        row, _ = _section_row("Transcript")
        dl.addLayout(row)
        self.detail_meta = label("", "caption", wrap=True)
        dl.addWidget(self.detail_meta)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setPlaceholderText("Select a transcription to read it here.")
        dl.addWidget(self.detail, 1)
        action_row = QHBoxLayout()
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setIcon(icon("copy"))
        self.copy_btn.clicked.connect(
            lambda: QGuiApplication.clipboard().setText(self.detail.toPlainText()))
        self.add_word_btn = QPushButton("Add selection to vocabulary")
        self.add_word_btn.setIcon(icon("plus"))
        self.add_word_btn.setToolTip("Select a word or phrase above first")
        self.add_word_btn.clicked.connect(self._on_add_word)
        action_row.addWidget(self.copy_btn)
        action_row.addStretch()
        action_row.addWidget(self.add_word_btn)
        dl.addLayout(action_row)
        splitter.addWidget(detail_card)
        splitter.setSizes([420, 420])
        lay.addWidget(splitter, 1)

        self.refresh()

    @staticmethod
    def _make_item(d: dict) -> QListWidgetItem:
        d = dict(d)
        d["_meta"] = format_meta(d["ts"], d.get("stt_seconds", 0.0), bool(d.get("used_llm")),
                                 d.get("llm_seconds", 0.0))
        item = QListWidgetItem(d["text_final"])
        item.setData(Qt.ItemDataRole.UserRole, d)
        return item

    def _update_empty_state(self):
        n = self.list_widget.count()
        self.list_stack.setCurrentIndex(0 if n else 1)
        searching = bool(self.search_box.text().strip())
        if not n and searching:
            self.empty_label.setText("No transcriptions match your search.")
        elif not n:
            self.empty_label.setText("No transcriptions yet.\nYour dictations will appear here.")
        self.count_label.setText(f"{n} shown" if searching else f"{n} transcriptions")

    def refresh(self):
        self.list_widget.clear()
        rows = history.list_recent(limit=500, search=self.search_box.text().strip())
        for r in rows:
            self.list_widget.addItem(self._make_item(dict(r)))
        self._update_empty_state()

    def _on_item_clicked(self, item: QListWidgetItem):
        data = item.data(Qt.ItemDataRole.UserRole)
        self.detail.setPlainText(data["text_final"])
        self.detail_meta.setText(data.get("_meta", ""))

    def _on_add_word(self):
        sel = self.detail.textCursor().selectedText().strip()
        if not sel:
            QMessageBox.information(
                self, "Nothing selected",
                "Select a word or phrase in the transcript first."
            )
            return
        # let the user fix the spelling before saving
        text, ok = QInputDialog.getText(
            self, "Add to vocabulary",
            "Correct spelling to remember (Whisper will prefer this form):",
            text=sel,
        )
        if ok and text.strip():
            self.add_to_vocab_requested.emit(text.strip())

    def add_session_transcription(self, r):
        # prepend without reloading everything
        self.list_widget.insertItem(0, self._make_item({
            "ts": r.timestamp,
            "text_raw": r.text_raw,
            "text_final": r.text_final,
            "used_llm": int(r.used_llm),
            "stt_seconds": r.stt_seconds,
            "llm_seconds": r.llm_seconds,
        }))
        self._update_empty_state()


# =====================================================================
# VOCABULARY
# =====================================================================
class VocabTab(QWidget):
    vocab_changed = Signal(list)  # new list

    def __init__(self, parent=None):
        super().__init__(parent)
        page, lay = _page()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page)

        lay.addWidget(_header(
            "Vocabulary",
            "Words Whisper should prefer: names, acronyms, product and technical terms. "
            "They are added to the model's initial prompt on every dictation.",
        ))

        add_row = QHBoxLayout()
        add_row.setSpacing(theme.SPACE["sm"])
        self.input = QLineEdit()
        self.input.setPlaceholderText("Add a term, e.g. PySide6")
        self.input.returnPressed.connect(self._on_add)
        add_row.addWidget(self.input)
        self.add_btn = QPushButton("Add")
        self.add_btn.setIcon(icon("plus", "accent_text"))
        set_variant(self.add_btn, "primary")
        self.add_btn.clicked.connect(self._on_add)
        add_row.addWidget(self.add_btn)
        lay.addLayout(add_row)

        self.stack = QStackedWidget()
        self.list_widget = QListWidget()
        self.list_widget.setObjectName("List")
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.list_widget.currentItemChanged.connect(
            lambda cur, _prev: self.remove_btn.setEnabled(cur is not None))
        self.empty_label = label("No custom terms yet.\nAdd names or jargon Whisper tends to misspell.",
                                 "empty", wrap=True)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stack.addWidget(self.list_widget)
        self.stack.addWidget(self.empty_label)
        lay.addWidget(self.stack, 1)

        rm_row = QHBoxLayout()
        self.count_label = label("", "caption")
        rm_row.addWidget(self.count_label)
        rm_row.addStretch()
        self.remove_btn = QPushButton("Remove selected")
        self.remove_btn.setIcon(icon("trash"))
        self.remove_btn.setEnabled(False)
        self.remove_btn.clicked.connect(self._on_remove)
        rm_row.addWidget(self.remove_btn)
        lay.addLayout(rm_row)

        self.refresh()

    def refresh(self):
        self.list_widget.clear()
        terms = vocabulary.load()
        for term in terms:
            self.list_widget.addItem(term)
        self.stack.setCurrentIndex(0 if terms else 1)
        self.count_label.setText(f"{len(terms)} terms")
        self.remove_btn.setEnabled(False)

    def _on_add(self):
        term = self.input.text().strip()
        if not term:
            return
        items = vocabulary.add(term)
        self.input.clear()
        self.refresh()
        self.vocab_changed.emit(items)

    def add_external(self, term: str):
        items = vocabulary.add(term)
        self.refresh()
        self.vocab_changed.emit(items)

    def _on_remove(self):
        item = self.list_widget.currentItem()
        if item is None:
            return
        items = vocabulary.remove(item.text())
        self.refresh()
        self.vocab_changed.emit(items)


# =====================================================================
# SETTINGS
# =====================================================================
def _data_dir_display() -> str:
    if os.environ.get("DICTATION_DEMO"):
        return "data\\  (next to the app)"
    return str(config.DATA_DIR)


class SettingsTab(QWidget):
    settings_changed = Signal(dict)

    def __init__(self, available_ollama_models: list[str], parent=None):
        super().__init__(parent)
        page, lay = _page()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(page)

        lay.addWidget(_header("Settings"))

        def form_card(title: str):
            c, cl = card()
            row, _ = _section_row(title)
            cl.addLayout(row)
            form = QFormLayout()
            form.setHorizontalSpacing(theme.SPACE["xl"])
            form.setVerticalSpacing(theme.SPACE["md"])
            form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            cl.addLayout(form)
            return c, cl, form

        # transcription
        c, cl, form = form_card("Transcription")
        self.whisper_combo = QComboBox()
        self.whisper_combo.addItems(["tiny", "base", "small", "medium", "large-v3"])
        idx = self.whisper_combo.findText(config.WHISPER_MODEL)
        if idx >= 0:
            self.whisper_combo.setCurrentIndex(idx)
        form.addRow("Whisper model", self.whisper_combo)
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["auto", "it", "en"])
        idx = self.lang_combo.findText(config.LANGUAGE)
        if idx >= 0:
            self.lang_combo.setCurrentIndex(idx)
        form.addRow("Language", self.lang_combo)
        cl.addWidget(label("Changing the Whisper model takes effect after restarting the app.", "caption", wrap=True))
        lay.addWidget(c)

        # llm
        c, cl, form = form_card("LLM cleanup (optional)")
        self.ollama_combo = QComboBox()
        if available_ollama_models:
            self.ollama_combo.addItems(available_ollama_models)
            idx = self.ollama_combo.findText(config.OLLAMA_MODEL)
            if idx >= 0:
                self.ollama_combo.setCurrentIndex(idx)
        else:
            self.ollama_combo.addItem(config.OLLAMA_MODEL)
        form.addRow("Ollama model", self.ollama_combo)
        cl.addWidget(label("Uses a local Ollama server (localhost:11434). Turn it on from Home → Options.",
                           "caption", wrap=True))
        lay.addWidget(c)

        # hotkey + system
        c, cl, form = form_card("Hotkey & system")
        form.addRow("Push-to-talk", KeyCombo(config.HOTKEY_KEYS))
        self.autostart_check = QCheckBox("Start with Windows")
        self.autostart_check.setChecked(autostart.is_enabled())
        self.autostart_check.stateChanged.connect(self._on_autostart_toggled)
        form.addRow("Startup", self.autostart_check)
        data_lbl = label(_data_dir_display(), "muted")
        data_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("Data folder", data_lbl)
        lay.addWidget(c)

        save_row = QHBoxLayout()
        save_row.addStretch()
        self.save_btn = QPushButton("Save settings")
        self.save_btn.setIcon(icon("save", "accent_text"))
        set_variant(self.save_btn, "primary")
        self.save_btn.clicked.connect(self._on_save)
        save_row.addWidget(self.save_btn)
        lay.addLayout(save_row)
        lay.addStretch()

    def _on_autostart_toggled(self, state: int):
        try:
            if bool(state):
                autostart.enable()
            else:
                autostart.disable()
        except Exception as e:
            QMessageBox.warning(self, "Start with Windows", f"Error: {e}")

    def _on_save(self):
        cfg = {
            "WHISPER_MODEL": self.whisper_combo.currentText(),
            "LANGUAGE": self.lang_combo.currentText(),
            "OLLAMA_MODEL": self.ollama_combo.currentText(),
        }
        self.settings_changed.emit(cfg)
        QMessageBox.information(
            self, "Settings saved",
            "Settings saved.\nA new Whisper model is loaded after restarting the app."
        )
