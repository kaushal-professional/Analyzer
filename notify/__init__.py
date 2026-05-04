"""Telegram notifications + webhook for Fyers auto-login.

Public API:
  - send_message(text, chat_id=None) — POST to Telegram sendMessage.
  - register_bot() — one-shot setWebhook + setMyCommands.
  - run_webhook_server(host, port) — bind ThreadingHTTPServer and serve forever.
"""
from notify.telegram import (
    register_bot,
    run_webhook_server,
    send_message,
)

__all__ = ["register_bot", "run_webhook_server", "send_message"]
