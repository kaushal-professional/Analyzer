"""Entry point: start the gRPC server + auto-login scheduler + Telegram webhook.

Three concurrent components inside a single process:
  - main thread: gRPC server (blocks forever)
  - daemon thread: scheduler loop (Mon–Fri 09:13 IST auto-login)
  - daemon thread: Telegram webhook HTTP server (/frc command)

Plus a one-shot bootstrap that registers the webhook URL with Telegram and
advertises the /frc command. The bootstrap is best-effort: failure is
logged but does not block startup.
"""
# Use the OS trust store for HTTPS (required on Windows when an antivirus or
# corporate proxy intercepts SSL with a self-signed root that is in the OS
# trust store but NOT in certifi's bundle). Must run before any module that
# opens an SSL connection (urllib, requests, etc.).
import truststore
truststore.inject_into_ssl()

import logging
import threading

import config.settings as settings
import notify
import scheduler
from grpc_service.server import serve

logger = logging.getLogger(__name__)


def _start_daemon(target, name, *args):
    t = threading.Thread(target=target, args=args, name=name, daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s]: %(message)s",
    )

    # 1. One-shot Telegram bootstrap (non-fatal).
    notify.register_bot()

    # 2. Telegram webhook server thread.
    _start_daemon(
        notify.run_webhook_server,
        "telegram-webhook",
        settings.TELEGRAM_WEBHOOK_HOST,
        settings.TELEGRAM_WEBHOOK_PORT,
    )

    # 3. Scheduler thread (catch-up on boot, then daily 09:13 IST loop).
    _start_daemon(scheduler.run_scheduler_loop, "scheduler")

    # 4. gRPC server (blocks the main thread).
    serve(host=settings.GRPC_HOST, port=settings.GRPC_PORT)
