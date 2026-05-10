"""
scripts/youtube.py — YouTube upload, wrapped as an async function.
Navigation code is unchanged from the working youtube_script.py.
"""

import asyncio
import os
from playwright.async_api import async_playwright

PROFILE_DIR = r"C:\Anas\projects\islamic_uploader\sessions\youtube_session"


async def upload(video_path: str, title: str, caption: str) -> dict:
    """Returns {"success": bool, "error": str}"""
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
            await page.goto("https://www.youtube.com")

            await page.click('button[aria-label="Create"]')
            await page.click('text=Upload video')

            file_input = page.locator('input[type="file"]').first
            await file_input.wait_for(state="attached")
            await file_input.set_input_files(video_path)

            # ===== TITLE =====
            title_input = page.get_by_role("textbox", name="Add a title that describes")
            await title_input.click()
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await title_input.type(title)

            # ===== DESCRIPTION =====
            print("⏳ Adding description...")
            desc_input = page.get_by_role("textbox", name="Tell viewers about your video")
            await desc_input.click()
            await desc_input.type(caption)

            # CHECK BOX
            await page.get_by_role("radio", name="No, it's not 'Made for Kids'").click()

            # Next steps
            print("⏳ Clicking Next...")
            for i in range(3):
                next_btn = page.locator('button:has-text("Next")')
                await next_btn.wait_for(timeout=5000)
                await next_btn.click()
                await page.wait_for_timeout(1500)
                print(f"✅ Next {i+1} clicked")

            # PUBLIC - Visibility
            public_radio = page.get_by_role("radio", name="Public")
            await public_radio.wait_for()
            await public_radio.click()

            # PUBLISH
            publish_btn = page.get_by_role("button", name="Publish")
            await publish_btn.wait_for()
            await publish_btn.click()

            print("✅ YouTube upload successful")
            await page.wait_for_timeout(5000)
            await browser.close()

        return {"success": True, "error": ""}

    except Exception as exc:
        return {"success": False, "error": str(exc)}