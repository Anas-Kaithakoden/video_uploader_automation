"""
text_cleaner.py — Polish and clean extracted English text using a local LLM.

The text arriving here is already in English — either:
  - Translated directly by Whisper from Arabic audio (task="translate")
  - Extracted via OCR from burned-in English subtitles

So we no longer need translation. The LLM's job is to:
  - Fix Whisper's run-on sentences and filler words
  - Remove OCR noise / duplicate subtitle lines
  - Produce clean, readable English paragraphs
  - Preserve Islamic meaning and tone
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import requests

from config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT
from logger import get_logger

log = get_logger(__name__)


# ── Data container ─────────────────────────────────────────────────────────────

@dataclass
class CleanedText:
    english_cleaned: str = ""   # polished English text ready for captions
    success:         bool = False
    error:           str = ""


# ── Prompt builder ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an Islamic content editor and English language expert.
You will receive raw English text extracted from an Islamic lecture or recitation video.
The text may have been produced by Whisper (speech-to-text) or OCR (from burned-in subtitles).

Common issues to fix:
- Whisper: run-on sentences, repeated words, filler words like "um", "uh"
- OCR: duplicate subtitle lines, broken words split across lines, stray characters
- Both: fragmented sentences that need to be joined into proper paragraphs

Your rules:
1. Remove all duplicate or near-duplicate sentences
2. Fix grammar and punctuation
3. Join fragmented sentences into readable paragraphs
4. Preserve the Islamic tone and ALL religious meaning — do NOT paraphrase Quran verses or hadith
5. Do NOT add your own commentary, summaries, or opinions
6. Output only the cleaned text — nothing else

Respond ONLY with valid JSON in this exact format (no markdown, no preamble):
{
  "english_cleaned": "the cleaned English text here"
}"""


def _build_user_prompt(raw_text: str) -> str:
    return f"Here is the raw extracted text:\n\n{raw_text}\n\nProcess it as instructed."


# ── Ollama API call ─────────────────────────────────────────────────────────────

def _call_ollama(prompt: str) -> str:
    """
    Send a prompt to the local Ollama server and return the response text.
    Raises requests.RequestException on connection failure.
    """
    url = f"{OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        "stream": False,   # get the full response at once
        "options": {
            "temperature": 0.3,   # low temp = consistent, accurate output
            "num_predict": 2048,
        },
    }

    log.info(f"Sending text to Ollama ({OLLAMA_MODEL}) for cleaning...")
    response = requests.post(url, json=payload, timeout=OLLAMA_TIMEOUT)
    response.raise_for_status()

    data = response.json()
    # Ollama /api/chat returns: {"message": {"role": "assistant", "content": "..."}}
    return data["message"]["content"].strip()


def _parse_llm_response(raw_response: str) -> dict:
    """
    Parse JSON from LLM response.
    LLMs sometimes wrap JSON in markdown code fences — strip those first.
    """
    # Strip markdown code fences if present
    text = raw_response
    if "```" in text:
        # Extract content between ``` fences
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            try:
                return json.loads(part)
            except json.JSONDecodeError:
                continue

    # Try parsing directly
    return json.loads(text)


# ── Main function ────────────────────────────────────────────────────────────────

def clean_and_translate(raw_text: str) -> CleanedText:
    """
    Clean Arabic transcription and translate to English using local LLM.

    Args:
        raw_text: Raw text from Whisper or OCR.

    Returns:
        CleanedText with arabic_cleaned and english_translation fields.
    """
    result = CleanedText()

    if not raw_text or not raw_text.strip():
        result.error = "Empty text passed to cleaner."
        log.warning(result.error)
        return result

    prompt = _build_user_prompt(raw_text)

    try:
        raw_response = _call_ollama(prompt)
        log.debug(f"LLM raw response (first 200 chars): {raw_response[:200]}")

        parsed = _parse_llm_response(raw_response)

        result.english_cleaned = parsed.get("english_cleaned", "").strip()

        if result.english_cleaned:
            result.success = True
            log.info(
                f"LLM cleaning succeeded | "
                f"chars={len(result.english_cleaned)}"
            )
        else:
            result.error = "LLM returned empty english_cleaned field."
            log.warning(result.error)

    except requests.exceptions.ConnectionError:
        result.error = (
            f"Cannot connect to Ollama at {OLLAMA_BASE_URL}. "
            "Make sure Ollama is running: `ollama serve`"
        )
        log.error(result.error)

    except requests.exceptions.Timeout:
        result.error = f"Ollama request timed out after {OLLAMA_TIMEOUT}s."
        log.error(result.error)

    except (json.JSONDecodeError, KeyError) as exc:
        result.error = f"Failed to parse LLM response as JSON: {exc}"
        log.error(f"{result.error} | Raw response: {raw_response[:300]}")

    except Exception as exc:
        result.error = str(exc)
        log.exception(f"Unexpected error in text cleaner: {exc}")

    return result
