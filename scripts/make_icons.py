"""Regenerate icons/app.ico and icons/tray_*.png from the runtime icon
drawing in widgets.app_pixmap(), so the .exe icon matches the in-app one.

    .venv\\Scripts\\python.exe scripts\\make_icons.py
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402
from PySide6.QtCore import QBuffer, QIODevice  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402


def _to_pil(pm) -> Image.Image:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pm.save(buf, "PNG")
    return Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA")


def main() -> int:
    app = QGuiApplication(sys.argv)  # noqa: F841  (needed for QPixmap)
    from widgets import app_pixmap

    icons = ROOT / "icons"
    big = _to_pil(app_pixmap("idle", 256))
    big.save(icons / "app.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    for state in ("idle", "listening", "recording", "processing"):
        _to_pil(app_pixmap(state, 256)).save(icons / f"tray_{state}.png")
    print("icons regenerated in", icons)
    return 0


if __name__ == "__main__":
    sys.exit(main())
