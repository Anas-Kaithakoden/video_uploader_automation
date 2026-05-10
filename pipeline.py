"""
pipeline.py — Core processing pipeline for Steps 1 & 2.

Called by both the Telegram handler (bot mode) and main.py (CLI mode).

Flow:
  video_path
    → transcribe with Whisper
    → if failed → OCR fallback
    → if text found → clean + translate with LLM
    → save results to output/<video_id>/
    → update job tracker
"""

from __future__ import annotations

import os

from config import OUTPUT_DIR
from logger import get_logger
from transcriber import transcribe
from ocr_fallback import ocr_extract
from text_cleaner import clean_and_translate
from caption_generator import generate_caption
from storage.utils import create_job, update_job

log = get_logger(__name__)


def _save_output(video_id: str, raw_text: str, method: str,
                 english_cleaned: str, caption_text: str) -> str:
    """
    Save results to output/<video_id>/result.txt
    Returns the path of the saved file.
    """
    out_dir = os.path.join(OUTPUT_DIR, video_id)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "result.txt")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write(f"VIDEO ID : {video_id}\n")
        f.write(f"METHOD   : {method}\n")
        f.write("=" * 60 + "\n\n")

        f.write("── RAW ENGLISH (Whisper translate / OCR) ──\n")
        f.write(raw_text + "\n\n")

        f.write("── CLEANED ENGLISH ──\n")
        f.write(english_cleaned + "\n\n")

        f.write("── CAPTION ──\n")
        f.write(caption_text + "\n")

    log.info(f"Results saved → {out_path}")
    return out_path


def run_pipeline(video_path: str, video_id: str | None = None,
                 user_note: str = "") -> dict:
    """
    Run the full pipeline on a video file.

    Args:
        video_path : Path to the downloaded video file.
        video_id   : Optional identifier (defaults to filename without extension).
        user_note  : Short context from the user (speaker name, tone, topic).

    Returns:
        Result dict with: success, method, raw_text, english_cleaned,
        caption, output_path, error.
    """
    if not video_id:
        video_id = os.path.splitext(os.path.basename(video_path))[0]

    log.info(f"── Pipeline START | video_id={video_id} ──────────────────────")

    # ── Create job entry ──────────────────────────────────────────────────────
    job_id = create_job(video_path, video_id=video_id)
    log.info(f"Job created: {job_id}")

    result = {
        "success":         False,
        "method":          None,
        "raw_text":        "",
        "english_cleaned": "",
        "caption":         "",
        "title":           "",
        "twitter_text":    "",
        "output_path":     "",
        "error":           "",
    }

    # ── Step 1: Transcription ─────────────────────────────────────────────────
    log.info("Step 1 → Whisper transcription...")
    transcript = transcribe(video_path)

    if not transcript.success:
        log.warning(f"Whisper failed ({transcript.error}) → trying OCR fallback...")
        update_job(job_id, transcription_method="ocr_fallback")
        transcript = ocr_extract(video_path)

    if not transcript.success:
        result["error"] = f"Both Whisper and OCR failed. Last error: {transcript.error}"
        log.error(result["error"])
        update_job(job_id, status="failed", error=result["error"])
        return result

    result["method"]   = transcript.method
    result["raw_text"] = transcript.raw_text
    update_job(job_id, transcription_method=transcript.method)
    log.info(f"Transcription OK via {transcript.method} | {len(transcript.raw_text)} chars")

    # ── Step 2: LLM Text Cleaning ─────────────────────────────────────────────
    log.info("Step 2 → Cleaning English text with LLM...")
    cleaned = clean_and_translate(transcript.raw_text)

    if cleaned.success:
        result["english_cleaned"] = cleaned.english_cleaned
    else:
        log.warning(f"LLM cleaning failed ({cleaned.error}) — using raw text.")
        result["english_cleaned"] = transcript.raw_text

    # ── Step 3: Caption Generation ────────────────────────────────────────────
    log.info(f"Step 3 → Generating caption | user_note='{user_note[:60]}'...")
    caption = generate_caption(result["english_cleaned"], user_note=user_note)

    if caption.success:
        result["caption"]      = caption.full_text
        result["title"]        = caption.title
        result["twitter_text"] = caption.twitter_text
        update_job(job_id, title=caption.title)
        log.info(f"Caption OK | title='{caption.title}'")
    else:
        log.warning(f"Caption generation failed ({caption.error})")
        result["caption"] = "[Caption generation failed — check Ollama]"

    # ── Save all results ──────────────────────────────────────────────────────
    out_path = _save_output(
        video_id,
        result["raw_text"],
        result["method"],
        result["english_cleaned"],
        result["caption"],
    )
    result["output_path"] = out_path
    result["success"]     = True

    update_job(job_id, status="completed")
    log.info(f"── Pipeline DONE | output → {out_path} ──────────────────────")
    return result