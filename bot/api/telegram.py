"""Vercel Python function: Telegram webhook for @HarvestlyBot (stdlib only)."""
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import harvestly_engine as H            # noqa: E402
import webhook                          # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
PHOTO_BASE = "https://harvestly-bot.vercel.app"


class handler(BaseHTTPRequestHandler):
    def _reply(self, code, text):
        data = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        env = os.environ
        given = self.headers.get("X-Telegram-Bot-Api-Secret-Token")
        # N6-08: authenticate first, so an unauthenticated caller learns nothing about the configuration
        if not webhook.secret_ok(given, env.get("TELEGRAM_WEBHOOK_SECRET")):
            return self._reply(401, "unauthorized")
        if not (env.get("TELEGRAM_BOT_TOKEN") and env.get("TURSO_URL") and env.get("TURSO_TOKEN") and env.get("STATE_SALT")):
            return self._reply(503, "not configured")
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        try:
            body = self.rfile.read(min(n, webhook.MAX_BODY + 1)) if n > 0 else b""
            code, text = webhook.process(
                body, given, env["TELEGRAM_WEBHOOK_SECRET"],
                webhook.TursoBackend(env["TURSO_URL"], env["TURSO_TOKEN"]), webhook.Transport(env["TELEGRAM_BOT_TOKEN"]),
                H, env["STATE_SALT"], env.get("PHOTO_BASE", PHOTO_BASE))
        except Exception as e:               # B6-04: log the class only (no text, ids, token or stack); 200 stops retries
            logging.getLogger("harvestly-bot").error("unhandled error: %s", type(e).__name__)
            code, text = 200, "error"
        self._reply(code, text)

    def do_GET(self):
        self._reply(405, "method not allowed")

    do_PUT = do_DELETE = do_PATCH = do_GET

    def log_message(self, *a):          # no access log lines (they would carry nothing useful, keep quiet)
        pass
