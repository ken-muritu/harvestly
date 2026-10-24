"""Offline tests for the webhook handler (fake Telegram transport + in-memory backend). Run: python3 -m unittest -v test_webhook"""
import hashlib, io, json, logging, os, sys, unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
import harvestly_engine as H
import webhook as W

SECRET, SALT, CHAT = "s3cret-value", "salt-xyz", 424242
BASE = "https://harvestly-bot.example"


class FakeTx:
    def __init__(self):
        self.calls = []
    def call(self, method, params=None, timeout=20):
        self.calls.append((method, params))
        return {}
    def texts(self):
        return [p.get("text") or p.get("caption") for m, p in self.calls if m in ("sendMessage", "sendPhoto")]


def upd(i, text, chat=CHAT, ctype="private"):
    return json.dumps({"update_id": i, "message": {"chat": {"id": chat, "type": ctype}, "text": text}}).encode()


class T(unittest.TestCase):
    def setUp(self):
        self.be, self.tx, self.clock = W.MemoryBackend(), FakeTx(), [1_800_000_000.0]
    def post(self, body, secret=SECRET, backend=None):
        return W.process(body, secret, SECRET, backend or self.be, self.tx, H, SALT, BASE,
                         now=lambda: self.clock[0], sleep=lambda s: None, demo_wait=0)

    def test_secret(self):
        for bad in (None, "", "wrong", SECRET + "x"):
            self.assertEqual(self.post(upd(1, "/start"), bad)[0], 401)
        self.assertEqual(self.tx.calls, []); self.assertEqual(self.be.updates, {})      # nothing processed
        self.assertFalse(W.secret_ok("x", ""))                                          # unset secret never matches

    def test_empty_and_junk_200(self):
        for body in (b"", b"{}", b"not json", b"[]", b'{"update_id":"x"}'):
            self.assertEqual(self.post(body)[0], 200)
        self.assertEqual(self.tx.calls, [])
        self.assertEqual(self.post(b"x" * (W.MAX_BODY + 1))[0], 413)

    def test_non_message_and_groups_ignored(self):
        self.assertEqual(self.post(json.dumps({"update_id": 5, "edited_message": {}}).encode())[0], 200)
        self.assertEqual(self.post(upd(6, "hi", ctype="group"))[0], 200)
        self.assertEqual(self.tx.calls, [])

    def test_start_sends_logo_by_url(self):
        self.assertEqual(self.post(upd(1, "/start"))[0], 200)
        photos = [p for m, p in self.tx.calls if m == "sendPhoto"]
        self.assertEqual(photos[0]["photo"], BASE + "/logo.png")
        first = self.tx.texts()[0]
        self.assertIn("Choose a language", first); self.assertIn("Chagua lugha", first)          # the one bilingual message
        kb = [p for m, p in self.tx.calls if m == "sendPhoto"][0]["reply_markup"]["keyboard"]
        self.assertEqual(kb, [[{"text": "English"}, {"text": "Kiswahili"}]])
        self.tx.calls.clear(); self.post(upd(2, "English"))
        self.assertIn("JOIN KITALE SACK 12", self.tx.texts()[0]); self.assertNotIn("SAJILI", self.tx.texts()[0])

    def test_b6_11_start_instruction_replayed_in_english_chat_stays_english(self):
        import re
        self.post(upd(1, "/start")); self.post(upd(4, "English"))
        cmd = re.search(r"<code>(JOIN [A-Z ]+ \d+)</code>", self.tx.texts()[-1]).group(1)        # the bot's own English instruction
        self.tx.calls.clear()
        self.post(upd(2, cmd)); self.post(upd(3, "METER 14.2"))
        out = " ".join(self.tx.texts())
        self.assertIn("Registered", out); self.assertIn("Reading recorded", out)
        for sw in ("Umesajiliwa", "Karibu", "Kipimo", "haijathibitishwa"):
            self.assertNotIn(sw, out)
        (key,) = self.be.chats
        self.assertEqual(json.loads(self.be.chats[key][0])["lang"], "en")

    def test_b6_06_kiswahili_chat_gets_kiswahili_strings(self):
        self.post(upd(1, "Kiswahili"))
        self.assertIn("Jaribio la mfano", self.tx.texts()[0]); self.assertIn("SAJILI KITALE MAGUNIA 12", self.tx.texts()[0])
        self.assertNotIn("JOIN", self.tx.texts()[0]); self.tx.calls.clear()
        self.post(upd(2, "/start")); self.assertIn("Jaribio la mfano", self.tx.texts()[0])
        self.tx.calls.clear()
        self.post(json.dumps({"update_id": 3, "message": {"chat": {"id": CHAT, "type": "private"}, "sticker": {}}}).encode())
        self.assertEqual(len(self.tx.texts()), 1); self.assertTrue(self.tx.texts()[0].endswith(W.core.NON_TEXT["sw"]))

    def test_b6_02_state_is_saved_before_anything_is_sent_and_a_failed_save_sends_nothing(self):
        order = []
        class Spy(W.MemoryBackend):
            def save(s, *a): order.append("save"); super().save(*a)
        class Tx(FakeTx):
            def call(s, method, params=None, timeout=20):
                if method == "sendMessage": order.append("send")
                return super().call(method, params, timeout)
        self.tx = Tx()
        be = Spy()
        self.post(upd(1, "JOIN KITALE SACK 12"), backend=be)
        self.assertLess(order.index("save"), order.index("send"))
        class NoSave(W.MemoryBackend):
            def save(s, *a): raise RuntimeError("x")
        be2 = NoSave(); self.tx.calls.clear()
        self.assertEqual(self.post(upd(9, "JOIN KITALE SACK 12"), backend=be2), (503, "retry"))
        self.assertEqual(self.tx.calls, []); self.assertNotIn(9, be2.updates)                  # nothing sent, claim released
        be2.save = W.MemoryBackend.save.__get__(be2)                                            # store recovers: Telegram's retry works
        self.assertEqual(self.post(upd(9, "JOIN KITALE SACK 12"), backend=be2)[0], 200)
        self.assertIn("Registered", " ".join(self.tx.texts()))

    def test_dedupe(self):
        self.post(upd(7, "/help")); n = len(self.tx.calls)
        self.assertEqual(self.post(upd(7, "/help")), (200, "duplicate"))
        self.assertEqual(len(self.tx.calls), n)

    def test_state_persists_between_invocations(self):
        self.post(upd(1, "SAJILI KITALE SACK 12"))
        self.tx.calls.clear()
        self.post(upd(2, "METER 14.2"))
        out = " ".join(self.tx.texts())
        self.assertNotIn("Harvestly: Which", out); self.assertNotIn("To join", out)      # known chat, not a stranger
        self.post(upd(3, "/lang sw")); self.post(upd(4, "/lang en"))
        self.post(upd(5, "/reset"))
        self.assertIn("deleted", self.tx.texts()[-1])

    def test_warning_sends_dial_card_url(self):
        self.post(upd(1, "SAJILI KITALE SACK 12")); self.tx.calls.clear()
        self.post(upd(2, "/demo"))
        urls = [p["photo"] for m, p in self.tx.calls if m == "sendPhoto"]
        self.assertTrue(urls and all(u.startswith(BASE + "/cards/dial-") and u.endswith(".png") for u in urls))
        for u in urls:
            self.assertTrue(os.path.isfile(os.path.join(HERE, "public", u[len(BASE) + 1:])))   # the file really is deployed

    def test_demo_cards_follow_the_chat_language(self):
        self.post(upd(1, "JOIN KITALE SACK 12")); self.tx.calls.clear(); self.post(upd(2, "/demo"))
        en = [p["photo"] for m, p in self.tx.calls if m == "sendPhoto"]
        self.post(upd(3, "/lang sw")); self.tx.calls.clear(); self.post(upd(4, "/demo"))
        sw = [p["photo"] for m, p in self.tx.calls if m == "sendPhoto"]
        self.assertTrue(en and sw)
        self.assertTrue(all("/cards/dial-" in u and "dial-sw-" not in u for u in en))
        self.assertTrue(all("/cards/dial-sw-" in u for u in sw))
        for u in en + sw:
            self.assertTrue(os.path.isfile(os.path.join(HERE, "public", u[len(BASE) + 1:])))

    def test_photo_failure_falls_back_to_text(self):
        class Bad(FakeTx):
            def call(s, method, params=None, timeout=20):
                if method == "sendPhoto":
                    raise W.core.TelegramError("HTTP 400 bad", 400)
                return super().call(method, params, timeout)
        self.tx = Bad()
        self.post(upd(1, "/start"))
        self.assertIn("Choose a language", self.tx.texts()[0])

    def test_rate_limit_persists_across_invocations(self):
        for i in range(1, 21):
            self.post(upd(i, "/help"))
        self.tx.calls.clear()
        self.post(upd(21, "/help")); self.post(upd(22, "/help"))
        self.assertEqual(self.tx.texts(), [W.core.SLOW_DOWN[None]])                  # warned once, then silent
        self.clock[0] += 61
        self.tx.calls.clear(); self.post(upd(23, "/help"))
        self.assertIn("Choose a language", self.tx.texts()[-1])

    def test_stored_data_is_minimal(self):
        self.post(upd(1, "SAJILI KITALE SACK 12")); self.post(upd(2, "hello private words"))
        blob = json.dumps([self.be.chats, self.be.updates])
        self.assertNotIn(str(CHAT), blob); self.assertNotIn("hello private words", blob); self.assertNotIn("KITALE SACK", blob)
        (key,) = self.be.chats
        self.assertEqual(key, hashlib.sha256(f"{SALT}:{CHAT}".encode()).hexdigest()[:20])
        st = json.loads(self.be.chats[key][0])
        self.assertEqual(set(st) - {"batch", "lang", "banner", "optout", "rl"}, set())
        self.assertEqual(st["batch"]["replies"], [])

    def test_prune(self):
        self.post(upd(1, "/help")); old = self.clock[0]
        self.be.prune(int(old) + 31 * 86400)
        self.assertEqual((self.be.chats, self.be.updates), ({}, {}))

    def test_backend_down_returns_503_before_doing_anything(self):
        class Down(W.MemoryBackend):
            def begin(self, *a): raise RuntimeError("turso down")
        code, _ = self.post(upd(1, "/start"), backend=Down())
        self.assertEqual(code, 503); self.assertEqual(self.tx.calls, [])

    def test_save_failure_is_503_and_nothing_is_sent(self):
        class NoSave(W.MemoryBackend):
            def save(self, *a): raise RuntimeError("x")
        self.assertEqual(self.post(upd(1, "/help"), backend=NoSave())[0], 503); self.assertEqual(self.tx.calls, [])

    def test_logs_carry_no_text_ids_or_token(self):
        buf = io.StringIO(); h = logging.StreamHandler(buf); lg = logging.getLogger("harvestly-bot")
        lg.addHandler(h); lg.setLevel(logging.DEBUG)
        try:
            self.post(upd(1, "very private words")); self.post(upd(2, "/help"))
        finally:
            lg.removeHandler(h)
        out = buf.getvalue()
        self.assertNotIn("very private", out); self.assertNotIn(str(CHAT), out)

    def test_transport_scrubs_token(self):
        tx = W.Transport("123:TOKEN")
        with mock.patch("urllib.request.urlopen", side_effect=OSError("boom 123:TOKEN")):
            with self.assertRaises(W.core.TelegramError) as c:
                tx.call("getMe")
        self.assertNotIn("123:TOKEN", str(c.exception))


