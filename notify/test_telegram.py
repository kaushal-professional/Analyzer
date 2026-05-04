"""Unit tests for notify.telegram."""
import json
from unittest.mock import patch, MagicMock
from urllib.error import URLError

import pytest


class TestSendMessage:
    def test_uses_default_chat_id_from_settings(self, monkeypatch):
        from notify import telegram as t
        monkeypatch.setattr(t, "TELEGRAM_BOT_TOKEN", "BOT123")
        monkeypatch.setattr(t, "TELEGRAM_CHAT_ID", "111")

        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode())
            resp = MagicMock()
            resp.status = 200
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda *a: None
            return resp

        with patch("notify.telegram.urlopen", side_effect=fake_urlopen):
            ok = t.send_message("hello")

        assert ok is True
        assert captured["url"] == "https://api.telegram.org/botBOT123/sendMessage"
        assert captured["body"] == {"chat_id": "111", "text": "hello"}

    def test_explicit_chat_id_overrides_default(self, monkeypatch):
        from notify import telegram as t
        monkeypatch.setattr(t, "TELEGRAM_BOT_TOKEN", "BOT123")
        monkeypatch.setattr(t, "TELEGRAM_CHAT_ID", "111")

        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode())
            resp = MagicMock()
            resp.status = 200
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda *a: None
            return resp

        with patch("notify.telegram.urlopen", side_effect=fake_urlopen):
            ok = t.send_message("hello", chat_id=42)

        assert ok is True
        assert captured["body"]["chat_id"] == 42

    def test_retries_on_transient_urlerror_then_succeeds(self, monkeypatch):
        from notify import telegram as t
        monkeypatch.setattr(t, "TELEGRAM_BOT_TOKEN", "BOT")
        monkeypatch.setattr(t, "TELEGRAM_CHAT_ID", "111")
        monkeypatch.setattr(t, "_RETRY_DELAY", 0)

        attempts = {"n": 0}

        def fake_urlopen(req, timeout=None):
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise URLError("transient")
            resp = MagicMock()
            resp.status = 200
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda *a: None
            return resp

        with patch("notify.telegram.urlopen", side_effect=fake_urlopen):
            ok = t.send_message("hello")
        assert ok is True
        assert attempts["n"] == 3

    def test_returns_false_after_max_retries(self, monkeypatch):
        from notify import telegram as t
        monkeypatch.setattr(t, "TELEGRAM_BOT_TOKEN", "BOT")
        monkeypatch.setattr(t, "TELEGRAM_CHAT_ID", "111")
        monkeypatch.setattr(t, "_RETRY_DELAY", 0)

        with patch("notify.telegram.urlopen", side_effect=URLError("down")):
            ok = t.send_message("hello")
        assert ok is False

    def test_returns_false_when_bot_token_missing(self, monkeypatch):
        from notify import telegram as t
        monkeypatch.setattr(t, "TELEGRAM_BOT_TOKEN", None)
        monkeypatch.setattr(t, "TELEGRAM_CHAT_ID", "111")
        # No urlopen patch — function should short-circuit before any HTTP call.
        ok = t.send_message("hello")
        assert ok is False


