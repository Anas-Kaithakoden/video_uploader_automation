"""
scripts/reddit.py — Reddit upload, wrapped as an async function.
Navigation code is unchanged from the working reddit_script.py.
"""

import asyncio
import os
from playwright.async_api import async_playwright, expect

PROFILE_DIR = r"C:\Anas\projects\islamic_uploader\sessions\reddit_session"

# Subreddits to post to and their matching flair
SUBREDDITS = [
    {"name": "TrueDeen", "flair": "Qur'an/Hadith"},
    {"name": "islam",    "flair": "Quran & Hadith"},
    {"name": "Muslim",    "flair": "Quran/Hadith 🕋"}
]


async def upload(video_path: str, title: str, caption: str) -> dict:
    """Returns {"success": bool, "error": str}"""
    os.makedirs(PROFILE_DIR, exist_ok=True)
    video_path = os.path.abspath(video_path)

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
            await page.goto("https://www.reddit.com")

            for sub in SUBREDDITS:
                subreddit  = sub["name"]
                flair_name = sub["flair"]
                print(f"\n🚀 Posting to r/{subreddit}")

                # Open submit page
                await page.goto("https://www.reddit.com/submit")

                await page.get_by_role("button", name="Select Community").wait_for(timeout=60000)

                # ===== SELECT COMMUNITY =====
                await page.get_by_role("button", name="Select Community").click()

                community_search = page.get_by_label("Search communities").get_by_placeholder("Search communities")
                await community_search.click()
                await community_search.press("Control+A")
                await community_search.press("Backspace")
                await community_search.fill(subreddit)
                await page.get_by_test_id("items-container").get_by_text(f"r/{subreddit}", exact=True).click()
                print(f"✅ Selected r/{subreddit}")

                # ===== SWITCH TO IMAGES & VIDEO =====
                await page.get_by_role("tab", name="Images & Video").click()
                await page.wait_for_function("""
                () => {
                    const el = document.querySelector('r-post-type-select');
                    return el && el.getAttribute('value') === 'IMAGE';
                }
                """)

                # ===== VIDEO UPLOAD =====
                async with page.expect_file_chooser() as fc_info:
                    await page.get_by_role("button", name="Upload files").click()
                file_chooser = await fc_info.value
                await file_chooser.set_files(video_path)

                # ===== TITLE =====
                title_box = page.get_by_role("textbox", name="Title")
                await title_box.click()
                await title_box.fill(title)

                # ===== BODY =====
                body_box = page.get_by_role("textbox", name="Optional Body text field")
                await body_box.wait_for()
                await body_box.click()
                await body_box.press_sequentially(caption)

                # ===== FLAIR =====
                await page.get_by_role("button", name="Add flair and tags *").click()
                await page.get_by_role("radio", name=flair_name).click()
                await page.get_by_role("button", name="Add", exact=True).click()

                # ===== POST =====
                post_button = page.get_by_role("button", name="Post", exact=True)
                await expect(post_button).to_be_enabled(timeout=120000)
                await post_button.click()
                print(f"✅ Posted successfully to r/{subreddit}")

                await page.wait_for_timeout(5000)

            await page.wait_for_timeout(5000)
            await browser.close()

        return {"success": True, "error": ""}

    except Exception as exc:
        return {"success": False, "error": str(exc)}