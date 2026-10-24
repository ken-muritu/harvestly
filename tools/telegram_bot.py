#!/usr/bin/env python3
"""Harvestly Telegram bridge: a HACKATHON PROTOTYPE TEST of the Python reference engine.

Long-polls the Telegram Bot API (stdlib only) and routes each private text message to
harvestly_engine.respond(). It mirrors how plsql/ords_handlers.sql routes Telegram (registration words
JOIN/REGISTER/SAJILI, STOP/START per chat, how-to for strangers) but runs on a laptop, with a fixed
SIMULATED forecast. It is not a live alert service: no proactive alerts, no real weather.

Run:      python3 telegram_bot.py                 (token from env TELEGRAM_BOT_TOKEN or ~/.config/harvestly/secrets.env)
Profile:  python3 telegram_bot.py --setup-profile (setMyName / descriptions / commands, once)
Check:    python3 telegram_bot.py --check         (getMe only)

The token is never printed or logged; every logged string is scrubbed of it. Logs carry no message text and no
names: only update ids, a short hash prefix of the chat and the command class.
"""
import argparse
import collections
import dataclasses
import hashlib
import html as htmllib
import importlib.util
import json
import logging
import os
import random
import re
import secrets
import signal
import sys
import time
import mimetypes
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harvestly_bot_core import *      # noqa: F401,F403  shared routing/formatting (also used by the Vercel webhook)
from harvestly_bot_core import TelegramError, find_asset, esc, plain, fmt_engine, batch_to_json, batch_from_json, BotCore

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.environ.get("HARVESTLY_BOT_STATE") or os.path.expanduser("~/.local/share/harvestly-bot/state.json")
SECRETS_PATH = os.path.expanduser("~/.config/harvestly/secrets.env")
EAT = timezone(timedelta(hours=3))
POLL_TIMEOUT = 30
RATE_MAX, RATE_WINDOW = 20, 60.0           # messages per chat per minute
MAX_INBOUND = 1000                          # same cut as the engine / ORDS handler (R1-07)
KEEP_SENT = 40                              # trim batch history kept on disk
log = logging.getLogger("harvestly-bot")


# ---------------------------------------------------------------------------------------------- engine loading
def load_engine(engine_dir=None):
    cands = [engine_dir, os.environ.get("HARVESTLY_ENGINE_DIR"), os.path.join(HERE, "engine"),
             os.path.join(HERE, "..", "engine"), os.path.expanduser("~/harvestly/engine")]
    for d in cands:
        if d and os.path.exists(os.path.join(d, "harvestly_engine.py")):
            spec = importlib.util.spec_from_file_location("harvestly_engine", os.path.join(d, "harvestly_engine.py"))
            mod = importlib.util.module_from_spec(spec)
            sys.modules["harvestly_engine"] = mod
            spec.loader.exec_module(mod)
            return mod, os.path.abspath(d)
    raise SystemExit("harvestly_engine.py not found (set HARVESTLY_ENGINE_DIR)")


# ---------------------------------------------------------------------------------------------- token + transport
def read_token():
    tok = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not tok and os.path.exists(SECRETS_PATH):
        with open(SECRETS_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    tok = line.split("=", 1)[1].strip().strip("'\"")
    if not tok:
        raise SystemExit("TELEGRAM_BOT_TOKEN not set")
    return tok





class Transport:
    """Real Bot API transport. Anything raised or logged is scrubbed of the token."""

    def __init__(self, token):
        self._token = token

    def _scrub(self, s):
        return str(s).replace(self._token, "<token>")

    def upload(self, method, params, field, path, timeout=40):
        """multipart/form-data call with one local file (sendPhoto)."""
        boundary = secrets.token_hex(12)
        parts = []
        for k, v in params.items():
            v = v if isinstance(v, str) else json.dumps(v)
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        with open(path, "rb") as f:
            blob = f.read()
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{os.path.basename(path)}"\r\n'
                      f'Content-Type: {ctype}\r\n\r\n').encode() + blob + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        return self.call(method, None, timeout, raw=(b"".join(parts), f"multipart/form-data; boundary={boundary}"))

    def call(self, method, params=None, timeout=40, raw=None):
        url = f"https://api.telegram.org/bot{self._token}/{method}"
        data, ctype = raw if raw else (json.dumps(params or {}).encode(), "application/json")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": ctype})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read().decode("utf-8", "replace"))
            except Exception:
                body = {}
            raise TelegramError(f"HTTP {e.code} {self._scrub(body.get('description', ''))[:120]}", e.code,
                                (body.get("parameters") or {}).get("retry_after")) from None
        except Stop:
            raise
        except Exception as e:      # URLError, timeout, ssl, bad json
            raise TelegramError(f"{type(e).__name__}: {self._scrub(e)[:120]}") from None
        if not body.get("ok"):
            raise TelegramError(self._scrub(body.get("description", "not ok"))[:120], body.get("error_code"),
                                (body.get("parameters") or {}).get("retry_after"))
        return body.get("result")