class Prune(unittest.TestCase):
    """B6-01: the daily cron endpoint (bot/api/prune.py) is authenticated and deletes idle chats and old update ids."""
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(HERE, "api"))
        import prune
        cls.P = prune

    def test_requires_the_cron_secret(self):
        be = W.MemoryBackend(); be.chats["k"] = ("{}", 0); be.updates[1] = 0
        for hdr in (None, "", "Bearer", "Bearer wrong", "wrong-secret", "Basic cron-secret"):
            self.assertEqual(self.P.run(hdr, {"CRON_SECRET": "cron-secret"}, be)[0], 401)
        self.assertEqual(self.P.run("Bearer cron-secret", {}, be)[0], 401)                  # unset secret fails closed
        self.assertEqual((len(be.chats), len(be.updates)), (1, 1))

    def test_deletes_idle_chats_and_old_updates_only(self):
        import time
        be, now = W.MemoryBackend(), time.time()
        be.chats["old"] = ("{}", now - 31 * 86400); be.chats["fresh"] = ("{}", now - 29 * 86400)
        be.updates[1] = now - 3 * 86400; be.updates[2] = now - 3600
        self.assertEqual(self.P.run("Bearer cron-secret", {"CRON_SECRET": "cron-secret"}, be), (200, "ok"))
        self.assertEqual((set(be.chats), set(be.updates)), ({"fresh"}, {2}))

    def test_cron_is_declared_daily(self):
        v = json.load(open(os.path.join(HERE, "vercel.json")))
        self.assertEqual(v["crons"], [{"path": "/api/prune", "schedule": v["crons"][0]["schedule"]}])
        self.assertRegex(v["crons"][0]["schedule"], r"^\d+ \d+ \* \* \*$")                      # once a day (Hobby limit)


