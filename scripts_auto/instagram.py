"""
scripts/instagram.py — Instagram upload, wrapped as an async function.
Navigation code is unchanged from the working instagram_script.py.
"""

import asyncio
import os
from playwright.async_api import async_playwright, expect

PROFILE_DIR = r"C:\Anas\projects\islamic_uploader\sessions\instagram_session"


async def upload(video_path: str, caption: str) -> dict:
    """
    caption: the full ready-to-post text (title + description + hashtags combined).
    Returns {"success": bool, "error": str}
    """
    os.makedirs(PROFILE_DIR, exist_ok=True)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch_persistent_context(
                user_data_dir=PROFILE_DIR,
                channel="chrome",
                headless=False,
                args=["--disable-blink-features=AutomationControlled"],
                ignore_default_args=["--enable-automation"],
            )

            page = await browser.new_page()
            await page.goto("https://www.instagram.com")

            # ===== WAIT =====
            await page.wait_for_timeout(3000)
            # ===== CLICK CREATE =====
            await page.get_by_label("New post").click()
            await page.wait_for_timeout(2000)
            # ===== UPLOAD VIDEO =====
            file_input = page.locator('input[type="file"]')
            await file_input.set_input_files(video_path)
            # ===== WAIT FOR VIDEO LOAD =====
            await page.wait_for_timeout(5000)
            # ===== NEXT =====
            next_button = page.get_by_role("button", name="Next").last
            await next_button.click()
            await page.wait_for_timeout(3000)
            # ===== NEXT AGAIN =====
            next_button = page.get_by_role("button", name="Next").last
            await next_button.click()
            # ===== WAIT =====
            await page.wait_for_timeout(3000)
            # ===== ADD CAPTION =====
            caption_box = page.locator('div[aria-label="Write a caption..."]')
            await caption_box.click()
            await page.keyboard.press("Control+A")
            await page.keyboard.type(caption)
            # ===== WAIT FOR SHARE BUTTON =====
            share_button = page.get_by_role("button", name="Share", exact=True)
            await expect(share_button).to_be_enabled(timeout=180000)
            # ===== SMALL HUMAN DELAY =====
            await page.wait_for_timeout(3000)
            # ===== SHARE =====
            await share_button.click()
            done_button = page.get_by_role("button", name="Done", exact=True)
            await done_button.wait_for(timeout=300000)
            await done_button.click()
            print("✅ Instagram post uploaded successfully")
            await browser.close()

        return {"success": True, "error": ""}

    except Exception as exc:
        return {"success": False, "error": str(exc)}