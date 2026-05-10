"""
main.py — Entry point for the Islamic Video Uploader system.

Modes:
  python main.py bot               — Start Telegram bot (default)
  python main.py cli <video_path>  — Process a local video file directly
"""

import sys
import os

# ── Windows UTF-8 fix ──────────────────────────────────────────────────────────
# Windows console defaults to cp1252 which can't print → ── etc.
# Reconfigure stdout/stderr to UTF-8 before anything else runs.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from logger import get_logger
from config import DOWNLOADS_DIR, OUTPUT_DIR

log = get_logger("main")

# Ensure required directories exist at startup
for d in [DOWNLOADS_DIR, OUTPUT_DIR, "logs", "storage"]:
    os.makedirs(d, exist_ok=True)


def run_cli(video_path: str) -> None:
    """CLI mode: process a local video file and print results."""
    from pipeline import run_pipeline

    if not os.path.isfile(video_path):
        log.error(f"File not found: {video_path}")
        sys.exit(1)

    log.info(f"CLI mode — processing: {video_path}")
    result = run_pipeline(video_path)

    print("\n" + "=" * 60)
    if result["success"]:
        print(f"✅  METHOD            : {result['method']}")
        print(f"📄  OUTPUT FILE       : {result['output_path']}")
        print("\n── CLEANED ENGLISH ──")
        print(result["english_cleaned"] or "(none)")
    else:
        print(f"❌  FAILED: {result['error']}")
    print("=" * 60 + "\n")


def run_bot() -> None:
    """Bot mode: start the Telegram polling bot."""
    from telegram_handler import run_bot as _run_bot
    _run_bot()


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args or args[0] == "bot":
        run_bot()

    elif args[0] == "cli":
        if len(args) < 2:
            print("Usage: python main.py cli <path/to/video.mp4>")
            sys.exit(1)
        run_cli(args[1])

    else:
        print("Unknown mode. Use: python main.py [bot|cli <video_path>]")
        sys.exit(1)
