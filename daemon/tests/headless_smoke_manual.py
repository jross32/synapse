"""Smoke-test an independent ephemeral headless browser, without credentials."""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel="chrome")
        try:
            page = await browser.new_page()
            await page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=30000)
            print("headless=True", "title=", await page.title(), "url=", page.url)
            print("authenticated=NOT_ASSERTED; ephemeral profile, no credentials copied")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
