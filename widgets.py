"""Reusable UI building blocks: line icons, app/tray icon, status dot,
key caps, cards and the two-line history row delegate.

Icons are drawn with QPainter at runtime so they share one stroke style and
always use theme colours (no icon font, no extra dependency).
"""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QColor, QFontMetrics, QIcon, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget,
)

import theme


# ====================================================================== icons
def _stroke(p: QPainter, c: QColor, w: float):
    pen = QPen(c, w)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)


def _draw_glyph(p: QPainter, name: str, c: QColor, s: float):
    """Draw glyph `name` in a s x s box with a 24-unit design grid."""
    k = s / 24.0
    p.save()
    p.scale(k, k)
    _stroke(p, c, 1.8)
    if name == "mic":
        p.drawRoundedRect(QRectF(9, 3, 6, 11), 3, 3)
        path = QPainterPath()
        path.moveTo(5.5, 11)
        path.cubicTo(5.5, 19, 18.5, 19, 18.5, 11)
        p.drawPath(path)
        p.drawLine(QPointF(12, 17.5), QPointF(12, 21))
    elif name == "home":
        path = QPainterPath()
        path.moveTo(4, 11)
        path.lineTo(12, 4)
        path.lineTo(20, 11)
        path.moveTo(6, 9.5)
        path.lineTo(6, 20)
        path.lineTo(18, 20)
        path.lineTo(18, 9.5)
        p.drawPath(path)
    elif name == "history":
        p.drawEllipse(QRectF(4, 4, 16, 16))
        p.drawLine(QPointF(12, 8), QPointF(12, 12))
        p.drawLine(QPointF(12, 12), QPointF(15, 14))
    elif name == "book":
        p.drawRoundedRect(QRectF(5, 3.5, 14, 17), 2, 2)
        p.drawLine(QPointF(9, 8), QPointF(15, 8))
        p.drawLine(QPointF(9, 11.5), QPointF(15, 11.5))
    elif name == "gear":
        p.drawEllipse(QRectF(9, 9, 6, 6))
        for i in range(8):
            a = i * math.pi / 4
            p.drawLine(QPointF(12 + 6 * math.cos(a), 12 + 6 * math.sin(a)),
                       QPointF(12 + 8.5 * math.cos(a), 12 + 8.5 * math.sin(a)))
        p.drawEllipse(QRectF(6, 6, 12, 12))
    elif name == "play":
        path = QPainterPath()
        path.moveTo(8, 5)
        path.lineTo(19, 12)
        path.lineTo(8, 19)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "stop":
        p.drawRoundedRect(QRectF(6, 6, 12, 12), 2, 2)
    elif name == "copy":
        p.drawRoundedRect(QRectF(8, 8, 12, 12), 2, 2)
        path = QPainterPath()
        path.moveTo(5, 15)
        path.lineTo(4, 15)
        path.lineTo(4, 4)
        path.lineTo(15, 4)
        path.lineTo(15, 5)
        p.drawPath(path)
    elif name == "folder":
        path = QPainterPath()
        path.moveTo(3.5, 7)
        path.lineTo(3.5, 19)
        path.lineTo(20.5, 19)
        path.lineTo(20.5, 8.5)
        path.lineTo(11.5, 8.5)
        path.lineTo(9.5, 5.5)
        path.lineTo(3.5, 5.5)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "file":
        path = QPainterPath()
        path.moveTo(6, 3.5)
        path.lineTo(14, 3.5)
        path.lineTo(18, 7.5)
        path.lineTo(18, 20.5)
        path.lineTo(6, 20.5)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(9, 12), QPointF(15, 12))
        p.drawLine(QPointF(9, 15.5), QPointF(15, 15.5))
    elif name == "refresh":
        p.drawArc(QRectF(5, 5, 14, 14), 30 * 16, 290 * 16)
        path = QPainterPath()
        path.moveTo(19.5, 4.5)
        path.lineTo(18.6, 9)
        path.lineTo(14.2, 8)
        p.drawPath(path)
    elif name == "plus":
        p.drawLine(QPointF(12, 5), QPointF(12, 19))
        p.drawLine(QPointF(5, 12), QPointF(19, 12))
    elif name == "trash":
        p.drawLine(QPointF(4.5, 7), QPointF(19.5, 7))
        p.drawLine(QPointF(10, 4), QPointF(14, 4))
        p.drawRoundedRect(QRectF(6.5, 7, 11, 13), 1.5, 1.5)
    elif name == "save":
        p.drawRoundedRect(QRectF(4.5, 4.5, 15, 15), 2, 2)
        p.drawRect(QRectF(8.5, 4.5, 7, 5))
        p.drawRect(QRectF(8, 13, 8, 6.5))
    elif name == "window":
        p.drawRoundedRect(QRectF(3.5, 5, 17, 14), 2, 2)
        p.drawLine(QPointF(3.5, 9), QPointF(20.5, 9))
    elif name == "power":
        p.drawArc(QRectF(5, 5.5, 14, 14), 120 * 16, -240 * 16)
        p.drawLine(QPointF(12, 3.5), QPointF(12, 11))
    p.restore()