import threading
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def _start_test_server(monkeypatch, secret="SECRET", chat_id_env="111"):
    """Start the webhook server on a random free port and return (server, port)."""
    from notify import telegram as t
    monkeypatch.setattr(t, "TELEGRAM_WEBHOOK_SECRET", secret)
    monkeypatch.setattr(t, "TELEGRAM_CHAT_ID", chat_id_env)
    server = ThreadingHTTPServer(("127.0.0.1", 0), t._TelegramHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def _post(port, body: dict, headers: dict | None = None) -> tuple[int, str]:
    """POST JSON to the test server. Returns (status, body_text). HTTPError → (code, '')."""
    data = json.dumps(body).encode()
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = Request(f"http://127.0.0.1:{port}/", data=data, headers=h, method="POST")
    try:
        with urlopen(req, timeout=5) as resp:
            return resp.status, resp.read().decode()
    except HTTPError as e:
        return e.code, ""


class TestTelegramHandler:
    def test_missing_secret_header_returns_401(self, monkeypatch):
        server, port = _start_test_server(monkeypatch, secret="SECRET")
        try:
            status, _ = _post(port, {"message": {"chat": {"id": 111}, "text": "/frc"}})
            assert status == 401
        finally:
            server.shutdown()

    def test_wrong_secret_header_returns_401(self, monkeypatch):
        server, port = _start_test_server(monkeypatch, secret="SECRET")
        try:
            status, _ = _post(
                port,
                {"message": {"chat": {"id": 111}, "text": "/frc"}},
                headers={"X-Telegram-Bot-Api-Secret-Token": "WRONG"},
            )
            assert status == 401
        finally:
            server.shutdown()

    def test_malformed_json_returns_400(self, monkeypatch):
        server, port = _start_test_server(monkeypatch, secret="SECRET")
        try:
            req = Request(
                f"http://127.0.0.1:{port}/",
                data=b"{not json",
                headers={
                    "Content-Type": "application/json",
                    "X-Telegram-Bot-Api-Secret-Token": "SECRET",
                },
                method="POST",
            )
            try:
                urlopen(req, timeout=5)
                assert False, "expected HTTPError"
            except HTTPError as e:
                assert e.code == 400
        finally:
            server.shutdown()

    def test_chat_id_mismatch_returns_200_no_login(self, monkeypatch):
        server, port = _start_test_server(monkeypatch, secret="SECRET", chat_id_env="111")
        from notify import telegram as t
        called = {"frc": 0}
        monkeypatch.setattr(t, "_handle_frc", lambda update: called.__setitem__("frc", called["frc"] + 1))
        try:
            status, _ = _post(
                port,
                {"message": {"chat": {"id": 999}, "text": "/frc"}},
                headers={"X-Telegram-Bot-Api-Secret-Token": "SECRET"},
            )
            assert status == 200
            __import__("time").sleep(0.05)
            assert called["frc"] == 0
        finally:
            server.shutdown()

    def test_unknown_command_returns_200_no_login(self, monkeypatch):
        server, port = _start_test_server(monkeypatch, secret="SECRET", chat_id_env="111")
        from notify import telegram as t
        called = {"frc": 0}
        monkeypatch.setattr(t, "_handle_frc", lambda update: called.__setitem__("frc", called["frc"] + 1))
        try:
            status, _ = _post(
                port,
                {"message": {"chat": {"id": 111}, "text": "/something_else"}},
                headers={"X-Telegram-Bot-Api-Secret-Token": "SECRET"},
            )
            assert status == 200
            __import__("time").sleep(0.05)
            assert called["frc"] == 0
        finally:
            server.shutdown()

    def test_frc_with_valid_secret_and_chat_dispatches(self, monkeypatch):
        server, port = _start_test_server(monkeypatch, secret="SECRET", chat_id_env="111")
        from notify import telegram as t
        called = {"frc": 0, "update": None}
        done = threading.Event()

        def fake_handle(update):
            called["frc"] += 1
            called["update"] = update
            done.set()

        monkeypatch.setattr(t, "_handle_frc", fake_handle)
        try:
            status, _ = _post(
                port,
                {"message": {"chat": {"id": 111}, "text": "/frc"}},
                headers={"X-Telegram-Bot-Api-Secret-Token": "SECRET"},
            )
            assert status == 200
            # Handler runs after the 200 is sent, in the request thread.
            # Wait deterministically (up to 2s) instead of a fixed sleep that
            # gets flaky on loaded CI.
            assert done.wait(timeout=2.0), "handler did not run within 2s"
            assert called["frc"] == 1
            assert called["update"]["message"]["text"] == "/frc"
        finally:
            server.shutdown()

    def test_chat_id_unconfigured_rejects_all(self, monkeypatch):
        # When TELEGRAM_CHAT_ID is None (env var unset), even a request with a
        # chat_id should NOT dispatch — it would otherwise silently appear to
        # work while ignoring all real traffic.
        server, port = _start_test_server(monkeypatch, secret="SECRET", chat_id_env=None)
        from notify import telegram as t
        called = {"frc": 0}
        monkeypatch.setattr(t, "_handle_frc", lambda update: called.__setitem__("frc", called["frc"] + 1))
        try:
            status, _ = _post(
                port,
                {"message": {"chat": {"id": 111}, "text": "/frc"}},
                headers={"X-Telegram-Bot-Api-Secret-Token": "SECRET"},
            )
            assert status == 200
            __import__("time").sleep(0.05)
            assert called["frc"] == 0
        finally:
            server.shutdown()


class TestHandleFrc:
    def test_success_path_sends_two_messages(self, monkeypatch):
        from notify import telegram as t
        sent = []
        monkeypatch.setattr(t, "send_message",
                            lambda text, chat_id=None: sent.append((text, chat_id)) or True)
        monkeypatch.setattr(t, "force_full_login",
                            lambda: {"access_token": "a", "refresh_token": "r"})

        update = {"message": {"chat": {"id": 555}, "text": "/frc"}}
        t._handle_frc(update)

        assert len(sent) == 2  # "🔄 Forcing..." + "✅ Re-login complete..."
        assert "Forcing" in sent[0][0]
        assert "Re-login complete" in sent[1][0]
        # Replies route to the originating chat
        assert sent[0][1] == 555
        assert sent[1][1] == 555

    def test_failure_path_sends_failure_message(self, monkeypatch):
        from notify import telegram as t
        sent = []
        monkeypatch.setattr(t, "send_message",
                            lambda text, chat_id=None: sent.append((text, chat_id)) or True)
        monkeypatch.setattr(t, "force_full_login", lambda: {})

        update = {"message": {"chat": {"id": 555}, "text": "/frc"}}
        t._handle_frc(update)

        assert len(sent) == 2
        assert "Forcing" in sent[0][0]
        assert "Re-login failed" in sent[1][0]
        assert sent[1][1] == 555

    def test_exception_in_login_sends_internal_error(self, monkeypatch):
        from notify import telegram as t
        sent = []
        monkeypatch.setattr(t, "send_message",
                            lambda text, chat_id=None: sent.append((text, chat_id)) or True)

        def boom():
            raise RuntimeError("kaboom")
        monkeypatch.setattr(t, "force_full_login", boom)

        update = {"message": {"chat": {"id": 555}, "text": "/frc"}}
        t._handle_frc(update)  # must NOT raise

        assert any("Internal error" in text for text, _ in sent)


class TestRegisterBot:
    def test_calls_setwebhook_and_setmycommands(self, monkeypatch):
        from notify import telegram as t
        monkeypatch.setattr(t, "TELEGRAM_BOT_TOKEN", "BOT")
        monkeypatch.setattr(t, "TELEGRAM_WEBHOOK_URL", "https://example.com/tg")
        monkeypatch.setattr(t, "TELEGRAM_WEBHOOK_SECRET", "SECRET")

        calls = []

        def fake_urlopen(req, timeout=None):
            calls.append((req.full_url, json.loads(req.data.decode())))
            resp = MagicMock()
            resp.status = 200
            resp.__enter__ = lambda s: s
            resp.__exit__ = lambda *a: None
            return resp

        with patch("notify.telegram.urlopen", side_effect=fake_urlopen):
            t.register_bot()

        urls = [c[0] for c in calls]
        assert any(u.endswith("/setWebhook") for u in urls)
        assert any(u.endswith("/setMyCommands") for u in urls)

        webhook_call = next(c for c in calls if c[0].endswith("/setWebhook"))
        assert webhook_call[1] == {
            "url": "https://example.com/tg",
            "secret_token": "SECRET",
        }

        commands_call = next(c for c in calls if c[0].endswith("/setMyCommands"))
        assert commands_call[1] == {
            "commands": [{"command": "frc", "description": "Force Fyers re-login"}]
        }

    def test_failure_is_non_fatal(self, monkeypatch):
        from notify import telegram as t
        monkeypatch.setattr(t, "TELEGRAM_BOT_TOKEN", "BOT")
        monkeypatch.setattr(t, "TELEGRAM_WEBHOOK_URL", "https://example.com/tg")
        monkeypatch.setattr(t, "TELEGRAM_WEBHOOK_SECRET", "SECRET")

        with patch("notify.telegram.urlopen", side_effect=URLError("down")):
            # Must not raise.
            t.register_bot()

    def test_skips_when_token_or_url_missing(self, monkeypatch):
        from notify import telegram as t
        monkeypatch.setattr(t, "TELEGRAM_BOT_TOKEN", None)
        monkeypatch.setattr(t, "TELEGRAM_WEBHOOK_URL", None)
        monkeypatch.setattr(t, "TELEGRAM_WEBHOOK_SECRET", None)
        # Should silently no-op (and not call urlopen).
        with patch("notify.telegram.urlopen") as m:
            t.register_bot()
            m.assert_not_called()

    def test_skips_when_secret_missing(self, monkeypatch):
        # Without a secret, do_POST would reject every request with 401, making
        # registration counterproductive (Telegram retries → log noise → no /frc).
        from notify import telegram as t
        monkeypatch.setattr(t, "TELEGRAM_BOT_TOKEN", "BOT")
        monkeypatch.setattr(t, "TELEGRAM_WEBHOOK_URL", "https://example.com/tg")
        monkeypatch.setattr(t, "TELEGRAM_WEBHOOK_SECRET", None)
        with patch("notify.telegram.urlopen") as m:
            t.register_bot()
            m.assert_not_called()
