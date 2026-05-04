"""Telegram bot client + webhook server for Fyers auto-login notifications.

Uses stdlib only: urllib.request for HTTP, http.server for the webhook.
Reads TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_WEBHOOK_URL,
TELEGRAM_WEBHOOK_SECRET from config.settings.
"""
import hmac
import json
import logging
import time as _time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from auth.force_login import force_full_login
from config.settings import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TELEGRAM_WEBHOOK_HOST,
    TELEGRAM_WEBHOOK_PORT,
    TELEGRAM_WEBHOOK_SECRET,
    TELEGRAM_WEBHOOK_URL,
)

logger = logging.getLogger(__name__)

_IST = ZoneInfo("Asia/Kolkata")
_API_BASE = "https://api.telegram.org"
_MAX_RETRIES = 3
_RETRY_DELAY = 1  # seconds; tests monkeypatch this to 0
_HTTP_TIMEOUT = 10


def _now_ist_str() -> str:
    return datetime.now(_IST).strftime("%Y-%m-%d %H:%M:%S IST")


def send_message(text: str, chat_id: int | str | None = None) -> bool:
    """POST to Telegram sendMessage. Returns True on 2xx, False otherwise.

    chat_id: when None, falls back to TELEGRAM_CHAT_ID from env.
    """
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("send_message: TELEGRAM_BOT_TOKEN not set; skipping")
        return False
    target_chat = chat_id if chat_id is not None else TELEGRAM_CHAT_ID
    if target_chat is None:
        logger.warning("send_message: no chat_id and TELEGRAM_CHAT_ID not set; skipping")
        return False

    url = f"{_API_BASE}/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    body = json.dumps({"chat_id": target_chat, "text": text}).encode()
    headers = {"Content-Type": "application/json"}

    last_err = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            req = Request(url, data=body, headers=headers, method="POST")
            with urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
                if 200 <= resp.status < 300:
                    return True
                logger.warning(f"send_message: HTTP {resp.status}")
                return False
        except HTTPError as e:
            logger.warning(f"send_message: HTTPError {e.code}")
            return False
        except URLError as e:
            last_err = e
            logger.debug(f"send_message: URLError attempt {attempt}/{_MAX_RETRIES}: {e}")
            if attempt < _MAX_RETRIES:
                _time.sleep(_RETRY_DELAY)
    logger.error(f"send_message: gave up after {_MAX_RETRIES} attempts: {last_err}")
    return False


