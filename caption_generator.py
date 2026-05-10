"""
caption_generator.py — Generate one universal social media caption using local LLM.

The user provides a short note when sending the video (e.g. "Sheikh Suleiman Al-Rehaili,
emotional tone, about the power of a smile"). The LLM uses that note + the cleaned
transcript to produce a single polished caption that works across all platforms.

Output format:
  {
    "title":       "A smile that changed their entire life",
    "description": "A touching story shared by...",
    "hashtags":    ["#Islam", "#Quran", ...]
  }
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import List

import requests

from config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT
from logger import get_logger

log = get_logger(__name__)


# ── Data container ─────────────────────────────────────────────────────────────

@dataclass
class Caption:
    title:        str = ""
    description:  str = ""
    hashtags:     List[str] = field(default_factory=list)
    twitter_text: str = ""    # ≤280 chars for X — title + short desc only
    full_text:    str = ""    # full caption ready to copy-paste
    success:      bool = False
    error:        str = ""


# ── Prompt ──────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert Islamic social media content writer.
You write captions for Islamic lecture and reminder videos.

STRICT RULES — you must follow these exactly:
- TITLE: max 8 words, emotional and curiosity-driven
- DESCRIPTION: 1-2 sentences max, warm and sincere Islamic tone
- HASHTAGS: exactly 3-5 hashtags, most relevant only
- TOTAL LENGTH of (title + description + hashtags) combined: MUST be 280 characters or less. Count carefully.
- twitter_text: same as the full caption — since everything is already within 280 chars
- No clickbait, no exaggeration, authentic Islamic tone

Format the full caption exactly like this:
✨ [Title]

[Description]

#tag1 #tag2 #tag3

Hashtag pool (pick 3-5 most relevant):
English: #Islam #Quran #Islamic #Muslim #Hadith #Reminder #Dawah #IslamicQuotes #Sunnah #Allah #SubhanAllah #MashaAllah #IslamicReminder #Deen #Iman
Arabic:  #إسلام #قرآن #تذكير #دعوة #مسلم #الله

Respond ONLY with valid JSON — no markdown, no preamble:
{
  "title": "...",
  "description": "...",
  "hashtags": ["#tag1", "#tag2", "#tag3"],
  "twitter_text": "✨ [Title]\\n\\n[Description]\\n\\n#tag1 #tag2 #tag3"
}"""


def _build_prompt(transcript: str, user_note: str) -> str:
    return (
        f"User note about this video:\n{user_note}\n\n"
        f"Video transcript (cleaned English):\n{transcript}\n\n"
        "Generate the caption now."
    )


# ── Ollama call ────────────────────────────────────────────────────────────────

def _call_ollama(prompt: str) -> str:
    url = f"{OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        "stream": False,
        "options": {
            "temperature": 0.7,   # slightly creative for engaging captions
            "num_predict": 1024,
        },
    }
    log.info(f"Generating caption with {OLLAMA_MODEL}...")
    response = requests.post(url, json=payload, timeout=OLLAMA_TIMEOUT)
    response.raise_for_status()
    return response.json()["message"]["content"].strip()


def _parse_response(raw: str) -> dict:
    """
    Parse the LLM response into a dict with title, description, hashtags.

    Strategy (most to least strict):
      1. Strip markdown fences, try json.loads directly
      2. Regex-extract each field individually — handles malformed JSON
         (trailing commas, unescaped quotes, truncated output)
    """
    import re

    # ── Attempt 1: clean and parse as JSON ────────────────────────────────────
    text = raw.strip()

    # Strip ```json ... ``` or ``` ... ``` fences
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fenced:
        text = fenced.group(1).strip()

    # Also strip any leading/trailing text before the first { and after the last }
    brace_start = text.find("{")
    brace_end   = text.rfind("}")
    if brace_start != -1 and brace_end != -1:
        text = text[brace_start : brace_end + 1]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass  # fall through to regex extraction

    # ── Attempt 2: regex field extraction ─────────────────────────────────────
    # This handles: trailing commas, unescaped apostrophes, truncated JSON, etc.
    result = {}

    # Extract "title": "..."
    title_match = re.search(r'"title"\s*:\s*"([^"]*)"', raw)
    if title_match:
        result["title"] = title_match.group(1).strip()

    # Extract "description": "..."  (description may span multiple lines)
    desc_match = re.search(r'"description"\s*:\s*"([\s\S]*?)"(?:\s*,|\s*})', raw)
    if desc_match:
        result["description"] = desc_match.group(1).strip()

    # Extract hashtags array — grab everything between [ and ]
    tags_match = re.search(r'"hashtags"\s*:\s*\[([\s\S]*?)\]', raw)
    if tags_match:
        # Parse individual quoted strings from the array
        tags = re.findall(r'"(#[^"]+)"', tags_match.group(1))
        result["hashtags"] = tags

    if result:
        log.debug(f"Used regex fallback parser. Extracted fields: {list(result.keys())}")
        return result

    # ── Attempt 3: give up and raise so caller logs it ────────────────────────
    raise json.JSONDecodeError("Could not parse LLM response", raw, 0)


