"""Central theme: colour / spacing / typography tokens + QSS loader.

Every colour used by the UI comes from here. Widgets never hard-code hex
values: static styling lives in theme.qss (with @token placeholders), and
custom-painted widgets (overlay, status dot, icons) read `tokens()`.

Light/dark follows the Windows setting (Qt >= 6.5 colorScheme), overridable
with the env var DICTATION_THEME=light|dark.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).parent
QSS_PATH = ROOT / "theme.qss"

# ------------------------------------------------------------------ tokens
SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32}
RADIUS = {"sm": 6, "md": 10, "lg": 14, "pill": 999}

# Segoe UI Variable ships with Windows 11, Segoe UI with Windows 10.
FONT_UI = ["Segoe UI Variable Text", "Segoe UI", "Arial"]
FONT_DISPLAY = ["Segoe UI Variable Display", "Segoe UI Semibold", "Segoe UI"]
FONT_MONO = ["Cascadia Mono", "Consolas", "Courier New"]
TYPE = {"caption": 11, "body": 13, "label": 12, "title": 16, "display": 24}

DARK = {
    "bg": "#121417",
    "surface": "#1b1e23",
    "surface_alt": "#23272e",
    "surface_hover": "#2a2f37",
    "border": "#2f343c",
    "border_strong": "#424854",
    "text": "#e9ebee",
    "text_muted": "#a0a7b1",  # 6.9:1 on surface
    "text_faint": "#8a919c",  # >= 5:1 on surface and bg
    "accent": "#3fb8ae",
    "accent_hover": "#55c9bf",
    "accent_text": "#0a1715",
    "danger": "#ff6b6b",
    "state_idle": "#8b939e",
    "state_loading": "#7fa7e0",
    "state_listening": "#3ccf8e",
    "state_recording": "#ff5a5f",
    "state_processing": "#f2b544",
    "overlay_bg": "#14161a",
    "overlay_text": "#f4f5f7",
}

LIGHT = {
    "bg": "#f3f4f6",
    "surface": "#ffffff",
    "surface_alt": "#eef0f3",
    "surface_hover": "#e5e8ec",
    "border": "#dadde3",
    "border_strong": "#c3c8d0",
    "text": "#1a1d22",
    "text_muted": "#565f6b",  # 6.4:1 on surface
    "text_faint": "#646c77",  # >= 4.5:1 on surface and bg
    "accent": "#0f7a73",
    "accent_hover": "#0c6560",
    "accent_text": "#ffffff",
    "danger": "#c62f35",
    "state_idle": "#6b7480",
    "state_loading": "#3567b0",
    "state_listening": "#178a55",
    "state_recording": "#d6343a",
    "state_processing": "#a86f00",
    "overlay_bg": "#14161a",  # overlay stays dark: it floats over any app
    "overlay_text": "#f4f5f7",
}

_mode: str | None = None


def _system_is_dark() -> bool:
    forced = (os.environ.get("DICTATION_THEME") or "").lower()
    if forced in ("light", "dark"):
        return forced == "dark"
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return True


def mode() -> str:
    return _mode or ("dark" if _system_is_dark() else "light")


def tokens() -> dict:
    return DARK if mode() == "dark" else LIGHT


def color(name: str, alpha: float | None = None) -> QColor:
    c = QColor(tokens()[name])
    if alpha is not None:
        c.setAlphaF(alpha)
    return c


def state_color(state: str) -> QColor:
    return color(f"state_{state}") if f"state_{state}" in tokens() else color("state_idle")


def _rgba(hex_color: str, alpha: float) -> str:
    c = QColor(hex_color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {int(alpha * 255)})"


def _qss_values() -> dict:
    t = dict(tokens())
    # derived tints, used by the status card and selection
    for k in [k for k in t if k.startswith("state_")]:
        t[k + "_tint"] = _rgba(t[k], 0.14)
        t[k + "_edge"] = _rgba(t[k], 0.45)
    t["accent_tint"] = _rgba(t["accent"], 0.16)
    t["font_ui"] = ", ".join(f'"{f}"' for f in FONT_UI)
    t["font_display"] = ", ".join(f'"{f}"' for f in FONT_DISPLAY)
    t["font_mono"] = ", ".join(f'"{f}"' for f in FONT_MONO)
    for k, v in TYPE.items():
        t[f"fs_{k}"] = f"{v}px"
    for k, v in SPACE.items():
        t[f"sp_{k}"] = f"{v}px"
    for k, v in RADIUS.items():
        t[f"r_{k}"] = f"{v}px"
    return t


def stylesheet() -> str:
    try:
        raw = QSS_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""
    values = _qss_values()
    # longest names first so @state_idle_tint wins over @state_idle
    names = sorted(values, key=len, reverse=True)
    pattern = re.compile("@(" + "|".join(map(re.escape, names)) + r")\b")
    return pattern.sub(lambda m: str(values[m.group(1)]), raw)


def apply(app: QApplication, force_mode: str | None = None):
    """Apply Fusion style + palette + font + stylesheet to the whole app."""
    global _mode
    _mode = force_mode
    t = tokens()
    app.setStyle("Fusion")

    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(t["bg"]))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(t["text"]))
    pal.setColor(QPalette.ColorRole.Base, QColor(t["surface"]))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(t["surface_alt"]))
    pal.setColor(QPalette.ColorRole.Text, QColor(t["text"]))
    pal.setColor(QPalette.ColorRole.Button, QColor(t["surface_alt"]))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(t["text"]))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(t["accent"]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(t["accent_text"]))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(t["surface_alt"]))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(t["text"]))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(t["text_faint"]))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(t["text_faint"]))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(t["text_faint"]))
    app.setPalette(pal)

    font = QFont()
    font.setFamilies(FONT_UI)
    font.setPixelSize(TYPE["body"])
    app.setFont(font)

    app.setStyleSheet(stylesheet())


def font(kind: str = "body", weight: QFont.Weight = QFont.Weight.Normal, mono: bool = False,
         display: bool = False) -> QFont:
    f = QFont()
    f.setFamilies(FONT_MONO if mono else FONT_DISPLAY if display else FONT_UI)
    f.setPixelSize(TYPE.get(kind, TYPE["body"]))
    f.setWeight(weight)
    return f
