import os
import json
import random
import requests
from pathlib import Path
from playwright.sync_api import sync_playwright, Page, BrowserContext
from dotenv import load_dotenv

load_dotenv()

# --- 環境変数の読み込み ---
RAKUTEN_APP_ID       = os.environ.get("RAKUTEN_APP_ID", "")
RAKUTEN_ACCESS_KEY   = os.environ.get("RAKUTEN_ACCESS_KEY", "")
RAKUTEN_AFFILIATE_ID = os.environ.get("RAKUTEN_AFFILIATE_ID", "")

TWITTER_USERNAME = os.environ.get("TWITTER_USERNAME", "")
TWITTER_PASSWORD = os.environ.get("TWITTER_PASSWORD", "")
TWITTER_EMAIL    = os.environ.get("TWITTER_EMAIL", "")

COOKIES_FILE = Path("cookies.json")

# --- GitHub Secrets の COOKIES_JSON からクッキーファイルを復元 ---
_cookies_json_env = os.environ.get("COOKIES_JSON", "")
if _cookies_json_env and not COOKIES_FILE.exists():
    COOKIES_FILE.write_text(_cookies_json_env, encoding="utf-8")
    print("[INFO] COOKIES_JSON 環境変数から cookies.json を復元しました。")

# --- 検索キーワードとハッシュタグの対応 ---
KEYWORD_CONFIG = [
    {
        "keyword": "Nintendo Switch 本体",
        "hashtags": "#NintendoSwitch #スイッチ #入荷情報 #ゲーム",
    },
    {
        "keyword": "PlayStation5 本体",
        "hashtags": "#PS5 #PlayStation5 #入荷情報 #ゲーム",
    },
    {
        "keyword": "ポケモンカード スカーレット",
        "hashtags": "#ポケモンカード #ポケカ #スカーレット #入荷情報",
    },
    {
        "keyword": "ポケモンカード バイオレット",
        "hashtags": "#ポケモンカード #ポケカ #バイオレット #入荷情報",
    },
    {
        "keyword": "S.H.Figuarts フィギュア",
        "hashtags": "#SHフィギュアーツ #フィギュア #入荷情報",
    },
    {
        "keyword": "ねんどろいど フィギュア",
        "hashtags": "#ねんどろいど #nendoroid #フィギュア #入荷情報",
    },
    {
        "keyword": "figma フィギュア",
        "hashtags": "#figma #フィギュア #入荷情報",
    },
]

RAKUTEN_SEARCH_URL = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20220601"


def fetch_rakuten_item(config: dict) -> dict | None:
    """楽天商品検索APIで在庫ありの商品を1件取得する"""
    params = {
        "applicationId":  RAKUTEN_APP_ID,
        "accessKey":      RAKUTEN_ACCESS_KEY,
        "affiliateId":    RAKUTEN_AFFILIATE_ID,
        "keyword":        config["keyword"],
        "availability":   1,
        "hits":           10,
        "sort":           "standard",
        "imageFlag":      1,
        "formatVersion":  2,
    }

    try:
        headers = {"Origin": "https://github.com/", "Referer": "https://github.com/"}
        response = requests.get(RAKUTEN_SEARCH_URL, params=params, headers=headers, timeout=10)
        if response.status_code != 200:
            print("楽天APIエラー詳細:", response.text)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"[ERROR] 楽天API呼び出し失敗: {e}")
        return None

    data = response.json()
    items = data.get("Items", [])
    if not items:
        print(f"[INFO] 商品が見つかりませんでした: {config['keyword']}")
        return None

    item = random.choice(items)
    url = item.get("affiliateUrl") or item.get("itemUrl", "")
    images = item.get("mediumImageUrls", [])
    image_url = images[0] if images else ""

    return {
        "name":      item.get("itemName", ""),
        "price":     item.get("itemPrice", 0),
        "url":       url,
        "image_url": image_url,
        "hashtags":  config["hashtags"],
    }


def build_tweet(item: dict) -> str:
    """投稿文を生成する"""
    name  = item["name"][:40] + "…" if len(item["name"]) > 40 else item["name"]
    price = f"{item['price']:,}"
    url   = item["url"]
    tags  = item["hashtags"]

    return (
        f"🚨入荷速報🚨\n"
        f"【{name}】が楽天に入荷・販売中！\n"
        f"💰価格: {price}円\n\n"
        f"👇購入はこちらから（早い者勝ち！）\n"
        f"{url}\n\n"
        f"{tags}"
    )


# ---------------------------------------------------------------------------
# Playwright ユーティリティ
# ---------------------------------------------------------------------------

