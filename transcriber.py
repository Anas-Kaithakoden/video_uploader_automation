"""
transcriber.py — Primary transcription using OpenAI Whisper (runs locally).

Returns a TranscriptResult dataclass with:
  - raw_text  : full joined transcript
  - segments  : list of {start, end, text} dicts for SRT/caption use
  - language  : detected language code
  - success   : bool — False means the caller should try OCR fallback
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Dict, Any

import whisper  # openai-whisper package

from config import WHISPER_MODEL
from logger import get_logger

log = get_logger(__name__)


# ── Data container ─────────────────────────────────────────────────────────────

@dataclass
class TranscriptResult:
    raw_text:  str = ""
    segments:  List[Dict[str, Any]] = field(default_factory=list)
    language:  str = "unknown"
    success:   bool = False
    method:    str = "whisper"   # "whisper" or "ocr"
    error:     str = ""


# ── Module-level model cache ────────────────────────────────────────────────────
# Whisper model loading is slow — keep it in memory between calls.
_model_cache: dict[str, Any] = {}


def _load_model(model_name: str):
    """Load (or return cached) Whisper model."""
    if model_name not in _model_cache:
        log.info(f"Loading Whisper model '{model_name}' — this may take a moment...")
        _model_cache[model_name] = whisper.load_model(model_name)
        log.info(f"Whisper model '{model_name}' loaded.")
    return _model_cache[model_name]


# ── Main function ───────────────────────────────────────────────────────────────

def transcribe(video_path: str) -> TranscriptResult:
    """
    Transcribe the audio track of a video file using Whisper.

    Whisper auto-detects language; for Islamic videos the language is
    almost always Arabic ("ar") but we let Whisper decide.

    Args:
        video_path: Absolute or relative path to the video file.

    Returns:
        TranscriptResult  (success=False if anything goes wrong)
    """
    result = TranscriptResult()

    if not os.path.isfile(video_path):
        result.error = f"File not found: {video_path}"
        log.error(result.error)
        return result

    try:
        model = _load_model(WHISPER_MODEL)

        log.info(f"Transcribing + translating: {video_path}")
        # task="translate" → Whisper detects the language (Arabic, English, etc.)
        # and outputs English text directly — no separate translation step needed.
        # fp16=False is safer on CPU; set True if you have a CUDA GPU.
        raw = model.transcribe(
            video_path,
            task="translate",   # ← key change: outputs English regardless of source language
            fp16=False,
            verbose=False,
        )

        result.language  = raw.get("language", "unknown")   # detected source language
        result.raw_text  = raw.get("text", "").strip()      # always English output

        # Build a clean segment list
        result.segments = [
            {
                "start": round(seg["start"], 2),
                "end":   round(seg["end"],   2),
                "text":  seg["text"].strip(),
            }
            for seg in raw.get("segments", [])
            if seg["text"].strip()
        ]

        if result.raw_text:
            result.success = True
            log.info(
                f"Whisper succeeded | source_language={result.language} | "
                f"output=English | segments={len(result.segments)} | chars={len(result.raw_text)}"
            )
        else:
            result.error = "Whisper returned empty transcription."
            log.warning(result.error)

    except Exception as exc:
        result.error = str(exc)
        log.exception(f"Whisper transcription failed: {exc}")

    return result
