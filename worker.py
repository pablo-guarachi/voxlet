"""DictationWorker — hotkey listener, recording, STT, cleanup, paste.

Exposes callbacks for state and transcriptions; the UI (Qt or CLI) subscribes.
All diagnostics go through the `<app_id>.worker` logger (see logging_setup).

States: 'idle' (worker not started), 'listening' (waiting for the hotkey),
        'recording' (capturing audio), 'processing' (STT/LLM/paste running).
"""
from __future__ import annotations

import os
import sys
import time
import threading
import traceback
from dataclasses import dataclass, field
from typing import Callable, Optional

if sys.platform == "win32":
    # The CUDA DLLs from the pip wheels live in nvidia/<pkg>/bin/ (no __init__.py,
    # so not importable): resolve the path via the filesystem. PATH is updated
    # too because cudnn loads cublas as a dependency and ignores add_dll_directory.
    _sp = os.path.join(sys.prefix, "Lib", "site-packages", "nvidia")
    for _pkg in ("cublas", "cudnn"):
        _dir = os.path.join(_sp, _pkg, "bin")
        if os.path.isdir(_dir):
            os.add_dll_directory(_dir)
            os.environ["PATH"] = _dir + os.pathsep + os.environ.get("PATH", "")

try:
    import onnxruntime  # noqa: F401
except Exception:
    pass

import numpy as np
import sounddevice as sd
import pyperclip
import requests
from pynput import keyboard
from pynput.keyboard import Controller, Key
from faster_whisper import WhisperModel

import config
from audio_mute import AudioMuter
from logging_setup import get_logger

log = get_logger("worker")


@dataclass
class TranscriptionResult:
    text_raw: str
    text_final: str
    stt_seconds: float
    llm_seconds: float
    used_llm: bool
    timestamp: float = field(default_factory=time.time)


StateCallback = Callable[[str], None]
TranscriptionCallback = Callable[[TranscriptionResult], None]
LogCallback = Callable[[str], None]


