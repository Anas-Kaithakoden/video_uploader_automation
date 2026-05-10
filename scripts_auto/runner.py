"""
scripts/runner.py — Run upload scripts for selected platforms sequentially.

Each platform upload runs in its own thread with a fresh event loop —
identical to running asyncio.run() in isolation, which is how the test
scripts work. This avoids Playwright event loop conflicts with the Telegram bot.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
from concurrent.futures import ThreadPoolExecutor
from typing import List

from logger import get_logger

log = get_logger(__name__)

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))


def _load(name: str):
    """Load a script module by file path — avoids package name conflicts."""
    path = os.path.join(_SCRIPTS_DIR, f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _split_title_body(full_text: str) -> tuple:
    lines = full_text.strip().splitlines()
    title = lines[0].lstrip("✨ ").strip() if lines else "Islamic Video"
    body  = "\n".join(lines[1:]).strip()
    if body.startswith(title):
        body = body[len(title):].strip()
    return title, body


def _run_in_fresh_loop(upload_fn, *args, **kwargs) -> dict:
    """
    Run an async upload function in a completely fresh event loop.
    This replicates asyncio.run() isolation — same as the standalone test scripts.
    Playwright works correctly here because it owns the entire event loop.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(upload_fn(*args, **kwargs))
    finally:
        loop.close()
        asyncio.set_event_loop(None)


async def run_platforms(
    platforms:    List[str],
    video_path:   str,
    title:        str,
    caption:      str,
    twitter_text: str = "",
) -> dict:

    results = {}
    executor = ThreadPoolExecutor(max_workers=1)
    loop = asyncio.get_running_loop()

    for platform in platforms:
        log.info(f"Starting upload: {platform}")
        try:
            mod = _load(platform)

            if platform == "instagram":
                fn   = mod.upload
                args = (video_path, caption)

            elif platform == "twitter":
                fn   = mod.upload
                args = (video_path, twitter_text or caption)

            elif platform in ("youtube", "reddit"):
                yt_title, yt_body = _split_title_body(caption)
                fn   = mod.upload
                args = (video_path, yt_title, yt_body)

            else:
                results[platform] = {"success": False, "error": f"Unknown platform: {platform}"}
                continue

            # Run in a thread with its own fresh event loop — isolates Playwright
            result = await loop.run_in_executor(
                executor,
                _run_in_fresh_loop,
                fn,
                *args
            )

        except Exception as exc:
            log.exception(f"{platform} upload crashed: {exc}")
            result = {"success": False, "error": str(exc)}

        results[platform] = result
        status = "OK" if result["success"] else "FAILED"
        log.info(f"{platform}: {status} {result.get('error') or ''}")

        if platform != platforms[-1]:
            await asyncio.sleep(3)

    executor.shutdown(wait=False)
    return results