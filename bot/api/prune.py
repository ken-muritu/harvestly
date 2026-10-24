"""Vercel Cron target (daily): deletes chats idle for 30 days and update ids older than 2 days (B6-01).

Vercel sends `Authorization: Bearer <CRON_SECRET>` to cron invocations when the CRON_SECRET env var is set; anything
else gets 401. The response carries no data about what was deleted beyond "ok"."""
import hashlib
import hmac
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import webhook                          # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def authorised(header, secret):
    if not secret or not header or not header.startswith("Bearer "):
        return False
    return hmac.compare_digest(hashlib.sha256(header[7:].encode()).digest(), hashlib.sha256(secret.encode()).digest())


def run(header, env, backend=None):
    """Returns (status, text). Fails closed (401) if CRON_SECRET is unset or the header is wrong."""
    if not authorised(header, env.get("CRON_SECRET")):
        return 401, "unauthorized"
    if backend is None:
        if not (env.get("TURSO_URL") and env.get("TURSO_TOKEN")):
            return 503, "not configured"
        backend = webhook.TursoBackend(env["TURSO_URL"], env["TURSO_TOKEN"])
    try:
        webhook.prune_now(backend)
    except Exception as e:
        logging.getLogger("harvestly-bot").error("prune failed: %s", type(e).__name__)
        return 500, "failed"
    logging.getLogger("harvestly-bot").info("prune ok")
    return 200, "ok"


class handler(BaseHTTPRequestHandler):
    def _reply(self, code, text):
        data = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):                   # Vercel Cron issues GET
        self._reply(*run(self.headers.get("Authorization"), os.environ))

    def do_POST(self):
        self._reply(405, "method not allowed")

    do_PUT = do_DELETE = do_PATCH = do_POST

    def log_message(self, *a):
        pass
