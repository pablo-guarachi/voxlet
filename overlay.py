"""Floating overlay shown while recording and transcribing.

Frameless, translucent, always on top, never steals focus (the text must be
pasted into the app the user is typing in). Drag with the left mouse button,
right-click to rotate horizontal/vertical or reset the position. Position and
orientation persist via QSettings.

States
- recording:  pulsing red dot + animated activity bars + elapsed time
- processing: amber spinner + "Transcribing…"
The bars are a decorative "you are being heard" cue, not a level meter: the
audio stream is owned by the worker thread and is intentionally not touched.
"""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QPoint, QPointF, QRectF, QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QApplication, QMenu, QWidget

import config
import theme

SIZE_HORIZONTAL = QSize(236, 56)
SIZE_VERTICAL = QSize(56, 208)
FRAME_MS = 33  # ~30 fps, only while visible


class RecordingOverlay(QWidget):
    def __init__(self):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self._settings = QSettings(config.APP_ID, "overlay")
        self._migrate_legacy_settings()
        self._orientation = self._settings.value("orientation", "horizontal", type=str)
        self._mode = "recording"  # or "processing"
        self._t0 = time.monotonic()
        self._frozen_t: float | None = None  # screenshot mode: fixed frame
        self._drag_offset: QPoint | None = None

        self._apply_size()
        self._restore_position()

        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self.update)

    def _migrate_legacy_settings(self):
        """Copy position/orientation saved under an old app name (once)."""
        if self._settings.allKeys():
            return
        for org in config.LEGACY_QSETTINGS_ORGS:
            old = QSettings(org, "overlay")
            keys = old.allKeys()
            if keys:
                for k in keys:
                    self._settings.setValue(k, old.value(k))
                self._settings.sync()
                return

    # ---- public API ----

    def show_recording(self):
        self._set_mode("recording", restart_clock=True)

    def show_processing(self):
        self._set_mode("processing", restart_clock=False)

    def hide_recording(self):
        self._timer.stop()
        self.hide()

    def freeze_frame(self, mode: str, seconds: float, orientation: str | None = None):
        """Render a fixed frame without showing the window (screenshots)."""
        self._mode = mode
        self._frozen_t = seconds
        if orientation:
            self._orientation = orientation
            self._apply_size()
        self.update()

    def _set_mode(self, mode: str, restart_clock: bool):
        self._mode = mode
        if restart_clock or not self.isVisible():
            self._t0 = time.monotonic()
        self._timer.start()
        self.show()
        self.raise_()
        self.update()

    def _elapsed(self) -> float:
        if self._frozen_t is not None:
            return self._frozen_t
        return time.monotonic() - self._t0

    # ---- orientation / size ----

    def _apply_size(self):
        if self._orientation == "vertical":
            self.setFixedSize(SIZE_VERTICAL)
        else:
            self.setFixedSize(SIZE_HORIZONTAL)

    def toggle_orientation(self):
        self._orientation = "vertical" if self._orientation == "horizontal" else "horizontal"
        self._settings.setValue("orientation", self._orientation)
        # keep the centre while rotating
        center = self.geometry().center()
        self._apply_size()
        rect = self.geometry()
        rect.moveCenter(center)
        self._clamp_to_screen(rect)
        self.move(rect.topLeft())
        self._save_position()
        self.update()

    # ---- persistence ----

    def _restore_position(self):
        pos = self._settings.value("pos")
        if pos is None:
            # default: bottom-right corner of the primary screen
            screen = QApplication.primaryScreen().availableGeometry()
            x = screen.right() - self.width() - 30
            y = screen.bottom() - self.height() - 50
            self.move(x, y)
        else:
            self.move(pos)
            # make sure it is still on screen (e.g. monitor unplugged)
            self._clamp_to_screen(self.geometry())

    def _save_position(self):
        self._settings.setValue("pos", self.pos())

    def _clamp_to_screen(self, rect):
        screen = QApplication.primaryScreen().availableGeometry()
        if rect.right() > screen.right():
            rect.moveRight(screen.right())
        if rect.bottom() > screen.bottom():
            rect.moveBottom(screen.bottom())
        if rect.left() < screen.left():
            rect.moveLeft(screen.left())
        if rect.top() < screen.top():
            rect.moveTop(screen.top())
        self.move(rect.topLeft())

    # ---- mouse: drag + context menu ----

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = ev.globalPosition().toPoint() - self.pos()
            ev.accept()

    def mouseMoveEvent(self, ev):
        if self._drag_offset is not None and ev.buttons() & Qt.MouseButton.LeftButton:
            self.move(ev.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self._drag_offset is not None:
            self._drag_offset = None
            self._save_position()

    def contextMenuEvent(self, ev):
        menu = QMenu(self)
        rotate = QAction(
            "Rotate to vertical" if self._orientation == "horizontal" else "Rotate to horizontal",
            self,
        )
        rotate.triggered.connect(self.toggle_orientation)
        menu.addAction(rotate)
        menu.addSeparator()
        reset = QAction("Reset position", self)

        def _reset():
            self._settings.remove("pos")
            self._restore_position()

        reset.triggered.connect(_reset)
        menu.addAction(reset)
        menu.exec(ev.globalPos())

    # ---- drawing ----

    def _accent(self) -> QColor:
        # the overlay always uses the dark palette: it floats over any app
        key = "state_recording" if self._mode == "recording" else "state_processing"
        return QColor(theme.DARK[key])

    def _label(self) -> str:
        return "Listening" if self._mode == "recording" else "Transcribing…"

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self._elapsed()
        accent = self._accent()
        text_c = QColor(theme.DARK["overlay_text"])

        # pill background + soft accent edge
        rect = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        radius = min(rect.width(), rect.height()) / 2
        bg = QColor(theme.DARK["overlay_bg"])
        bg.setAlpha(236)
        edge = QColor(accent)
        edge.setAlpha(150)
        p.setBrush(bg)
        p.setPen(QPen(edge, 1.5))
        p.drawRoundedRect(rect, radius, radius)

        horizontal = self._orientation == "horizontal"
        if horizontal:
            indicator_c = QPointF(28, self.height() / 2)
        else:
            indicator_c = QPointF(self.width() / 2, 28)

        if self._mode == "recording":
            self._draw_pulse_dot(p, indicator_c, accent, t)
        else:
            self._draw_spinner(p, indicator_c, accent, t)

        label_font = QFont()
        label_font.setFamilies(theme.FONT_UI)
        label_font.setPixelSize(13)
        label_font.setWeight(QFont.Weight.DemiBold)
        time_font = QFont()
        time_font.setFamilies(theme.FONT_MONO)
        time_font.setPixelSize(12)
        mins, secs = divmod(int(t), 60)
        clock = f"{mins}:{secs:02d}"

        if horizontal:
            x = 50
            if self._mode == "recording":
                self._draw_bars(p, QRectF(x, self.height() / 2 - 10, 34, 20), accent, t, horizontal=True)
                x += 46
            p.setFont(label_font)
            p.setPen(text_c)
            p.drawText(QRectF(x, 0, self.width() - x - 52, self.height()),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._label())
            if self._mode == "recording":
                p.setFont(time_font)
                dim = QColor(text_c)
                dim.setAlpha(170)
                p.setPen(dim)
                p.drawText(QRectF(self.width() - 62, 0, 40, self.height()),
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, clock)
        else:
            y = 50
            if self._mode == "recording":
                self._draw_bars(p, QRectF(self.width() / 2 - 10, y, 20, 34), accent, t, horizontal=False)
                y += 46
            span = self.height() - y - 16
            p.save()
            p.translate(self.width() / 2, y + span / 2)
            p.rotate(-90)
            p.setFont(label_font)
            p.setPen(text_c)
            p.drawText(QRectF(-span / 2, -10, span, 20), Qt.AlignmentFlag.AlignCenter, self._label())
            p.restore()

        p.end()

    @staticmethod
    def _draw_pulse_dot(p: QPainter, c: QPointF, color: QColor, t: float):
        phase = (t % 1.2) / 1.2
        halo = QColor(color)
        halo.setAlphaF(0.45 * (1 - phase))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(halo)
        r = 6 + 8 * phase
        p.drawEllipse(c, r, r)
        p.setBrush(color)
        p.drawEllipse(c, 6, 6)

    @staticmethod
    def _draw_spinner(p: QPainter, c: QPointF, color: QColor, t: float):
        track = QColor(color)
        track.setAlpha(60)
        p.setPen(QPen(track, 2.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        box = QRectF(c.x() - 8, c.y() - 8, 16, 16)
        p.drawEllipse(box)
        pen = QPen(color, 2.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        start = int((-(t * 400.0) % 360.0) * 16)
        p.drawArc(box, start, 100 * 16)

    @staticmethod
    def _draw_bars(p: QPainter, area: QRectF, color: QColor, t: float, horizontal: bool):
        n = 5
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        for i in range(n):
            # smooth pseudo-random motion: two sines with different speeds
            v = 0.5 + 0.25 * math.sin(t * 6.1 + i * 1.7) + 0.2 * math.sin(t * 9.3 + i * 0.9)
            v = max(0.18, min(1.0, v))
            if horizontal:
                w = 3.2
                gap = (area.width() - n * w) / (n - 1)
                h = area.height() * v
                x = area.left() + i * (w + gap)
                p.drawRoundedRect(QRectF(x, area.center().y() - h / 2, w, h), 1.6, 1.6)
            else:
                h = 3.2
                gap = (area.height() - n * h) / (n - 1)
                w = area.width() * v
                y = area.top() + i * (h + gap)
                p.drawRoundedRect(QRectF(area.center().x() - w / 2, y, w, h), 1.6, 1.6)