# ---------------------------------------------------------------------------------------------- state file
class Store:
    """state.json: {"salt", "offset", "chats": {hash: {...}}}. Mode 600, atomic writes. No names, no usernames,
    no message text. The chat id itself is stored only as a salted hash (replies go to the chat that wrote)."""

    def __init__(self, path):
        self.path = path
        self.data = {"salt": secrets.token_hex(16), "offset": 0, "chats": {}}
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict) and isinstance(d.get("chats"), dict) and d.get("salt"):
                self.data = d
                self.data.setdefault("offset", 0)
        except (OSError, ValueError):
            pass

    def chat_key(self, chat_id):
        return hashlib.sha256(f"{self.data['salt']}:{int(chat_id)}".encode()).hexdigest()[:20]

    def save(self):
        d = os.path.dirname(self.path)
        os.makedirs(d, mode=0o700, exist_ok=True)
        tmp = self.path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(self.data, f, separators=(",", ":"))
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)

    @property
    def offset(self):
        return int(self.data.get("offset") or 0)

    def set_offset(self, n):
        self.data["offset"] = int(n)


class Bot(BotCore):
    """Local long-polling front end of the shared core."""

    # ---- polling loop
    def poll_once(self):
        params = {"timeout": POLL_TIMEOUT, "allowed_updates": ["message"]}
        if self.store.offset:
            params["offset"] = self.store.offset
        self.in_poll = True
        try:
            updates = self.tx.call("getUpdates", params, timeout=POLL_TIMEOUT + 10)
        finally:
            self.in_poll = False
        for upd in updates or []:
            uid = upd.get("update_id") if isinstance(upd, dict) else None
            label = self.handle_update(upd)
            log.info("update %s -> %s", uid, label)
            if isinstance(uid, int):
                self.store.set_offset(uid + 1)
            try:
                self.store.save()
            except OSError as e:
                log.error("state save failed: %s", type(e).__name__)
        return len(updates or [])

    def run(self):
        delay = 1.0
        log.info("polling started (engine %s)", self.H.__name__)
        while not self.stop:
            try:
                self.poll_once()
                delay = 1.0
            except Stop:
                break
            except TelegramError as e:
                wait = e.retry_after or delay
                log.warning("poll error: %s (retry in %.0fs)", e, wait)
                self.interruptible_sleep(wait + random.random())
                delay = min(delay * 2, 60.0)
            except Exception as e:
                log.error("unexpected poll error: %s", type(e).__name__)
                self.interruptible_sleep(delay + random.random())
                delay = min(delay * 2, 60.0)
        try:
            self.store.save()
        except OSError:
            pass
        log.info("stopped cleanly")

    def interruptible_sleep(self, secs):
        left = secs
        while not self.stop and left > 0:
            step = min(0.5, left)
            self.sleep(step)
            left -= step

    def request_stop(self, *_):
        self.stop = True
        if self.in_poll:
            raise Stop()


class Stop(Exception):
    pass


