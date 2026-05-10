"""
ocr_fallback.py — Subtitle extraction via frame sampling + Tesseract OCR.

Used when Whisper fails (no audio / silent video / corrupt audio track).

The videos have burned-in *English* subtitles, so Tesseract runs with lang="eng".
No translation is needed — the output is already English text.

Pipeline:
  1. Use ffmpeg to extract one frame every N seconds
  2. Crop the bottom portion of each frame (where subtitles live)
  3. Run Tesseract (English) on each cropped frame
  4. Deduplicate consecutive identical lines
  5. Return the joined English text as a TranscriptResult
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import List

try:
    from PIL import Image
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

from config import OCR_FRAME_INTERVAL, OCR_LANG, OCR_CROP_BOTTOM_PERCENT
from logger import get_logger
from transcriber import TranscriptResult  # reuse same dataclass

log = get_logger(__name__)


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _check_dependencies() -> str | None:
    """Return an error string if required tools are missing, else None."""
    if not OCR_AVAILABLE:
        return "Pillow or pytesseract not installed. Run: pip install pillow pytesseract"
    if not shutil.which("ffmpeg"):
        return "ffmpeg not found in PATH. Install with: sudo apt install ffmpeg"
    if not shutil.which("tesseract"):
        return "tesseract not found in PATH. Install with: sudo apt install tesseract-ocr"
    return None


def _extract_frames(video_path: str, output_dir: str, interval: int) -> List[str]:
    """
    Use ffmpeg to extract one frame every `interval` seconds.
    Returns a sorted list of frame file paths.
    """
    pattern = os.path.join(output_dir, "frame_%04d.png")
    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-vf", f"fps=1/{interval}",   # one frame per N seconds
        "-q:v", "2",                   # high quality PNG
        pattern,
        "-loglevel", "error",
        "-y",
    ]
    log.debug(f"Running ffmpeg: {' '.join(cmd)}")
    subprocess.run(cmd, check=True, capture_output=True)

    frames = sorted(
        os.path.join(output_dir, f)
        for f in os.listdir(output_dir)
        if f.endswith(".png")
    )
    log.info(f"Extracted {len(frames)} frames from video.")
    return frames


def _crop_subtitle_region(image: "Image.Image", bottom_fraction: float) -> "Image.Image":
    """
    Crop only the bottom `bottom_fraction` of the image.
    Islamic lecture videos typically have Arabic subtitles burned in at the bottom.
    """
    w, h = image.size
    top = int(h * (1.0 - bottom_fraction))
    return image.crop((0, top, w, h))


def _ocr_frame(frame_path: str, lang: str, crop_fraction: float) -> str:
    """
    Run Tesseract on a single frame.
    Returns the extracted text (may be empty).
    """
    img = Image.open(frame_path).convert("RGB")
    cropped = _crop_subtitle_region(img, crop_fraction)

    # Tesseract config: PSM 6 = single uniform block of text (good for subtitles)
    custom_config = r"--oem 3 --psm 6"
    text = pytesseract.image_to_string(cropped, lang=lang, config=custom_config)
    return text.strip()


def _deduplicate_lines(lines: List[str]) -> List[str]:
    """Remove consecutive duplicate lines (OCR often picks up the same subtitle twice)."""
    seen = []
    for line in lines:
        if not line:
            continue
        if not seen or line != seen[-1]:
            seen.append(line)
    return seen


# ── Main function ────────────────────────────────────────────────────────────────

def ocr_extract(video_path: str) -> TranscriptResult:
    """
    Extract subtitle text from a video using frame sampling + Tesseract OCR.

    Args:
        video_path: Path to the video file.

    Returns:
        TranscriptResult with method="ocr"
    """
    result = TranscriptResult(method="ocr")

    # ── Preflight checks ──────────────────────────────────────────────────────
    dep_error = _check_dependencies()
    if dep_error:
        result.error = dep_error
        log.error(f"OCR dependency check failed: {dep_error}")
        return result

    if not os.path.isfile(video_path):
        result.error = f"File not found: {video_path}"
        log.error(result.error)
        return result

    # ── Run pipeline in a temp directory ──────────────────────────────────────
    with tempfile.TemporaryDirectory(prefix="ocr_frames_") as tmp_dir:
        try:
            frames = _extract_frames(video_path, tmp_dir, OCR_FRAME_INTERVAL)
        except subprocess.CalledProcessError as exc:
            result.error = f"ffmpeg failed: {exc.stderr.decode()}"
            log.error(result.error)
            return result

        if not frames:
            result.error = "No frames were extracted by ffmpeg."
            log.error(result.error)
            return result

        raw_lines: List[str] = []
        for i, frame in enumerate(frames):
            try:
                text = _ocr_frame(frame, OCR_LANG, OCR_CROP_BOTTOM_PERCENT)
                if text:
                    raw_lines.append(text)
                    log.debug(f"Frame {i+1}/{len(frames)}: {text[:60]}...")
            except Exception as exc:
                log.warning(f"OCR failed on frame {frame}: {exc}")

    # ── Post-process ──────────────────────────────────────────────────────────
    deduped = _deduplicate_lines(raw_lines)
    result.raw_text = "\n".join(deduped)

    if result.raw_text.strip():
        result.success = True
        log.info(
            f"OCR succeeded | lines={len(deduped)} | chars={len(result.raw_text)}"
        )
    else:
        result.error = "OCR produced no text. Video may have no burned-in subtitles."
        log.warning(result.error)

    return result
