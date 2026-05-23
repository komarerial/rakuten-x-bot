"""
X (Twitter) に手動でログインし、セッションクッキーを cookies.json に保存する補助スクリプト。

使い方:
    python save_cookies.py

実行すると Chrome ブラウザが開くので、X に手動でログインしてください。
ログイン完了後、このターミナルで Enter を押すとクッキーが cookies.json に保存されます。
"""

import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

COOKIES_FILE = Path("cookies.json")
X_URL = "https://x.com"


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="chrome",   # システムの Chrome を使用
            headless=False,
        )
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto(X_URL)
        print("ブラウザが開きました。X にログインしてください。")
        print("ログイン完了後、このターミナルで Enter を押してください...")
        input()

        # Playwright の add_cookies が直接読み込める形式（list of dict）で保存
        cookies = await context.cookies()

        COOKIES_FILE.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] クッキーを {COOKIES_FILE} に保存しました ({len(cookies)} 件)")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