class _TelegramHandler(BaseHTTPRequestHandler):
    """Single-endpoint POST handler for Telegram updates.

    Order of operations in do_POST:
      1. Validate X-Telegram-Bot-Api-Secret-Token → 401 on mismatch.
      2. Read + parse JSON body → 400 on parse error.
      3. Validate update.message.chat.id == TELEGRAM_CHAT_ID → 200 + log on mismatch.
      4. Send 200 + flush (response on the wire BEFORE any slow work).
      5. Dispatch /frc synchronously in this same per-request thread.

    ThreadingHTTPServer assigns a fresh thread per request, so a slow /frc
    does not block subsequent updates.
    """

    server_version = "FyersAutoLogin/1.0"

    def log_message(self, fmt, *args):
        # Route BaseHTTPRequestHandler's stderr noise into our logger.
        logger.debug("webhook: " + fmt, *args)

    def _send(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()
        try:
            self.wfile.flush()
        except Exception:
            pass

    def do_POST(self):
        # 0. Drain the request body up-front. Reading even on rejection paths
        # avoids Windows TCP RST when the server closes the socket while the
        # client is still writing — that would abort the response with
        # ConnectionAbortedError before urllib could read the status code.
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length > 0 else b""

        # 1. Secret header — constant-time compare to avoid timing side-channel.
        secret = self.headers.get("X-Telegram-Bot-Api-Secret-Token") or ""
        if not TELEGRAM_WEBHOOK_SECRET or not hmac.compare_digest(secret, TELEGRAM_WEBHOOK_SECRET):
            logger.warning("webhook: rejected, bad secret header")
            self._send(401)
            return

        # 2. Parse body
        try:
            update = json.loads(raw.decode())
        except (ValueError, json.JSONDecodeError) as e:
            logger.warning(f"webhook: malformed JSON: {e}")
            self._send(400)
            return

        # 3. Chat-id allowlist
        if TELEGRAM_CHAT_ID is None:
            logger.error("webhook: TELEGRAM_CHAT_ID not configured; rejecting all messages")
            self._send(200)
            return
        try:
            incoming_chat_id = update["message"]["chat"]["id"]
        except (KeyError, TypeError):
            # Not a message update we care about (channel post, edit, etc.)
            self._send(200)
            return

        if str(incoming_chat_id) != str(TELEGRAM_CHAT_ID):
            logger.warning(f"webhook: rejected, chat_id {incoming_chat_id!r} != configured")
            self._send(200)
            return

        # 4. Send 200 NOW so Telegram doesn't time out / retry
        self._send(200)

        # 5. Dispatch /frc
        text = update.get("message", {}).get("text", "")
        if text == "/frc":
            try:
                _handle_frc(update)
            except Exception:
                logger.exception("webhook: _handle_frc raised")


def _handle_frc(update: dict) -> None:
    """Handle a /frc command: force a full TOTP login and reply to the originating chat."""
    chat_id = update["message"]["chat"]["id"]
    now_ist_str = _now_ist_str()
    send_message(f"🔄 Forcing Fyers re-login at {now_ist_str}...", chat_id=chat_id)
    try:
        tokens = force_full_login()
    except Exception:
        logger.exception("_handle_frc: force_full_login raised")
        send_message("❌ Internal error — check server logs", chat_id=chat_id)
        return
    if tokens.get("access_token"):
        send_message(f"✅ Re-login complete at {_now_ist_str()} — token valid 24h", chat_id=chat_id)
    else:
        send_message("❌ Re-login failed: see server logs for the failed step", chat_id=chat_id)


def run_webhook_server(host: str = TELEGRAM_WEBHOOK_HOST, port: int = TELEGRAM_WEBHOOK_PORT) -> None:
    """Bind ThreadingHTTPServer and serve forever. Called from a daemon thread.

    Wraps the entire body in a try/except so that a bind failure (port in use,
    permissions error) is logged at ERROR rather than silently killing the thread.
    The thread still exits — there is no recovery — but the operator gets a
    visible signal that /frc is now non-functional.
    """
    try:
        server = ThreadingHTTPServer((host, port), _TelegramHandler)
        logger.info(f"webhook: listening on {host}:{port}")
        server.serve_forever()
    except Exception:
        logger.exception(f"webhook: server died on {host}:{port} — /frc will not be available")


def register_bot() -> None:
    """One-shot startup: register webhook URL + advertise the /frc command.

    Failure is logged at WARNING and is non-fatal — the rest of the process
    starts regardless. If the webhook never gets registered, /frc simply
    won't reach us; restart the process once the public URL is live.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_WEBHOOK_URL:
        logger.warning("register_bot: TELEGRAM_BOT_TOKEN or TELEGRAM_WEBHOOK_URL not set; skipping")
        return
    if not TELEGRAM_WEBHOOK_SECRET:
        # Without a secret, do_POST rejects every request with 401. Registering the
        # webhook anyway would cause Telegram to keep retrying and produce log noise
        # with no actionable signal. Surface the misconfiguration loudly at startup.
        logger.warning(
            "register_bot: TELEGRAM_WEBHOOK_SECRET not set; webhook would reject all "
            "incoming requests with 401. Set the env var and restart. Skipping registration."
        )
        return

    set_webhook_url = f"{_API_BASE}/bot{TELEGRAM_BOT_TOKEN}/setWebhook"
    webhook_body = json.dumps({
        "url": TELEGRAM_WEBHOOK_URL,
        "secret_token": TELEGRAM_WEBHOOK_SECRET,
    }).encode()

    set_commands_url = f"{_API_BASE}/bot{TELEGRAM_BOT_TOKEN}/setMyCommands"
    commands_body = json.dumps({
        "commands": [{"command": "frc", "description": "Force Fyers re-login"}],
    }).encode()

    headers = {"Content-Type": "application/json"}

    for url, body, label in [
        (set_webhook_url, webhook_body, "setWebhook"),
        (set_commands_url, commands_body, "setMyCommands"),
    ]:
        try:
            req = Request(url, data=body, headers=headers, method="POST")
            with urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
                if 200 <= resp.status < 300:
                    logger.info(f"register_bot: {label} ✓")
                else:
                    logger.warning(f"register_bot: {label} HTTP {resp.status}")
        except (URLError, HTTPError) as e:
            logger.warning(f"register_bot: {label} failed: {e}")
