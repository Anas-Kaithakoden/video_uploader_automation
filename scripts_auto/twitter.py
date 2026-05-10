"""
scripts/twitter.py — X/Twitter upload, wrapped as an async function.
Navigation code is unchanged from the working x_script.py.

X has a 280-character limit. The caller must pass twitter_text (≤280 chars).
"""

import asyncio
import os
from playwright.async_api import async_playwright, expect

PROFILE_DIR = r"C:\Anas\projects\islamic_uploader\sessions\x_session"


async def upload(video_path: str, tweet_text: str) -> dict:
    """
    tweet_text: ready-to-post text, must be ≤280 chars.
    Returns {"success": bool, "error": str}
    """
    os.makedirs(PROFILE_DIR, exist_ok=True)
    video_path_abs = os.path.abspath(video_path)

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

            # ===== X VIDEO POST =====
            await page.goto("https://x.com/home")
            # ===== WAIT FOR COMPOSER =====
            tweet_box = page.get_by_role("textbox", name="Post text")
            await tweet_box.wait_for(timeout=60000)
            # ===== TYPE TWEET via clipboard (handles emojis + Arabic correctly) =====
            await tweet_box.click()
            await page.evaluate(f"navigator.clipboard.writeText({repr(tweet_text)})")
            await tweet_box.press("Control+v")
            await page.wait_for_timeout(1000)
            # ===== DISMISS TYPEAHEAD DROPDOWN =====
            # X shows a hashtag/account autocomplete dropdown after pasting text.
            # This dropdown intercepts pointer events and blocks the media button click.
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(500)
            # ===== UPLOAD VIDEO =====
            media_button = page.get_by_role("button", name="Add photos or video")
            async with page.expect_file_chooser() as fc_info:
                await media_button.click()
            file_chooser = await fc_info.value
            await file_chooser.set_files(video_path_abs)
            print("Uploading video...")
            # ===== TRIGGER PREVIEW — click the tweet box and dispatch body click =====
            # X needs a real interaction after file select to render the video preview.
            # Clicking the tweet textbox (known visible element) + dispatching a
            # native click on document.body replicates what a manual click does.
            await tweet_box.click()
            await page.evaluate("document.body.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}))")
            # ===== WAIT FOR VIDEO PREVIEW =====
            await page.get_by_test_id("attachments").locator("video").wait_for(timeout=120000)
            print("Video preview loaded")
            # ===== EXTRA WAIT — matches working test script =====
            await page.wait_for_timeout(3000)
            # ===== POST BUTTON =====
            post_button = page.locator('[data-testid="tweetButtonInline"]')
            await expect(post_button).to_be_visible(timeout=120000)
            await expect(post_button).to_be_enabled(timeout=120000)
            # ===== POST via JS click — avoids scroll-instead-of-click issue =====
            await post_button.evaluate("(el) => el.click()")
            print("Tweet posted successfully")

            await page.wait_for_timeout(5000)
            await browser.close()

        return {"success": True, "error": ""}

    except Exception as exc:
        return {"success": False, "error": str(exc)}