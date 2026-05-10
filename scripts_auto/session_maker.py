import asyncio
import os
from playwright.async_api import async_playwright

# Change this per platform
PROFILE_DIR = r"C:\Anas\projects\islamic_uploader\sessions\test_session"

# Change this per platform
URL = "https://www.instagram.com"


async def main():

    os.makedirs(PROFILE_DIR, exist_ok=True)

    async with async_playwright() as p:

        browser = await p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            channel="chrome",
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
            ],
            ignore_default_args=["--enable-automation"],
        )

        page = await browser.new_page()

        await page.goto(URL)

        print("🔐 Log in manually if needed...")
        print("✅ After login, close the browser window manually")
        print("💾 Session will remain saved in PROFILE_DIR")

        # Keeps browser alive
        await page.pause()


asyncio.run(main())