"""Telegram webhook logic, independent of Vercel and of the network: process() takes the raw request and
injected transport/backend, so tests use fakes. No message text, chat id or token is ever logged."""
import hashlib
import hmac
import json
import logging
import os
import random
import time
import urllib.error
import urllib.request

import harvestly_bot_core as core

log = logging.getLogger("harvestly-bot")
MAX_BODY = 64 * 1024
CHAT_TTL_DAYS = 30            # chat state not touched for 30 days is deleted
UPDATE_TTL_DAYS = 2           # dedupe ids kept 2 days
PRUNE_ODDS = 25               # prune on about 1 in 25 requests


# ------------------------------------------------------------------------------------------ Telegram transport
class Transport:
    def __init__(self, token):
        self._token = token

    def call(self, method, params=None, timeout=20):
        req = urllib.request.Request(f"https://api.telegram.org/bot{self._token}/{method}",
                                     data=json.dumps(params or {}).encode(), headers={"Content-Type": "application/json"})
        scrub = lambda s: str(s).replace(self._token, "<token>")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read().decode("utf-8", "replace"))
            except Exception:
                body = {}
            raise core.TelegramError(f"HTTP {e.code} {scrub(body.get('description', ''))[:120]}", e.code,
                                     (body.get("parameters") or {}).get("retry_after")) from None
        except Exception as e:
            raise core.TelegramError(f"{type(e).__name__}: {scrub(e)[:120]}") from None
        if not body.get("ok"):
            raise core.TelegramError(scrub(body.get("description", "not ok"))[:120], body.get("error_code"),
                                     (body.get("parameters") or {}).get("retry_after"))
        return body.get("result")

    def upload(self, *a, **k):          # photos are sent by URL in the webhook
        raise core.TelegramError("upload not supported")


# ------------------------------------------------------------------------------------------ state backends
class MemoryBackend:
    """In-memory backend used by tests; same interface as TursoBackend."""

    def __init__(self):
        self.chats, self.updates = {}, {}

    def begin(self, update_id, key, now):
        """Atomically claim update_id. Returns (is_new, state_json_or_None)."""
        if update_id in self.updates:
            return False, None
        self.updates[update_id] = now
        row = self.chats.get(key)
        return True, row[0] if row else None

    def save(self, key, state_json, now):
        self.chats[key] = (state_json, now)

    def release(self, update_id):
        self.updates.pop(update_id, None)

    def prune(self, now):
        self.chats = {k: v for k, v in self.chats.items() if v[1] >= now - CHAT_TTL_DAYS * 86400}
        self.updates = {k: v for k, v in self.updates.items() if v >= now - UPDATE_TTL_DAYS * 86400}


class TursoBackend:
    """Turso over its HTTP pipeline API (stdlib). Tables chats(key,state,updated) and updates(update_id,ts)."""

    def __init__(self, url, token, timeout=8):
        self.base = url.replace("libsql://", "https://").rstrip("/") + "/v2/pipeline"
        self.token, self.timeout = token, timeout

    @staticmethod
    def _arg(v):
        return {"type": "integer", "value": str(v)} if isinstance(v, int) else {"type": "text", "value": v}

    def _run(self, stmts):
        reqs = [{"type": "execute", "stmt": {"sql": s, "args": [self._arg(a) for a in args]}} for s, args in stmts]
        reqs.append({"type": "close"})
        req = urllib.request.Request(self.base, data=json.dumps({"requests": reqs}).encode(),
                                     headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                res = json.loads(r.read().decode())["results"]
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"turso HTTP {e.code}") from None
        except Exception as e:
            raise RuntimeError(f"turso {type(e).__name__}") from None
        out = []
        for x in res[:-1]:
            if x.get("type") != "ok":
                raise RuntimeError("turso statement error")
            out.append(x["response"]["result"])
        return out

    def begin(self, update_id, key, now):
        ins, sel = self._run([("INSERT OR IGNORE INTO updates(update_id, ts) VALUES (?, ?)", [update_id, now]),
                              ("SELECT state FROM chats WHERE key = ?", [key])])
        if not ins.get("affected_row_count"):
            return False, None
        rows = sel.get("rows") or []
        return True, rows[0][0]["value"] if rows else None

    def save(self, key, state_json, now):
        self._run([("INSERT INTO chats(key, state, updated) VALUES (?, ?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET state = excluded.state, updated = excluded.updated",
                    [key, state_json, now])])

    def release(self, update_id):
        self._run([("DELETE FROM updates WHERE update_id = ?", [update_id])])

    def prune(self, now):
        self._run([("DELETE FROM chats WHERE updated < ?", [now - CHAT_TTL_DAYS * 86400]),
                   ("DELETE FROM updates WHERE ts < ?", [now - UPDATE_TTL_DAYS * 86400])])