def _load_cookies() -> list[dict]:
    """cookies.json を Playwright の add_cookies 形式で返す。
    旧形式（{name: value} の dict）も自動変換する。
    """
    raw = json.loads(COOKIES_FILE.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        # twikit 形式 → Playwright 形式に変換
        return [
            {"name": k, "value": v, "domain": ".x.com", "path": "/"}
            for k, v in raw.items()
        ]
    return raw


def _save_cookies(context: BrowserContext) -> None:
    """現在のコンテキストのクッキーを cookies.json に保存する"""
    cookies = context.cookies()
    COOKIES_FILE.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")


def _login(page: Page) -> None:
    """ユーザー名・パスワードで X にログインし、クッキーを更新する"""
    if not TWITTER_USERNAME or not TWITTER_PASSWORD:
        raise RuntimeError(
            "セッションが切れています。TWITTER_USERNAME と TWITTER_PASSWORD を "
            "GitHub Secrets または .env に設定してください。"
        )

    print("[INFO] ログインフローを開始します...")
    page.goto("https://x.com/i/flow/login", wait_until="domcontentloaded")

    # ユーザー名入力
    page.wait_for_selector('input[autocomplete="username"]', timeout=15000)
    page.fill('input[autocomplete="username"]', TWITTER_USERNAME)
    page.keyboard.press("Enter")

    # メールアドレス確認が挟まる場合に対応
    try:
        email_input = page.wait_for_selector('input[data-testid="ocfEnterTextTextInput"]', timeout=5000)
        if email_input and TWITTER_EMAIL:
            print("[INFO] メールアドレス確認ステップを検知しました。")
            email_input.fill(TWITTER_EMAIL)
            page.keyboard.press("Enter")
    except Exception:
        pass  # 確認ステップなし

    # パスワード入力
    page.wait_for_selector('input[name="password"]', timeout=15000)
    page.fill('input[name="password"]', TWITTER_PASSWORD)
    page.keyboard.press("Enter")

    # ホームへのリダイレクトを待機
    page.wait_for_url("**/home", timeout=30000)

    _save_cookies(page.context)
    print("[OK] 再ログイン完了。クッキーを更新しました。")


def post_to_twitter(text: str) -> None:
    """Playwright でツイートを投稿する"""
    if not COOKIES_FILE.exists():
        raise FileNotFoundError(
            f"{COOKIES_FILE} が見つかりません。\n"
            "先に `python save_cookies.py` を実行して X にログインし、クッキーを保存してください。"
        )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_cookies(_load_cookies())

        page = context.new_page()
        page.goto("https://x.com/compose/post", wait_until="domcontentloaded")

        # ログイン状態の確認（投稿モーダルのテキストエリアが出るか）
        try:
            page.wait_for_selector('[data-testid="tweetTextarea_0"]', timeout=8000)
            print("[INFO] セッション有効。投稿モーダルを確認しました。")
        except Exception:
            print("[INFO] セッション切れを検知。再ログインします...")
            _login(page)
            page.goto("https://x.com/compose/post", wait_until="domcontentloaded")
            page.wait_for_selector('[data-testid="tweetTextarea_0"]', timeout=15000)

        # テキストエリアに投稿文を入力
        textarea = page.locator('div[role="textbox"][data-testid="tweetTextarea_0"]').first
        textarea.click()
        page.keyboard.type(text)

        # 投稿ボタンをクリック（X側のJSがボタンを有効化するまで1秒待機）
        page.wait_for_timeout(1000)
        post_btn = page.get_by_test_id("tweetButton")
        if not post_btn.is_visible():
            post_btn = page.get_by_role("button", name="ポストする")
        post_btn.click(force=True)

        # 投稿完了を確認（3秒待機後にホーム画面またはURLで成功判定）
        page.wait_for_timeout(3000)

        # エラーポップアップの検出
        error_selectors = [
            '[data-testid="toast"]',
            '[role="alert"]',
        ]
        for sel in error_selectors:
            error_el = page.locator(sel).first
            if error_el.is_visible():
                error_text = error_el.inner_text()
                if any(kw in error_text for kw in ["失敗", "エラー", "error", "failed", "Something went wrong"]):
                    raise RuntimeError(f"投稿エラーを検出しました: {error_text}")

        # ホーム画面への遷移 or タイムラインの表示を確認
        current_url = page.url
        if "x.com/home" in current_url:
            print("[OK] ツイート投稿完了（URLがホームに遷移）")
        else:
            try:
                page.wait_for_selector('[data-testid="primaryColumn"]', timeout=5000)
                print("[OK] ツイート投稿完了（タイムライン表示を確認）")
            except Exception:
                print(f"[WARN] 投稿後のURL: {current_url} （ホーム遷移は未確認だが続行）")

        browser.close()


def main():
    config = random.choice(KEYWORD_CONFIG)
    print(f"[INFO] 検索キーワード: {config['keyword']}")

    item = fetch_rakuten_item(config)
    if not item:
        print("[INFO] 投稿対象の商品がないため終了します")
        return

    print(f"[INFO] 投稿対象: {item['name']} / {item['price']}円")

    tweet_text = build_tweet(item)
    print(f"[INFO] 投稿文:\n{tweet_text}")

    post_to_twitter(tweet_text)


if __name__ == "__main__":
    main()
