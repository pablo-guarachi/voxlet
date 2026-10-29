"""Central configuration.

The product name lives here, in ONE place: change APP_NAME and every window
title, tray tooltip, log folder, autostart entry and build output follows.
"""
import os
import re
from pathlib import Path

# ---------------------------------------------------------------- identity
APP_NAME = "Voxlet"  # display name (window titles, tray, overlay, shortcuts)
# filesystem/registry-safe id derived from APP_NAME (exe name, %LOCALAPPDATA%
# folder, HKCU Run value, QSettings organisation)
APP_ID = re.sub(r"[^A-Za-z0-9]", "", APP_NAME) or "DictationApp"
APP_TAGLINE = "Private push-to-talk dictation for Windows"

# Identifiers used by earlier versions of this project. Read once at startup
# and migrated to APP_ID so existing logs, overlay position and the autostart
# entry survive a rename. Add the old APP_ID here whenever APP_NAME changes.
LEGACY_APP_IDS = ["WhisperFlowClone"]
LEGACY_QSETTINGS_ORGS = ["whisperflow-clone"]

# ---------------------------------------------------------------- storage
# history.db and vocabulary.json live in ./data next to the sources (unchanged
# from earlier versions, so no migration is needed). DICTATION_DATA_DIR
# overrides it: demo/screenshot mode points it at a throw-away temp folder so
# it can never read or write the real history.
DATA_DIR_ENV = "DICTATION_DATA_DIR"
DATA_DIR = Path(os.environ.get(DATA_DIR_ENV) or (Path(__file__).parent / "data"))

# ---------------------------------------------------------------- hotkey (display only)
# The actual key handling lives in worker.py (_ctrl_held/_win_held).
HOTKEY_LABEL = "Ctrl + Win"
HOTKEY_KEYS = ["Ctrl", "Win"]

# ---------------------------------------------------------------- transcription
WHISPER_MODEL = "large-v3"
WHISPER_DEVICE = "cuda"
WHISPER_COMPUTE = "float16"
LANGUAGE = "auto"  # "auto" = detect among AUTO_LANGUAGES on every dictation
AUTO_LANGUAGES = ["it", "en"]  # auto-detection candidates (the first one is the fallback)

# Whisper initial_prompt per language: steers style/punctuation.
# The Italian prompts below are model input for Italian dictation, not UI text.
INITIAL_PROMPTS = {
    "it": "Trascrizione in italiano corrente, con punteggiatura.",
    "en": "Transcription in fluent English, with punctuation.",
}
VOCAB_PREFIX = {
    "it": " Termini specifici: ",
    "en": " Specific terms: ",
}

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.1:8b"
USE_LLM_CLEANUP = False

SAMPLE_RATE = 16000
CHANNELS = 1

CLEANUP_PROMPT_IT = """Sei un correttore di trascrizioni vocali italiane.
Compito: aggiungere punteggiatura, maiuscole, e rimuovere SOLO disfluenze evidenti ("ehm", "cioè" ripetuti, false partenze).
REGOLE FERREE:
- NON aggiungere parole non presenti nell'originale
- NON parafrasare, NON riformulare, NON tradurre
- NON aggiungere saluti, scuse, o commenti tuoi
- Se l'input è vuoto o senza senso, restituiscilo identico
- Se non sei sicuro, lascia il testo originale

Output: SOLO il testo corretto, nient'altro.

Originale: {text}
Corretto:"""

CLEANUP_PROMPT_EN = """You are a proofreader of English voice transcriptions.
Task: add punctuation and capitalization, and remove ONLY obvious disfluencies ("um", "uh", repeated "like", false starts).
STRICT RULES:
- DO NOT add words that are not in the original
- DO NOT paraphrase, rephrase, or translate
- DO NOT add greetings, apologies, or comments of your own
- If the input is empty or nonsensical, return it unchanged
- If unsure, keep the original text

Output: ONLY the corrected text, nothing else.

Original: {text}
Corrected:"""

CLEANUP_PROMPTS = {"it": CLEANUP_PROMPT_IT, "en": CLEANUP_PROMPT_EN}