class ChatStore:
    """What BotCore expects (.data["chats"], .chat_key), loaded for one chat at a time from a backend."""

    def __init__(self, salt):
        self.data = {"salt": salt, "chats": {}}

    def chat_key(self, chat_id):
        return hashlib.sha256(f"{self.data['salt']}:{int(chat_id)}".encode()).hexdigest()[:20]


class WebhookBot(core.BotCore):
    """BotCore with rate-limit counters kept in the chat state (survives between invocations).

    B6-03, known and accepted: the counter is a read-modify-write on the chat's state row, so two updates from one chat
    handled at the same instant could both pass at the limit or lose one write. Telegram delivers a chat's updates
    one at a time, and the window is fixed (a burst of up to 2 x 20 straddling a boundary); both are harmless here."""

    def __init__(self, *a, wall=time.time, **k):
        super().__init__(*a, **k)
        self.wall = wall
        self.persist = None             # callable: save this chat's state; set by process()
        self.persisted, self.persist_failed = False, False

    def deliver(self, chat_id, st, out):
        """B6-02: the state is saved BEFORE anything is sent, so a registration is never lost after the user was told
        "Registered", and a failed save sends nothing (process() then releases the claim so Telegram retries)."""
        if self.persist is not None:
            try:
                self.persist()
                self.persisted = True
            except Exception as e:
                log.error("state save failed: %s", type(e).__name__)
                self.persist_failed = True
                return
        super().deliver(chat_id, st, out)

    def rate_ok(self, key):
        st, now = self.chat(key), self.wall()
        rl = st.get("rl") or [now, 0, 0]
        if now - rl[0] > core.RATE_WINDOW:
            rl = [now, 0, 0]
        st["rl"] = rl
        if rl[1] >= core.RATE_MAX:
            return False
        rl[1] += 1
        return True

    def warn_once(self, key):
        rl = self.chat(key)["rl"]
        if rl[2]:
            return False
        rl[2] = 1
        return True


# ------------------------------------------------------------------------------------------ request handling
def secret_ok(given, expected):
    if not expected or not given:
        return False
    return hmac.compare_digest(hashlib.sha256(given.encode()).digest(), hashlib.sha256(expected.encode()).digest())


def private_chat_id(upd):
    msg = upd.get("message") if isinstance(upd, dict) else None
    chat = (msg or {}).get("chat") if isinstance(msg, dict) else None
    if isinstance(chat, dict) and isinstance(chat.get("id"), int) and chat.get("type") == "private":
        return chat["id"]
    return None


def process(body, secret_header, secret, backend, tx, H, salt, photo_base, now=time.time, sleep=time.sleep, demo_wait=0.6):
    """Returns (http_status, text). Valid updates always get 200, even when the bot itself fails."""
    if not secret_ok(secret_header, secret):
        return 401, "unauthorized"
    if len(body) > MAX_BODY:
        return 413, "too large"
    try:
        upd = json.loads(body.decode("utf-8")) if body else {}
    except ValueError:
        return 200, "ignored"                           # not an update we can use; a retry would not help
    uid = upd.get("update_id") if isinstance(upd, dict) else None
    if not isinstance(uid, int):
        return 200, "empty"
    t = int(now())
    store = ChatStore(salt)
    chat_id = private_chat_id(upd)
    key = store.chat_key(chat_id) if chat_id is not None else None
    try:
        is_new, state = backend.begin(uid, key or "-", t)
    except Exception as e:
        log.error("state backend failed: %s", e)
        return 503, "retry"                             # nothing was done yet: let Telegram retry
    if not is_new:
        return 200, "duplicate"
    label = "ignored"
    if key is not None:
        if state:
            try:
                store.data["chats"][key] = json.loads(state)
            except ValueError:
                pass
        bot = WebhookBot(tx, store, H, now=None, sleep=sleep, wall=now)
        bot.demo_wait, bot.photo_base = demo_wait, photo_base

        def save():
            if key in store.data["chats"]:
                backend.save(key, json.dumps(store.data["chats"][key], separators=(",", ":")), t)
        bot.persist = save
        label = bot.handle_update(upd)
        if not bot.persist_failed and not bot.persisted:     # nothing was sent (silent or rate-limited): save now
            try:
                save()
            except Exception as e:
                log.error("state save failed: %s", type(e).__name__)
                bot.persist_failed = True
        if bot.persist_failed:                                # nothing reached the user: let Telegram retry
            try:
                backend.release(uid)
            except Exception:
                pass
            return 503, "retry"
    if random.randrange(PRUNE_ODDS) == 0:
        try:
            backend.prune(t)
        except Exception as e:
            log.warning("prune failed: %s", e)
    log.info("update %s -> %s", uid, label)
    return 200, "ok"


def prune_now(backend, now=time.time):
    """The daily cron (B6-01): delete chats idle for CHAT_TTL_DAYS and update ids older than UPDATE_TTL_DAYS."""
    backend.prune(int(now()))