class Handler(unittest.TestCase):
    """The HTTP shell: auth before configuration (N6-08), no stack trace on a bug (B6-04), 405 on GET."""
    def call(self, method, headers=None, body=b"", env=None):
        import threading, http.client
        from http.server import HTTPServer
        sys.path.insert(0, os.path.join(HERE, "api"))
        import telegram as A
        srv = HTTPServer(("127.0.0.1", 0), A.handler)
        t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
        try:
            with mock.patch.dict(os.environ, env or {}, clear=True):
                c = http.client.HTTPConnection("127.0.0.1", srv.server_port)
                c.request(method, "/api/telegram", body, headers or {})
                r = c.getresponse(); return r.status, r.read().decode()
        finally:
            srv.shutdown(); srv.server_close()

    FULL = {"TELEGRAM_WEBHOOK_SECRET": "ws", "TELEGRAM_BOT_TOKEN": "1:t", "TURSO_URL": "https://x", "TURSO_TOKEN": "t", "STATE_SALT": "s"}

    def test_unauthenticated_is_401_even_when_unconfigured(self):
        self.assertEqual(self.call("POST", {}, b"{}", {})[0], 401)
        self.assertEqual(self.call("POST", {"X-Telegram-Bot-Api-Secret-Token": "nope"}, b"{}", self.FULL)[0], 401)
        self.assertEqual(self.call("GET", env=self.FULL)[0], 405)

    def test_authenticated_but_unconfigured_is_503(self):
        self.assertEqual(self.call("POST", {"X-Telegram-Bot-Api-Secret-Token": "ws"}, b"{}", {"TELEGRAM_WEBHOOK_SECRET": "ws"})[0], 503)

    def test_a_bug_returns_200_without_a_stack_trace(self):
        with mock.patch("webhook.process", side_effect=ValueError("secret text 999")), self.assertLogs("harvestly-bot", "ERROR") as lg:
            code, text = self.call("POST", {"X-Telegram-Bot-Api-Secret-Token": "ws", "Content-Length": "2"}, b"{}", self.FULL)
        self.assertEqual((code, text), (200, "error"))
        self.assertNotIn("secret text", "\n".join(lg.output)); self.assertIn("ValueError", "\n".join(lg.output))