def icon(name: str, color_token: str = "text_muted", size: int = 18) -> QIcon:
    """Line icon tinted with a theme token, rendered at 1x and 2x."""
    ic = QIcon()
    for scale in (1, 2):
        pm = QPixmap(size * scale, size * scale)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        _draw_glyph(p, name, theme.color(color_token), size * scale)
        p.end()
        pm.setDevicePixelRatio(scale)
        ic.addPixmap(pm)
    return ic


def app_pixmap(state: str = "idle", size: int = 64) -> QPixmap:
    """App / tray icon: rounded tile with a microphone, tinted by state."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    tile = QRectF(size * 0.04, size * 0.04, size * 0.92, size * 0.92)
    base = QColor("#14161a")
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(base)
    p.drawRoundedRect(tile, size * 0.24, size * 0.24)
    accent = QColor(theme.DARK["state_" + state]) if state != "idle" else QColor(theme.DARK["accent"])
    p.translate(size * 0.14, size * 0.12)
    _draw_glyph(p, "mic", accent, size * 0.72)
    p.resetTransform()
    if state in ("listening", "recording", "processing"):
        r = size * 0.13
        p.setPen(QPen(base, size * 0.05))
        p.setBrush(accent)
        p.drawEllipse(QPointF(size * 0.80, size * 0.80), r, r)
    p.end()
    return pm


def app_icon(state: str = "idle") -> QIcon:
    ic = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(app_pixmap(state, s))
    return ic


# ====================================================================== status dot
class StatusDot(QWidget):
    """Coloured dot; pulses softly while recording / processing."""

    def __init__(self, diameter: int = 14, parent=None):
        super().__init__(parent)
        self._d = diameter
        self._state = "idle"
        self._t0 = time.monotonic()
        self.setFixedSize(diameter * 3, diameter * 3)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self.update)

    def set_state(self, state: str):
        self._state = state
        animated = state in ("recording", "processing", "loading")
        if animated and not self._timer.isActive():
            self._t0 = time.monotonic()
            self._timer.start()
        elif not animated:
            self._timer.stop()
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = theme.state_color(self._state)
        center = QPointF(self.width() / 2, self.height() / 2)
        r = self._d / 2
        if self._timer.isActive():
            phase = ((time.monotonic() - self._t0) % 1.4) / 1.4
            halo = QColor(c)
            halo.setAlphaF(0.35 * (1 - phase))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(halo)
            hr = r + r * 1.6 * phase
            p.drawEllipse(center, hr, hr)
        elif self._state == "listening":
            halo = QColor(c)
            halo.setAlphaF(0.22)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(halo)
            p.drawEllipse(center, r * 1.7, r * 1.7)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawEllipse(center, r, r)
        p.end()


# ====================================================================== key caps
class KeyCombo(QWidget):
    """Renders a hotkey as key caps:  [Ctrl] + [Win]"""

    def __init__(self, keys: list[str], parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.SPACE["sm"])
        for i, k in enumerate(keys):
            if i:
                plus = QLabel("+")
                plus.setObjectName("KeyPlus")
                row.addWidget(plus)
            cap = QLabel(k)
            cap.setObjectName("KeyCap")
            cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row.addWidget(cap)
        row.addStretch()


# ====================================================================== layout helpers
def card(parent=None, margins: int | None = None) -> tuple[QFrame, QVBoxLayout]:
    f = QFrame(parent)
    f.setObjectName("Card")
    lay = QVBoxLayout(f)
    m = theme.SPACE["lg"] if margins is None else margins
    lay.setContentsMargins(m, m, m, m)
    lay.setSpacing(theme.SPACE["md"])
    return f, lay


def label(text: str = "", role: str | None = None, wrap: bool = False) -> QLabel:
    lb = QLabel(text)
    if role:
        lb.setProperty("role", role)
    lb.setWordWrap(wrap)
    return lb


def set_variant(btn, variant: str):
    btn.setProperty("variant", variant)
    repolish(btn)


def repolish(w: QWidget):
    w.style().unpolish(w)
    w.style().polish(w)
    w.update()


# ====================================================================== history row
class HistoryItemDelegate(QStyledItemDelegate):
    """Two-line row: transcript preview (2 lines max) + muted metadata."""

    PAD = 12

    def sizeHint(self, option, index):
        fm_text = QFontMetrics(theme.font("body"))
        fm_meta = QFontMetrics(theme.font("caption"))
        h = self.PAD * 2 + fm_text.lineSpacing() * 2 + 6 + fm_meta.height()
        return QSize(1, h)  # width follows the viewport

    def paint(self, p: QPainter, option, index):
        data = index.data(Qt.ItemDataRole.UserRole) or {}
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(option.rect)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.color("accent", 0.16))
            p.drawRoundedRect(r.adjusted(4, 2, -4, -2), 8, 8)
            p.setBrush(theme.color("accent"))
            p.drawRoundedRect(QRectF(r.left() + 4, r.top() + 10, 3, r.height() - 20), 1.5, 1.5)
        elif hovered:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.color("surface_hover"))
            p.drawRoundedRect(r.adjusted(4, 2, -4, -2), 8, 8)
        else:
            p.setPen(QPen(theme.color("border"), 1))
            p.drawLine(r.bottomLeft() + QPointF(self.PAD, 0), r.bottomRight() - QPointF(self.PAD, 0))

        inner = r.adjusted(self.PAD + 6, self.PAD, -self.PAD, -self.PAD)
        f_text = theme.font("body")
        fm = QFontMetrics(f_text)
        text_rect = QRectF(inner.left(), inner.top(), inner.width(), fm.lineSpacing() * 2)
        text = " ".join(str(data.get("text_final", "")).split())
        p.setFont(f_text)
        p.setPen(theme.color("text"))
        # elide to two lines
        lines, rest = [], text
        for i in range(2):
            if not rest:
                break
            if i == 1:
                lines.append(fm.elidedText(rest, Qt.TextElideMode.ElideRight, int(inner.width())))
                break
            n = len(rest)
            while n > 0 and fm.horizontalAdvance(rest[:n]) > inner.width():
                n = rest.rfind(" ", 0, n)
                if n <= 0:
                    n = len(rest)
                    break
            lines.append(rest[:n])
            rest = rest[n:].lstrip()
        for i, ln in enumerate(lines):
            p.drawText(QRectF(text_rect.left(), text_rect.top() + i * fm.lineSpacing(),
                              text_rect.width(), fm.lineSpacing()),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, ln)

        meta = data.get("_meta", "")
        p.setFont(theme.font("caption"))
        p.setPen(theme.color("text_faint"))
        p.drawText(QRectF(inner.left(), text_rect.bottom() + 6, inner.width(), inner.bottom() - text_rect.bottom() - 6),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, meta)
        p.restore()
