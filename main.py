import json
import logging
import os
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import telebot
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("tiktok-chest-bot")
BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
SCAN_INTERVAL = max(30, int(os.getenv("SCAN_INTERVAL", "60")))
bot = telebot.TeleBot(BOT_TOKEN)
stop = threading.Event()
status_lock = threading.Lock()
status = {"scanner": "starting", "telegram": "unchecked", "last_scan": None,
          "live_count": 0, "notifications_sent": 0}


def update_status(**values):
    with status_lock:
        status.update(values)


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/health"):
            self.send_error(404)
            return
        with status_lock:
            body = json.dumps(status).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


def verify_telegram():
    try:
        me = bot.get_me()
        member = bot.get_chat_member(CHAT_ID, me.id)
        if member.status in ("left", "kicked") or (
            member.status == "restricted" and not getattr(member, "can_send_messages", False)
        ):
            update_status(telegram="no_send_permission")
            log.error("Telegram bot has no permission to send to the configured chat")
            return False
        update_status(telegram="connected")
        log.info("Telegram authentication and configured chat membership verified")
        return True
    except Exception as exc:
        update_status(telegram="error")
        log.error("Telegram verification failed: %s (code=%s)",
                  type(exc).__name__, getattr(exc, "error_code", "unavailable"))
        return False


def get_live_usernames(page):
    response = page.goto("https://www.tiktok.com/live", timeout=30000,
                         wait_until="domcontentloaded")
    if response and response.status >= 400:
        raise RuntimeError("TikTok LIVE request rejected")
    page.wait_for_timeout(5000)
    for _ in range(3):
        if stop.is_set():
            return []
        page.mouse.wheel(0, 3000)
        page.wait_for_timeout(1500)
    usernames = set()
    for el in page.query_selector_all("a[href*='/@']"):
        href = el.get_attribute("href") or ""
        if "/@" in href and "/live" in href:
            username = href.split("/@", 1)[1].split("/", 1)[0].split("?", 1)[0]
            if username:
                usernames.add(username)
    return sorted(usernames)


def check_user_live(page, username):
    response = page.goto(f"https://www.tiktok.com/@{username}/live", timeout=30000,
                         wait_until="domcontentloaded")
    if response and response.status >= 400:
        return False
    page.wait_for_timeout(5000)
    # Heuristic inherited from the original bot; keyword matches aren't proof of a chest.
    body = page.locator("body").inner_text().lower()
    return any(word in body for word in ("rương xu", "treasure", "chest"))


def send_telegram(username):
    bot.send_message(CHAT_ID,
        f"🎁 Canlı yayımda sandıqla bağlı mətn aşkarlandı!\n"
        f"👤 @{username}\n🔗 https://www.tiktok.com/@{username}/live")
    with status_lock:
        status["notifications_sent"] += 1
    update_status(telegram="connected")


def scan_loop():
    sent_users = {}
    while not stop.is_set():
        if not verify_telegram():
            stop.wait(SCAN_INTERVAL)
            continue
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=True, args=["--disable-dev-shm-usage"])
                try:
                    page = browser.new_page()
                    log.info("Chromium started; TikTok scanner is running")
                    update_status(scanner="running")
                    while not stop.is_set():
                        usernames = get_live_usernames(page)
                        update_status(last_scan=int(time.time()), live_count=len(usernames),
                                      scanner="running" if usernames else "no_lives_found")
                        log.info("TikTok scan completed: %d live usernames", len(usernames))
                        now = time.monotonic()
                        sent_users = {u: t for u, t in sent_users.items() if now - t < 21600}
                        for username in usernames:
                            if stop.is_set():
                                break
                            if username in sent_users:
                                continue
                            try:
                                if check_user_live(page, username):
                                    send_telegram(username)
                                    sent_users[username] = time.monotonic()
                            except Exception as exc:
                                log.warning("Live check or notification failed: %s",
                                            type(exc).__name__)
                        stop.wait(SCAN_INTERVAL)
                finally:
                    browser.close()
        except Exception as exc:
            update_status(scanner="retrying")
            log.error("Scanner failed; retrying: %s", type(exc).__name__)
            stop.wait(SCAN_INTERVAL)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_args: stop.set())
    signal.signal(signal.SIGINT, lambda *_args: stop.set())
    server = ThreadingHTTPServer(("0.0.0.0", int(os.getenv("PORT", "10000"))),
                                 HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log.info("Health server listening; credentials are loaded from the environment")
    try:
        scan_loop()
    finally:
        server.shutdown()
        server.server_close()