class TursoShape(unittest.TestCase):
    def test_pipeline_requests(self):
        seen = []
        def fake(req, timeout=0):
            seen.append((req.full_url, req.headers["Authorization"], json.loads(req.data)))
            n = len(json.loads(req.data)["requests"]) - 1
            res = [{"type": "ok", "response": {"type": "execute", "result": {"affected_row_count": 1, "rows": [[{"type": "text", "value": "{\"lang\":\"sw\"}"}]]}}}] * n
            class R(io.BytesIO):
                def __enter__(s): return s
                def __exit__(s, *a): pass
            return R(json.dumps({"results": res + [{"type": "ok", "response": {"type": "close"}}]}).encode())
        be = W.TursoBackend("libsql://db-x.turso.io", "TOK")
        with mock.patch("urllib.request.urlopen", fake):
            self.assertEqual(be.begin(5, "k", 100), (True, '{"lang":"sw"}'))
            be.save("k", "{}", 100); be.prune(100); be.release(5)
        self.assertEqual(seen[0][0], "https://db-x.turso.io/v2/pipeline"); self.assertEqual(seen[0][1], "Bearer TOK")
        self.assertEqual(seen[0][2]["requests"][0]["stmt"]["args"][0], {"type": "integer", "value": "5"})
        self.assertEqual(seen[0][2]["requests"][-1], {"type": "close"})

    def test_duplicate_claim(self):
        res = {"results": [{"type": "ok", "response": {"type": "execute", "result": {"affected_row_count": 0, "rows": []}}}] * 2
               + [{"type": "ok", "response": {"type": "close"}}]}
        class R(io.BytesIO):
            def __enter__(s): return s
            def __exit__(s, *a): pass
        with mock.patch("urllib.request.urlopen", lambda r, timeout=0: R(json.dumps(res).encode())):
            self.assertEqual(W.TursoBackend("https://x", "t").begin(1, "k", 1), (False, None))


class Sync(unittest.TestCase):
    def test_copies_are_byte_identical(self):
        for src, dst in (("../engine/harvestly_engine.py", "lib/harvestly_engine.py"), ("../engine/vectors.json", "lib/vectors.json"),
                         ("../tools/harvestly_bot_core.py", "lib/harvestly_bot_core.py"),
                         ("../brand/telegram-profile-512.png", "public/logo.png")):
            self.assertEqual(open(os.path.join(HERE, src), "rb").read(), open(os.path.join(HERE, dst), "rb").read(), dst + " stale: run ./sync-engine.sh")
        self.assertEqual(open(os.path.join(HERE, "../engine/demo_sw.json"), "rb").read(), open(os.path.join(HERE, "lib/demo_sw.json"), "rb").read())
        for n in range(0, 91):
            for pre in ("dial-", "dial-sw-"):
                a, b = os.path.join(HERE, "../brand/telegram-cards/%s%d.png" % (pre, n)), os.path.join(HERE, "public/cards/%s%d.png" % (pre, n))
                self.assertEqual(open(a, "rb").read(), open(b, "rb").read())

    def test_site_has_no_forbidden_words(self):
        html = open(os.path.join(HERE, "public/index.html")).read()
        self.assertNotIn("dae" + "lus", html.lower()); self.assertIn("noindex", html)
        self.assertIn("t.me/HarvestlyBot", html)


if __name__ == "__main__":
    unittest.main()
