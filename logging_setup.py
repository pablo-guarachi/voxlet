"""Robust logging for the app (name taken from config.APP_NAME).

Goals:
- Work with PyInstaller --windowed (stdout/stderr = NUL).
- Survive a read-only install dir: logs go to %LOCALAPPDATA%.
- Capture native crashes (PortAudio segfaults) via faulthandler.
- Capture unhandled exceptions (main thread + worker threads).
- Capture Qt warnings (qInstallMessageHandler).

Imported as early as possible by the entrypoint.
"""
from __future__ import annotations

import faulthandler
import logging
import logging.handlers
import os
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path

import config

LOGGER_NAME = config.APP_ID.lower()

_initialized = False
_log_dir: Path | None = None
_log_file: Path | None = None
_fault_file_handle = None  # keeps the faulthandler file handle alive


def log_dir() -> Path:
    """Log directory. Always writable by the current user."""
    # Demo/screenshot mode: keep logs inside the throw-away data dir.
    if os.environ.get(config.DATA_DIR_ENV):
        d = Path(config.DATA_DIR) / "logs"
        d.mkdir(parents=True, exist_ok=True)
        return d
    base = Path(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"))
    app_dir = base / config.APP_ID
    if not app_dir.exists():
        # Backward compatibility: move the folder of a previous app name.
        # If it can't be moved (e.g. an old build still running holds the
        # log file open) keep using it as-is: nothing is lost.
        for legacy in config.LEGACY_APP_IDS:
            old = base / legacy
            if legacy != config.APP_ID and old.is_dir():
                try:
                    old.rename(app_dir)
                except OSError:
                    app_dir = old
                break
    d = app_dir / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_file() -> Path:
    return log_dir() / "app.log"


def fault_file() -> Path:
    return log_dir() / "fault.log"


def init(level: int = logging.INFO) -> logging.Logger:
    """Idempotent. Returns the main logger."""
    global _initialized, _log_dir, _log_file, _fault_file_handle

    logger = logging.getLogger(LOGGER_NAME)
    if _initialized:
        return logger

    _log_dir = log_dir()
    _log_file = log_file()

    logger.setLevel(level)
    logger.propagate = False

    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s/%(threadName)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = logging.handlers.RotatingFileHandler(
        _log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8", delay=False
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Save the original streams BEFORE any redirect, so the StreamHandler
    # always writes there (never to our _StreamToLogger).
    _orig_stderr = sys.stderr
    _orig_stdout = sys.stdout

    # Console handler only when a TTY is really attached (dev mode).
    # With PyInstaller --windowed sys.stderr is None → no StreamHandler,
    # which also avoids infinite recursion with the redirect below.
    try:
        if _orig_stderr is not None and getattr(_orig_stderr, "isatty", lambda: False)():
            ch = logging.StreamHandler(stream=_orig_stderr)
            ch.setFormatter(fmt)
            logger.addHandler(ch)
    except Exception:
        pass

    # Faulthandler: native crashes (PortAudio, ctypes, etc.)
    try:
        _fault_file_handle = open(fault_file(), "a", buffering=1, encoding="utf-8")
        _fault_file_handle.write(
            f"\n=== {datetime.now().isoformat()} faulthandler enabled ===\n"
        )
        faulthandler.enable(file=_fault_file_handle, all_threads=True)
    except Exception as e:
        logger.warning("faulthandler enable failed: %s", e)

    # Global excepthook (unhandled exceptions on the main thread)
    def _hook(exc_type, exc, tb):
        logger.critical(
            "UNCAUGHT EXCEPTION:\n%s",
            "".join(traceback.format_exception(exc_type, exc, tb)),
        )
        # still show the original error, e.g. on a dev console
        try:
            sys.__excepthook__(exc_type, exc, tb)
        except Exception:
            pass

    sys.excepthook = _hook

    # Per-thread excepthook (Python >= 3.8)
    def _thread_hook(args):
        logger.critical(
            "UNCAUGHT THREAD EXCEPTION in %s:\n%s",
            args.thread.name if args.thread else "?",
            "".join(
                traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
            ),
        )

    try:
        threading.excepthook = _thread_hook
    except Exception:
        pass

    # Redirect stdout/stderr → logger so leftover print() calls are not lost
    class _StreamToLogger:
        def __init__(self, lg, lvl):
            self._lg = lg
            self._lvl = lvl
            self._buf = ""

        def write(self, msg):
            try:
                if not msg:
                    return
                self._buf += msg
                while "\n" in self._buf:
                    line, self._buf = self._buf.split("\n", 1)
                    if line.strip():
                        self._lg.log(self._lvl, line.rstrip())
            except Exception:
                pass

        def flush(self):
            try:
                if self._buf.strip():
                    self._lg.log(self._lvl, self._buf.rstrip())
                self._buf = ""
            except Exception:
                pass

        def isatty(self):
            return False

    # Only when not attached to a TTY (i.e. --windowed or a subprocess).
    # The StreamHandler added above points at _orig_stderr, so there is no
    # risk of recursion: the logger never writes to our redirects.
    try:
        if not (_orig_stdout and getattr(_orig_stdout, "isatty", lambda: False)()):
            sys.stdout = _StreamToLogger(logger, logging.INFO)
        if not (_orig_stderr and getattr(_orig_stderr, "isatty", lambda: False)()):
            sys.stderr = _StreamToLogger(logger, logging.WARNING)
    except Exception:
        pass

    logger.info("=" * 60)
    logger.info(config.APP_NAME + " starting — pid=%s python=%s", os.getpid(), sys.version.split()[0])
    logger.info("frozen=%s argv=%s", getattr(sys, "frozen", False), sys.argv)
    logger.info("log file: %s", _log_file)

    _initialized = True
    return logger


def install_qt_handler():
    """Call AFTER the QApplication has been created."""
    try:
        from PySide6.QtCore import qInstallMessageHandler, QtMsgType
    except Exception:
        return

    logger = logging.getLogger(LOGGER_NAME + ".qt")

    def _handler(msg_type, ctx, message):
        lvl = {
            QtMsgType.QtDebugMsg: logging.DEBUG,
            QtMsgType.QtInfoMsg: logging.INFO,
            QtMsgType.QtWarningMsg: logging.WARNING,
            QtMsgType.QtCriticalMsg: logging.ERROR,
            QtMsgType.QtFatalMsg: logging.CRITICAL,
        }.get(msg_type, logging.INFO)
        loc = ""
        try:
            if ctx and ctx.file:
                loc = f" ({ctx.file}:{ctx.line})"
        except Exception:
            pass
        logger.log(lvl, "%s%s", message, loc)

    qInstallMessageHandler(_handler)


def get_logger(name: str | None = None) -> logging.Logger:
    if name:
        return logging.getLogger(LOGGER_NAME).getChild(name)
    return logging.getLogger(LOGGER_NAME)
