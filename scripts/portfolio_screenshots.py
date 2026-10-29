"""Generate the portfolio screenshots in docs/screenshots/portfolio/.

    .venv\\Scripts\\python.exe scripts\\portfolio_screenshots.py [--out DIR]

Runs the app in demo mode (app.py --screenshot): every window and state is
rendered off-screen with Qt's grab() using fake demo content, saved as PNG,
then the process exits (~15 s, mostly importing faster-whisper). Nothing appears on screen, the microphone and the
global hotkey are never opened, and the real history/vocabulary are never
read or written (demo data lives in a temp folder).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "docs" / "screenshots" / "portfolio"))
    args = ap.parse_args()

    venv_py = ROOT / ".venv" / "Scripts" / "python.exe"
    py = str(venv_py if venv_py.exists() else sys.executable)
    env = dict(os.environ)  # demo renders the dark set + one light Home shot
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    print(f"Rendering screenshots into {out} ...")
    rc = subprocess.call([py, str(ROOT / "app.py"), "--screenshot", str(out)], cwd=str(ROOT), env=env)
    pngs = sorted(out.glob("*.png"))
    for p in pngs:
        print(" ", p.name)
    print(f"done: {len(pngs)} files, exit code {rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