def _format_caption(title: str, description: str, hashtags: List[str]) -> str:
    """
    Build the final copy-pasteable caption string.

    Format:
      ✨ Title

      Description sentence one. Sentence two.

      #tag1 #tag2 #tag3 ...
    """
    tags_line = "  ".join(hashtags)
    return f"✨ {title}\n\n{description}\n\n{tags_line}"


# ── Main function ───────────────────────────────────────────────────────────────

def generate_caption(transcript: str, user_note: str = "") -> Caption:
    """
    Generate a universal social media caption.

    Args:
        transcript : Cleaned English text from the video.
        user_note  : Short context from the user (speaker name, tone, topic).

    Returns:
        Caption dataclass with title, description, hashtags, and full_text.
    """
    result = Caption()

    if not transcript.strip():
        result.error = "Cannot generate caption — transcript is empty."
        log.warning(result.error)
        return result

    # If user gave no note, use a generic placeholder so the prompt still works
    note = user_note.strip() if user_note.strip() else "Islamic lecture/reminder video."

    prompt = _build_prompt(transcript, note)

    try:
        raw_response = _call_ollama(prompt)
        log.debug(f"LLM caption response (first 300 chars): {raw_response[:300]}")

        parsed = _parse_response(raw_response)

        result.title        = parsed.get("title", "").strip()
        result.description  = parsed.get("description", "").strip()
        result.hashtags     = parsed.get("hashtags", [])
        result.twitter_text = parsed.get("twitter_text", "").strip()

        # Hard enforce 280 char limit on twitter_text — LLMs sometimes overshoot
        if len(result.twitter_text) > 280:
            result.twitter_text = result.twitter_text[:277] + "..."

        # Fallback: build twitter_text from title if LLM didn't provide it
        if not result.twitter_text and result.title:
            short = f"{result.title}\n\n{result.description[:150]}..."
            result.twitter_text = short[:277] + "..." if len(short) > 280 else short

        if result.title and result.description:
            result.full_text = _format_caption(
                result.title, result.description, result.hashtags
            )

            # Hard enforce 280 char limit — truncate description if LLM overshoots
            if len(result.full_text) > 280:
                allowed_desc = 280 - len(result.title) - len("  ".join(result.hashtags)) - 10
                result.description = result.description[:max(allowed_desc, 40)].rstrip() + "..."
                result.full_text = _format_caption(result.title, result.description, result.hashtags)

            # twitter_text = same full_text since it's already within 280
            if not result.twitter_text:
                result.twitter_text = result.full_text
            if len(result.twitter_text) > 280:
                result.twitter_text = result.full_text[:277] + "..."

            result.success = True
            log.info(f"Caption generated | title='{result.title}' | total_chars={len(result.full_text)}")
        else:
            result.error = "LLM returned incomplete caption fields."
            log.warning(result.error)

    except requests.exceptions.ConnectionError:
        result.error = f"Cannot connect to Ollama at {OLLAMA_BASE_URL}. Run: ollama serve"
        log.error(result.error)

    except (json.JSONDecodeError, KeyError) as exc:
        result.error = f"Failed to parse LLM caption response: {exc}"
        log.error(result.error)
        log.error(f"Raw LLM output was:\n{raw_response}")

    except Exception as exc:
        result.error = str(exc)
        log.exception(f"Unexpected error in caption generator: {exc}")

    return result