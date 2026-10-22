import asyncio
import re
from collections import deque
import json
import logging
import os
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import telebot
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, DisconnectEvent, EnvelopeEvent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("tiktok-chest-bot")
BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
SCAN_INTERVAL = max(30, int(os.getenv("SCAN_INTERVAL", "60")))
bot = telebot.TeleBot(BOT_TOKEN)
stop = threading.Event()
status_lock = threading.Lock()
status = {"scanner": "starting", "telegram": "unchecked", "last_scan": None,
          "live_count": 0, "notifications_sent": 0, "connected_rooms": 0,
          "detection": "EnvelopeEvent", "coverage": "discovered_live_rooms",
          "discovery": "starting", "last_error": None}


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


MAX_ROOMS = max(1, min(8, int(os.getenv("MAX_ROOMS", "3"))))
MONITOR_SECONDS = max(60, int(os.getenv("MONITOR_SECONDS", "180")))
USERNAME = re.compile(r"^[A-Za-z0-9_.]{1,30}$")
candidates = deque(maxlen=400)
connected = set()
active = set()
cooldown = {}
seen_events = {}
send_lock = None


async def pause(seconds):
    end = time.monotonic() + seconds
    while not stop.is_set() and time.monotonic() < end:
        await asyncio.sleep(min(1, max(0, end - time.monotonic())))


def add_candidates(usernames):
    for username in usernames:
        username = username.lstrip("@").strip()
        if USERNAME.fullmatch(username) and username not in candidates:
            candidates.append(username)


def public_live_names():
    # Read only the public discovery page; never bypass login or challenges.
    import urllib.request
    request = urllib.request.Request("https://www.tiktok.com/live",
        headers={"User-Agent": "TikTokChestBot/1.0"})
    with urllib.request.urlopen(request, timeout=25) as response:
        html = response.read(3000000).decode("utf-8", errors="replace")
    return sorted(set(re.findall(r"/@([A-Za-z0-9_.]+)/live", html)))


async def discover():
    add_candidates(os.getenv("TIKTOK_USERNAMES", "").replace("\n", ",").split(","))
    while not stop.is_set():
        try:
            names = await asyncio.to_thread(public_live_names)
            add_candidates(names)
            update_status(last_scan=int(time.time()), live_count=len(names),
                discovery="ready" if names else "no_lives_found",
                scanner="monitoring" if connected else "waiting_for_rooms")
            log.info("Public discovery completed: %d live rooms; %d queued",
                     len(names), len(candidates))
        except Exception as exc:
            update_status(discovery="error", last_error="discovery_"+type(exc).__name__)
            log.warning("Public discovery failed: %s", type(exc).__name__)
        await pause(120)


def envelope_details(event):
    info = event.envelope_info
    if info is None or int(event.display) != 1 or not info.envelope_id:
        return None
    unpack_at = int(info.unpack_at or 0)
    if unpack_at and unpack_at <= time.time():
        return None
    return info.envelope_id, unpack_at, info.diamond_count, info.people_count


async def notify_envelope(username, event):
    details = envelope_details(event)
    if details is None:
        return
    envelope_id, unpack_at, amount, people = details
    key = (username, envelope_id)
    async with send_lock:
        now = time.time()
        for old_key in list(seen_events):
            if now - seen_events[old_key] > 86400:
                del seen_events[old_key]
        if key in seen_events:
            return
        message = f"🎁 TikTok LIVE: sandıq hadisəsi aşkarlandı!\n👤 @{username}\n"
        if amount:
            message += f"💰 Miqdar: {amount}\n"
        if people:
            message += f"👥 İştirakçı sayı: {people}\n"
        if unpack_at:
            message += f"⏳ Açılmasına təxminən {max(0, int(unpack_at-time.time()))} saniyə\n"
        message += f"🔗 https://www.tiktok.com/@{username}/live"
        for attempt in range(3):
            if unpack_at and unpack_at <= time.time():
                return
            try:
                await asyncio.to_thread(bot.send_message, CHAT_ID, message, timeout=20)
                seen_events[key] = time.time()
                if len(seen_events) > 2000:
                    del seen_events[next(iter(seen_events))]
                with status_lock:
                    status["notifications_sent"] += 1
                update_status(telegram="connected")
                log.info("Envelope notification delivered for @%s", username)
                return
            except Exception as exc:
                update_status(telegram="send_error",
                              last_error="telegram_"+type(exc).__name__)
                log.warning("Notification delivery failed: %s", type(exc).__name__)
                await pause(5 * (attempt+1))


async def monitor(username):
    client = TikTokLiveClient(unique_id=username, web_kwargs={"timeout": 20.0})
    client.logger.setLevel(logging.CRITICAL)
    @client.on(ConnectEvent)
    async def on_connect(_event):
        connected.add(username)
        update_status(connected_rooms=len(connected), scanner="monitoring")
        log.info("LIVE event connection established: @%s", username)

    @client.on(DisconnectEvent)
    async def on_disconnect(_event):
        connected.discard(username)
        update_status(connected_rooms=len(connected))

    @client.on(EnvelopeEvent)
    async def on_envelope(event):
        await notify_envelope(username, event)

    try:
        await asyncio.wait_for(client.connect(), timeout=MONITOR_SECONDS)
    except asyncio.TimeoutError:
        log.info("Monitor window completed: @%s", username)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        cooldown[username] = time.monotonic() + 300
        update_status(last_error="live_"+type(exc).__name__)
        log.warning("LIVE connection failed for @%s: %s", username, type(exc).__name__)
    finally:
        connected.discard(username)
        update_status(connected_rooms=len(connected))
        try:
            await asyncio.wait_for(client.disconnect(close_client=True), timeout=5)
        except (Exception, asyncio.CancelledError):
            await client.close()


async def worker(index):
    await pause(index * 5)
    while not stop.is_set():
        selected = None
        for _ in range(len(candidates)):
            username = candidates.popleft()
            candidates.append(username)
            if username not in active and cooldown.get(username, 0) <= time.monotonic():
                selected = username
                break
        if selected is None:
            await pause(5)
            continue
        active.add(selected)
        try:
            await monitor(selected)
        finally:
            active.discard(selected)
        await pause(10)


async def run():
    global send_lock
    send_lock = asyncio.Lock()
    while not stop.is_set() and not await asyncio.to_thread(verify_telegram):
        update_status(scanner="waiting_for_telegram")
        await pause(30)
    if stop.is_set():
        return
    tasks = [asyncio.create_task(discover())]
    tasks.extend(asyncio.create_task(worker(i)) for i in range(MAX_ROOMS))
    try:
        while not stop.is_set():
            # Surface task failures rather than leaving a falsely healthy scanner.
            for task in tasks:
                if task.done():
                    task.result()
                    raise RuntimeError("monitor_task_stopped")
            await asyncio.sleep(1)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_args: stop.set())
    signal.signal(signal.SIGINT, lambda *_args: stop.set())
    server = ThreadingHTTPServer(("0.0.0.0", int(os.getenv("PORT", "10000"))),
                                 HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log.info("Health server listening; secrets loaded from environment")
    try:
        asyncio.run(run())
    finally:
        server.shutdown()
        server.server_close()
