"""
logger.py — Centralised logging factory.
Every module calls get_logger(__name__) to get a named logger that writes
to both the console and a rotating log file.
"""

import logging
import os
import sys
import io
from logging.handlers import RotatingFileHandler

from config import LOGS_DIR

os.makedirs(LOGS_DIR, exist_ok=True)

_LOG_FILE     = os.path.join(LOGS_DIR, "pipeline.log")
_MAX_BYTES    = 5 * 1024 * 1024
_BACKUP_COUNT = 3
_FMT      = "[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(_FMT, datefmt=_DATE_FMT)

    # ── Console handler — force UTF-8 so Arabic/emoji don't crash on Windows ──
    if hasattr(sys.stdout, "buffer"):
        utf8_stream = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    else:
        utf8_stream = sys.stdout
    ch = logging.StreamHandler(utf8_stream)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)

    # ── Rotating file handler ──────────────────────────────────────────────────
    fh = RotatingFileHandler(_LOG_FILE, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)

    logger.addHandler(ch)
    logger.addHandler(fh)
    return logger