# ---------------------------------------------------------------------------------------------- profile
# Profile text is shown before any language choice, so each variant is ONE language: the default (English) and
# language_code "sw" (shown to people whose Telegram is set to Swahili). Never mixed inside one text.
PROFILE = {
    "en": {
        "name": "Harvestly",
        "short": "Hackathon prototype: maize-storage advice test. Simulated weather, no real alerts yet. Free.",
        "description": ("Harvestly is a HACKATHON PROTOTYPE TEST of a maize-storage advice engine.\n"
                        "Advice here uses simulated weather; no real alerts are sent yet; it is free to try and "
                        "promises nothing.\n"
                        "Send /start to begin, or send JOIN KITALE SACK 12."),
        "commands": [{"command": "start", "description": "Welcome and how to register"},
                     {"command": "demo", "description": "Watch the pitch-demo week (simulated)"},
                     {"command": "weather", "description": "Recent weather near my ward (NASA estimate)"},
                     {"command": "forecast", "description": "Forecast for the next days near my ward"},
                     {"command": "help", "description": "What I understand"},
                     {"command": "lang", "description": "Change language"},
                     {"command": "stop", "description": "Stop all messages"},
                     {"command": "reset", "description": "Delete my test data"}],
    },
    "sw": {
        "name": "Harvestly",
        "short": "Jaribio la mfano: ushauri wa kuhifadhi mahindi. Hali ya hewa ya kuigwa, hakuna tahadhari halisi bado. Bure.",
        "description": ("Harvestly ni JARIBIO LA MFANO la mfumo wa ushauri wa kuhifadhi mahindi.\n"
                        "Ushauri hapa unatumia hali ya hewa ya kuigwa; hakuna tahadhari halisi zinazotumwa bado; ni bure "
                        "kujaribu na haiahidi chochote.\n"
                        "Tuma /start kuanza, au tuma SAJILI KITALE MAGUNIA 12."),
        "commands": [{"command": "start", "description": "Karibu na jinsi ya kusajili"},
                     {"command": "demo", "description": "Tazama wiki ya mfano (ya kuigwa)"},
                     {"command": "weather", "description": "Hali ya hewa ya karibuni (makadirio ya NASA)"},
                     {"command": "forecast", "description": "Utabiri wa siku zijazo karibu na kata yangu"},
                     {"command": "help", "description": "Ninachoelewa"},
                     {"command": "lang", "description": "Badilisha lugha"},
                     {"command": "stop", "description": "Simamisha ujumbe wote"},
                     {"command": "reset", "description": "Futa data yangu ya majaribio"}],
    },
}


def setup_profile(tx):
    for code, P in (("", PROFILE["en"]), ("sw", PROFILE["sw"])):
        extra = {"language_code": code} if code else {}
        try:        # Telegram rate-limits name changes (429 for about a day), so only set the name when it differs
            cur = (tx.call("getMyName", dict(extra)) or {}).get("name")
        except Exception:
            cur = None
        if cur != P["name"]:
            tx.call("setMyName", dict({"name": P["name"]}, **extra))
        tx.call("setMyDescription", dict({"description": P["description"]}, **extra))
        tx.call("setMyShortDescription", dict({"short_description": P["short"]}, **extra))
        tx.call("setMyCommands", dict({"commands": P["commands"]}, **extra))
    return "profile set"


# ---------------------------------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--setup-profile", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--drain", action="store_true", help="skip updates already waiting (no replies sent), then exit")
    ap.add_argument("--engine-dir")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stderr)
    token = read_token()
    tx = Transport(token)
    if a.check:
        me = tx.call("getMe", timeout=20)
        print("getMe ok: @%s" % me.get("username"))
        return 0
    if a.setup_profile:
        print(setup_profile(tx))
        return 0
    if a.drain:
        store = Store(STATE_PATH)
        ups = tx.call("getUpdates", {"timeout": 0, "offset": -1, "allowed_updates": ["message"]}, timeout=20)
        ids = [u["update_id"] for u in ups or [] if isinstance(u.get("update_id"), int)]
        if ids:
            store.set_offset(max(ids) + 1)
            store.save()
        print("drained; next offset", store.offset)
        return 0
    H, edir = load_engine(a.engine_dir)
    store = Store(STATE_PATH)
    store.save()
    bot = Bot(tx, store, H, edir)
    signal.signal(signal.SIGTERM, bot.request_stop)
    signal.signal(signal.SIGINT, bot.request_stop)
    me = tx.call("getMe", timeout=20)
    log.info("getMe ok: @%s; state %s; engine dir %s", me.get("username"), STATE_PATH, edir)
    bot.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
