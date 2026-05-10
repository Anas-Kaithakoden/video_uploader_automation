"""
config.py — Central configuration loaded from .env
All modules import from here. Never hardcode secrets anywhere else.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# ── Access Control ────────────────────────────────────────────────────────────
# Only respond to this Telegram chat ID. Get yours by messaging @userinfobot.
ALLOWED_CHAT_ID = int(os.getenv("ALLOWED_CHAT_ID", "0"))

# ── Whisper ───────────────────────────────────────────────────────────────────
# Model size: tiny | base | small | medium | large
# "small" is the minimum recommended for Arabic accuracy
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")

# ── Ollama (local LLM) ────────────────────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "llama3")
OLLAMA_TIMEOUT  = int(os.getenv("OLLAMA_TIMEOUT", "120"))  # seconds

# ── OCR Fallback ──────────────────────────────────────────────────────────────
# How often to sample frames from the video (every N seconds)
OCR_FRAME_INTERVAL = int(os.getenv("OCR_FRAME_INTERVAL", "2"))
# Tesseract language — subtitles are burned-in English so we use "eng"
OCR_LANG = os.getenv("OCR_LANG", "eng")
# Bottom crop percentage — subtitles are usually in the bottom 20%
OCR_CROP_BOTTOM_PERCENT = float(os.getenv("OCR_CROP_BOTTOM_PERCENT", "0.20"))

# ── Directories ───────────────────────────────────────────────────────────────
DOWNLOADS_DIR = "downloads"   # raw video files from Telegram
OUTPUT_DIR    = "output"      # transcription + cleaned text results
LOGS_DIR      = "logs"
STORAGE_DIR   = "storage"

# ── Retry ─────────────────────────────────────────────────────────────────────
MAX_RETRIES = 2