class DictationWorker:
    def __init__(
        self,
        on_state_change: Optional[StateCallback] = None,
        on_transcription: Optional[TranscriptionCallback] = None,
        on_log: Optional[LogCallback] = None,
    ):
        self.on_state_change = on_state_change or (lambda s: None)
        self.on_transcription = on_transcription or (lambda r: None)
        # on_log → shown in the UI log panel; everything is also logged to file.
        self._ui_log = on_log or (lambda m: None)

        self._state = "idle"
        self._kb = Controller()
        self._model: Optional[WhisperModel] = None
        self._listener: Optional[keyboard.Listener] = None
        self._pressed: set = set()
        self._stream: Optional[sd.InputStream] = None
        self._audio_buffer: list = []
        self._buffer_lock = threading.Lock()
        self._recording = False
        self._audio_status_seen: set = set()  # avoids spamming the same warning

        self.use_llm_cleanup: bool = config.USE_LLM_CLEANUP
        self.mute_audio_while_recording: bool = False
        self.vocabulary: list[str] = []
        self._muter = AudioMuter(log=lambda m: self._log(m))

    # ---------- log helpers ----------

    def _log(self, msg: str, level: int = 20):
        """Log to file (logger) and to the UI panel."""
        log.log(level, msg)
        try:
            self._ui_log(msg)
        except Exception:
            log.exception("UI log callback failed")

    @property
    def state(self) -> str:
        return self._state

    def _set_state(self, s: str):
        self._state = s
        log.debug("state -> %s", s)
        try:
            self.on_state_change(s)
        except Exception:
            log.exception("state callback error")

    # ---------- model ----------

    def load_model(self):
        self._log(f"[init] Loading Whisper model '{config.WHISPER_MODEL}' on {config.WHISPER_DEVICE}/{config.WHISPER_COMPUTE}...")
        try:
            self._model = WhisperModel(
                config.WHISPER_MODEL,
                device=config.WHISPER_DEVICE,
                compute_type=config.WHISPER_COMPUTE,
            )
            self._log("[init] Whisper ready.")
        except Exception as e:
            log.exception("Whisper load failed")
            self._log(f"[init][ERROR] Whisper load failed: {e}", level=40)
            raise

    # ---------- audio device introspection ----------

    def _log_audio_devices(self):
        try:
            devs = sd.query_devices()
            default_in, default_out = sd.default.device
            log.info("audio default: input=%s output=%s", default_in, default_out)
            for i, d in enumerate(devs):
                if d.get("max_input_channels", 0) > 0:
                    marker = " (DEFAULT INPUT)" if i == default_in else ""
                    log.info(
                        "  [%d] %s — in=%d sr=%s host=%s%s",
                        i,
                        d.get("name"),
                        d.get("max_input_channels"),
                        d.get("default_samplerate"),
                        d.get("hostapi"),
                        marker,
                    )
        except Exception:
            log.exception("query_devices failed")

    # ---------- start / stop ----------

    def start(self):
        if self._listener is not None:
            self._log("[start] worker already running")
            return
        if self._model is None:
            self.load_model()

        self._log_audio_devices()

        try:
            self._stream = sd.InputStream(
                samplerate=config.SAMPLE_RATE,
                channels=config.CHANNELS,
                callback=self._audio_callback,
                dtype="float32",
            )
            self._stream.start()
            log.info(
                "audio stream started: sr=%d ch=%d device=%s",
                config.SAMPLE_RATE,
                config.CHANNELS,
                self._stream.device,
            )
        except Exception as e:
            log.exception("InputStream open failed")
            self._log(f"[audio][ERROR] could not open stream: {e}", level=40)
            raise

        try:
            self._listener = keyboard.Listener(
                on_press=self._on_press, on_release=self._on_release
            )
            self._listener.start()
            log.info("keyboard listener started")
        except Exception as e:
            log.exception("keyboard.Listener start failed")
            self._log(f"[hotkey][ERROR] listener failed: {e}", level=40)
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
            raise

        self._set_state("listening")
        self._log("[ready] Hold Ctrl+Win to dictate.")

    def stop(self):
        log.info("worker stop requested")
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                log.exception("listener stop error")
            self._listener = None
        self._recording = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                log.exception("stream close error")
            self._stream = None
        self._set_state("idle")

    # ---------- hotkey handlers ----------

    def _ctrl_held(self) -> bool:
        return (Key.ctrl_l in self._pressed) or (Key.ctrl_r in self._pressed)

    def _win_held(self) -> bool:
        return (
            (Key.cmd in self._pressed)
            or (Key.cmd_l in self._pressed)
            or (Key.cmd_r in self._pressed)
        )

    def _on_press(self, key):
        try:
            self._pressed.add(key)
            if log.isEnabledFor(10):  # DEBUG
                log.debug("press %s -> ctrl=%s win=%s", key, self._ctrl_held(), self._win_held())
            if self._ctrl_held() and self._win_held() and not self._recording:
                self._start_recording()
        except Exception:
            log.exception("on_press error")

    def _on_release(self, key):
        try:
            self._pressed.discard(key)
            if not (self._ctrl_held() and self._win_held()) and self._recording:
                self._stop_and_process()
        except Exception:
            log.exception("on_release error")

    # ---------- audio capture ----------

    def _audio_callback(self, indata, frames, time_info, status):
        # PortAudio callback: must be fast and must never raise.
        if status:
            try:
                key = str(status)
                if key not in self._audio_status_seen:
                    self._audio_status_seen.add(key)
                    self._log(f"[audio][warn] {key}", level=30)
            except Exception:
                pass
        if not self._recording:
            return
        try:
            with self._buffer_lock:
                self._audio_buffer.append(indata.copy())
        except Exception:
            log.exception("audio buffer append error")

    def _start_recording(self):
        if self._recording:
            return
        with self._buffer_lock:
            self._audio_buffer = []
        self._recording = True
        self._log("[rec] Start")
        if self.mute_audio_while_recording:
            try:
                self._muter.mute_all_outputs()
            except Exception as e:
                log.exception("mute error")
                self._log(f"[mute][warn] {e}", level=30)
        self._set_state("recording")

    def _stop_and_process(self):
        if not self._recording:
            return
        self._recording = False
        try:
            self._muter.restore()
        except Exception:
            log.exception("muter restore error")
        self._log("[rec] Stop")

        with self._buffer_lock:
            buf = list(self._audio_buffer)
            self._audio_buffer = []

        if not buf:
            self._log("[rec] empty buffer (no samples captured — microphone?)", level=30)
            self._set_state("listening")
            return
        try:
            audio = np.concatenate(buf, axis=0).flatten()
        except Exception as e:
            log.exception("audio concat failed")
            self._log(f"[rec][ERROR] concat: {e}", level=40)
            self._set_state("listening")
            return

        duration = len(audio) / float(config.SAMPLE_RATE)
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        rms = float(np.sqrt(np.mean(audio**2))) if audio.size else 0.0
        log.info("captured: dur=%.2fs samples=%d peak=%.4f rms=%.4f", duration, len(audio), peak, rms)

        if duration < 0.3:
            self._log(f"[rec] too short ({duration:.2f}s)", level=30)
            self._set_state("listening")
            return
        if peak < 0.001:
            self._log(
                f"[rec][warn] audio signal almost silent (peak={peak:.5f}). "
                "Microphone muted or wrong device?",
                level=30,
            )

        self._set_state("processing")
        threading.Thread(
            target=self._process_audio, args=(audio,), daemon=True, name="stt-process"
        ).start()

    # ---------- processing pipeline ----------

    def _build_initial_prompt(self, lang: str) -> str:
        base = config.INITIAL_PROMPTS.get(lang, "")
        if self.vocabulary:
            prefix = config.VOCAB_PREFIX.get(lang, " ")
            base += prefix + ", ".join(self.vocabulary)
        return base.strip()

    def _resolve_language(self, audio: np.ndarray) -> str:
        """Fixed language from config, or detected among AUTO_LANGUAGES only.

        Whisper's unrestricted detection is often wrong on short phrases
        (e.g. Italian → Spanish/Portuguese): restricting it to the candidates makes it robust.
        """
        if config.LANGUAGE != "auto":
            return config.LANGUAGE
        candidates = config.AUTO_LANGUAGES
        try:
            detected, prob, all_probs = self._model.detect_language(
                audio, vad_filter=True
            )
        except Exception as e:
            self._log(f"[lang][warn] detect failed ({e}), fallback {candidates[0]}", level=30)
            return candidates[0]
        probs = {code: p for code, p in all_probs if code in candidates}
        lang = max(probs, key=probs.get) if probs else candidates[0]
        self._log(
            f"[lang] whisper={detected}({prob:.2f}) → chosen={lang} "
            + " ".join(f"{c}={probs.get(c, 0):.2f}" for c in candidates)
        )
        return lang

    def _process_audio(self, audio: np.ndarray):
        try:
            t0 = time.time()
            lang = self._resolve_language(audio)
            try:
                segments, info = self._model.transcribe(
                    audio,
                    language=lang,
                    vad_filter=True,
                    beam_size=5,
                    initial_prompt=self._build_initial_prompt(lang),
                )
                segs = list(segments)
                text_raw = " ".join(s.text.strip() for s in segs).strip()
            except Exception as e:
                log.exception("Whisper transcribe failed")
                self._log(f"[stt][ERROR] {e}\n{traceback.format_exc()}", level=40)
                return

            t1 = time.time()
            stt_s = t1 - t0
            self._log(f"[stt] {stt_s:.2f}s segments={len(segs)} text={text_raw!r}")

            if not text_raw:
                self._log("[stt] empty text (did VAD discard everything?)", level=30)
                return

            llm_s = 0.0
            text_final = text_raw
            if self.use_llm_cleanup:
                text_final = self._llm_cleanup(text_raw, lang)
                llm_s = time.time() - t1
                self._log(f"[llm] {llm_s:.2f}s — {text_final!r}")

            try:
                self._paste_text(text_final)
            except Exception as e:
                log.exception("paste failed")
                self._log(f"[paste][ERROR] {e}", level=40)

            result = TranscriptionResult(
                text_raw=text_raw,
                text_final=text_final,
                stt_seconds=stt_s,
                llm_seconds=llm_s,
                used_llm=self.use_llm_cleanup,
            )
            try:
                self.on_transcription(result)
            except Exception:
                log.exception("transcription callback error")
        except Exception:
            # safety net: whatever happens, never let the thread die silently
            log.exception("process_audio fatal")
        finally:
            self._set_state("listening")

    def _llm_cleanup(self, text: str, lang: str) -> str:
        prompt = config.CLEANUP_PROMPTS.get(lang, config.CLEANUP_PROMPT_IT)
        try:
            r = requests.post(
                config.OLLAMA_URL,
                json={
                    "model": config.OLLAMA_MODEL,
                    "prompt": prompt.format(text=text),
                    "stream": False,
                    "options": {"temperature": 0.2},
                },
                timeout=30,
            )
            r.raise_for_status()
            return r.json().get("response", text).strip()
        except Exception as e:
            log.exception("LLM cleanup failed")
            self._log(f"[llm][warn] {e}", level=30)
            return text

    def _paste_text(self, text: str):
        if not text.endswith((" ", "\n")):
            text = text + " "
        # CoInitialize for the current thread: on Windows pyperclip can touch
        # COM objects, and without a COM apartment Release() during GC causes
        # an access violation (silent crash of the whole process).
        co_initialized = False
        try:
            import comtypes
            try:
                comtypes.CoInitialize()
                co_initialized = True
            except OSError:
                # already initialised on this thread (RPC_E_CHANGED_MODE / S_FALSE)
                pass
        except Exception:
            log.exception("CoInitialize import failed (continuing without it)")
        try:
            pyperclip.copy(text)
        except Exception:
            log.exception("pyperclip.copy failed")
            return
        try:
            time.sleep(0.05)
            self._kb.press(Key.ctrl)
            self._kb.press("v")
            self._kb.release("v")
            self._kb.release(Key.ctrl)
            log.debug("pasted %d chars", len(text))
        finally:
            if co_initialized:
                try:
                    import comtypes
                    comtypes.CoUninitialize()
                except Exception:
                    pass
