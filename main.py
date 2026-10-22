import time
from playwright.sync_api import sync_playwright
import telebot

# === CẤU HÌNH TELEGRAM ===
BOT_TOKEN = '8020465328:AAHLYP3wDab4hoo1PjnawxPM5I_BXQ2mOGI'
CHAT_ID = '-4948534546'  # VD: 123456789
bot = telebot.TeleBot(BOT_TOKEN)

# === GỬI THÔNG BÁO VỀ TELEGRAM ===
def send_telegram(username):
    link = f'https://www.tiktok.com/@{username}/live'
    message = f"🎁 LIVE có rương xu!\n👤 @{username}\n🔗 {link}"
    bot.send_message(CHAT_ID, message)

# === LẤY DANH SÁCH USER ĐANG LIVE TỪ /live ===
def get_live_usernames(page):
    page.goto("https://www.tiktok.com/live", timeout=20000)
    time.sleep(5)

    # Scroll để load thêm livestream
    for _ in range(3):
        page.mouse.wheel(0, 3000)
        time.sleep(1.5)

    usernames = set()
    elements = page.query_selector_all("a[href*='/@']")

    for el in elements:
        href = el.get_attribute("href")
        if href and "/live" in href:
            try:
                username = href.split("/@")[1].split("/")[0]
                usernames.add(username)
            except:
                continue
    return list(usernames)

# === KIỂM TRA LIVE ĐÓ CÓ RƯƠNG XU KHÔNG ===
def check_user_live(page, username):
    url = f"https://www.tiktok.com/@{username}/live"
    try:
        page.goto(url, timeout=15000)
        time.sleep(5)
        html = page.content().lower()
        return ("rương xu" in html or "treasure" in html or "chest" in html)
    except:
        return False

# === MAIN LOOP: QUÉT MỖI 30 GIÂY ===
def scan_loop():
    sent_users = set()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        while True:
            try:
                print("🔍 Đang quét TikTok LIVE...")
                usernames = get_live_usernames(page)
                print(f"🔗 Tìm thấy {len(usernames)} users đang LIVE")

                for username in usernames:
                    if username in sent_users:
                        continue

                    if check_user_live(page, username):
                        print(f"🎁 Có rương xu: @{username}")
                        send_telegram(username)
                        sent_users.add(username)
                    else:
                        print(f"✖ Không có rương xu: @{username}")

                print("⏱️ Đợi 30 giây...")
                time.sleep(30)

            except Exception as e:
                print("❌ Lỗi:", e)
                time.sleep(30)

        browser.close()

# === CHẠY TOOL ===
if __name__ == "__main__":
    scan_loop()
