"""Start with Windows: manages the value under HKCU\\...\\Run."""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import winreg
    HAS_WINREG = True
except Exception:
    HAS_WINREG = False

import config

REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = config.APP_ID
# value names written by earlier versions of the app (see config.LEGACY_APP_IDS)
LEGACY_VALUE_NAMES = [n for n in config.LEGACY_APP_IDS if n != VALUE_NAME]


def _command_to_run() -> str:
    """Build the command to launch at login.

    Inside a PyInstaller bundle (sys.frozen) use the exe;
    otherwise pythonw.exe + app.py (no console window).
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    venv_pythonw = Path(sys.executable).with_name("pythonw.exe")
    py = str(venv_pythonw if venv_pythonw.exists() else sys.executable)
    script = str(Path(__file__).parent / "app.py")
    return f'"{py}" "{script}"'


def _read(name: str):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH) as k:
            return winreg.QueryValueEx(k, name)[0]
    except FileNotFoundError:
        return None
    except Exception:
        return None


def _delete(name: str):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, name)
    except FileNotFoundError:
        pass


def is_enabled() -> bool:
    if not HAS_WINREG:
        return False
    return any(_read(n) is not None for n in [VALUE_NAME, *LEGACY_VALUE_NAMES])


def migrate_legacy():
    """Rename an autostart entry written under an old app name.

    From source, the command is kept exactly as it was (only the value name
    changes). From a built exe, it is re-pointed at the running exe, because
    a rebuild under the new name replaces the old dist folder.
    Safe to call at every start.
    """
    if not HAS_WINREG:
        return
    for legacy in LEGACY_VALUE_NAMES:
        cmd = _read(legacy)
        if cmd is None:
            continue
        if getattr(sys, "frozen", False):
            cmd = _command_to_run()
        if _read(VALUE_NAME) is None:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, VALUE_NAME, 0, winreg.REG_SZ, cmd)
        _delete(legacy)


def enable():
    if not HAS_WINREG:
        return
    cmd = _command_to_run()
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, VALUE_NAME, 0, winreg.REG_SZ, cmd)
    for legacy in LEGACY_VALUE_NAMES:
        _delete(legacy)


def disable():
    if not HAS_WINREG:
        return
    for name in [VALUE_NAME, *LEGACY_VALUE_NAMES]:
        _delete(name)
