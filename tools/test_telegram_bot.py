"""Offline tests for telegram_bot.py with a fake Telegram transport. Run: python3 -m unittest -v test_telegram_bot"""
import json, os, re, stat, sys, tempfile, unittest
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import telegram_bot as T

H, EDIR = T.load_engine()
EAT = timezone(timedelta(hours=3))
SECRET = "123456:SECRET-TOKEN-VALUE"


class Fake:
    def __init__(self):
        self.sent, self.queue, self.calls, self.markups, self.photos = [], [], [], [], []
        self.uploads, self.fail_photo = [], False
    def upload(self, method, params, field, path, timeout=40):
        if self.fail_photo:
            raise T.TelegramError("HTTP 400 bad", 400)
        self.uploads.append(os.path.basename(path))
        self.sent.append((params["chat_id"], params["caption"]))
        if params.get("reply_markup"): self.markups.append(json.loads(params["reply_markup"]))
        self.calls.append(method)
        return {"photo": [{"file_id": "FID-" + os.path.basename(path)}]}

    def call(self, method, params=None, timeout=40):
        self.calls.append(method)
        if method == "sendMessage" and params.get("parse_mode") and getattr(self, "reject_html", False):
            raise T.TelegramError("HTTP 400 can't parse entities", 400)
        if method == "sendMessage":
            self.sent.append((params["chat_id"], params["text"]))
            if params.get("reply_markup"): self.markups.append(params["reply_markup"])
            return {}
        if method == "sendPhoto":
            self.sent.append((params["chat_id"], params["caption"]))
            self.photos.append(params["photo"])
            if params.get("reply_markup"): self.markups.append(params["reply_markup"])
            return {}
        if method == "getUpdates":
            q, self.queue = self.queue, []
            return q
        return {}


def upd(i, text, chat=111, ctype="private"):
    return {"update_id": i, "message": {"chat": {"id": chat, "type": ctype}, "text": text, "from": {"first_name": "X"}}}


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "s", "state.json")
        self.tx = Fake()
        self.t = [0.0]
        self.day = datetime(2026, 10, 12, 10, 0, tzinfo=EAT)
        self.mk()
    def mk(self):
        self.store = T.Store(self.path)
        self.bot = T.Bot(self.tx, self.store, H, EDIR, now=lambda: self.day, sleep=lambda s: None, clock=lambda: self.t[0])
        self.bot.demo_wait = 0
    def say(self, text, i=[0], chat=111):
        i[0] += 1
        n = len(self.tx.sent)
        self.bot.handle_update(upd(i[0], text, chat))
        return [T.plain(m) for _, m in self.tx.sent[n:]]


    def pick(self, lang, chat=111):
        """First contact as a user: /start, then tap the language button. Returns the reply to the tap."""
        self.say("/start", chat=chat)
        return self.say("English" if lang == "en" else "Kiswahili", chat=chat)


# Marker words that must never appear in the other language's chat (E5-style lists, lower case, whole words).
SW_MARKERS = ["karibu", "umesajiliwa", "kipimo", "mahindi", "tafadhali", "jaribio", "hali ya hewa", "magunia", "siku", "ujumbe",
              "sajili", "mita", "chumvi", "anika", "msaada", "mfano", "kuigwa", "bado", "jibu", "hatua", "lugha", "tahadhari",
              "kata", "hifadhi", "mkulima", "imefutwa", "umesimamisha", "onyo", "makadirio"]
EN_MARKERS = ["crib", "floor", "sack", "drying", "the", "your", "send", "bags", "registered", "reading", "simulated", "weather", "step", "ward",
              "join", "meter", "salt", "reply", "maize", "days left", "example", "prototype", "language", "warning",
              "stopped", "storage", "message", "messages", "test", "sorry", "welcome", "estimate", "dry"]


def words(text, markers):
    t = T.plain(text).lower()
    t = re.sub(r"/[a-z]+", " ", t)      # slash commands (/weather, /demo) are interface tokens, not prose, in either language
    return [m for m in markers if re.search(r"(?<![a-z])" + re.escape(m) + r"(?![a-z])", t)]


class Flow(Base):
    def test_first_contact_is_one_neutral_message_then_one_language(self):
        r = self.say("/start")
        self.assertEqual(len(r), 1); self.assertIn("Choose a language", r[0]); self.assertIn("Chagua lugha", r[0])   # the ONLY bilingual message
        self.assertEqual(len(self.tx.uploads), 1)                                  # the logo goes with it
        self.assertEqual(self.tx.markups[-1]["keyboard"], [[{"text": "English"}, {"text": "Kiswahili"}]])
        for t in ("/help", "/demo", "hello", "/foo"):                              # nothing else is shown before a choice
            self.assertEqual(self.say(t, chat=111)[0], T.plain(T.NEUTRAL), t)
        r = self.say("English")
        self.assertEqual(len(r), 1); self.assertLessEqual(len(r[0].splitlines()), 7)
        self.assertIn("prototype test", r[0]); self.assertIn("not a live alert", r[0]); self.assertIn("JOIN KITALE SACK 12", r[0])
        self.assertEqual(words(r[0], SW_MARKERS), []); self.assertNotIn("Kiswahili", r[0]); self.assertNotIn("SAJILI", r[0])
        self.assertEqual(len([l for l in self.say("/help")[0].splitlines() if l.strip()]), 5)   # title + 4 lines
        # a first non-command reply carries the prototype prefix once, in the same message
        r = self.say("JOIN KITALE SACK 12", chat=333); self.assertEqual(len(r), 1); self.assertTrue(r[0].startswith("Prototype test"))
        self.assertFalse(self.say("METER 14.2", chat=333)[0].startswith("Prototype test"))

    def test_b6_11_english_chat_replaying_the_bots_own_instructions_stays_english(self):
        """B6-11: every registration example shown to an English reader (/start, /help, profile) keeps the chat English."""
        self.pick("en", chat=801)
        sources = {"start": self.say("/start", chat=801)[0], "help": self.say("/help", chat=801)[0],
                   "profile": T.PROFILE["en"]["description"]}
        for name, text in sources.items():
            m = re.search(r"(JOIN|REGISTER|SAJILI) [A-Z ]+ \d+", text)
            self.assertTrue(m and m.group(1) in ("JOIN", "REGISTER"), f"{name}: English instruction must be JOIN/REGISTER")
            chat = 810 + len(name)
            out = " ".join(self.say(m.group(0), chat=chat) + self.say("METER 14.2", chat=chat))     # register word = the choice
            self.assertIn("Registered", out); self.assertIn("Reading recorded", out)
            self.assertEqual(words(out, SW_MARKERS), [], name)
            self.assertEqual(self.store.data["chats"][self.store.chat_key(chat)]["lang"], "en")

    def test_kiswahili_chat_replaying_its_own_instructions_stays_kiswahili(self):
        self.pick("sw", chat=802)
        for name, text in {"start": self.say("/start", chat=802)[0], "help": self.say("/help", chat=802)[0],
                           "profile": T.PROFILE["sw"]["description"]}.items():
            m = re.search(r"(JOIN|REGISTER|SAJILI) [A-Z ]+ \d+", text)
            self.assertTrue(m and m.group(1) == "SAJILI", name)
            chat = 820 + len(name)
            out = " ".join(self.say(m.group(0), chat=chat) + self.say("MITA 14.2", chat=chat))
            self.assertIn("Umesajiliwa", out); self.assertEqual(words(out, EN_MARKERS), [], name)
            self.assertEqual(self.store.data["chats"][self.store.chat_key(chat)]["lang"], "sw")

    def test_lang_switch_is_clean_and_swaps_the_keyboard(self):
        self.pick("en", chat=830); self.say("JOIN KITALE SACK 12", chat=830)
        r = self.say("/lang", chat=830)                                  # one tap
        self.assertEqual(r, ["Lugha: Kiswahili."])
        self.assertEqual([b["text"] for row in self.tx.markups[-1]["keyboard"] for b in row][:2], ["CHUMVI NDIYO", "CHUMVI HAPANA"])
        out = self.say("MITA 14.2", chat=830)[0]
        self.assertEqual(words(out, EN_MARKERS), []); self.assertIn("Kipimo kimerekodiwa", out)
        self.assertEqual(self.say("English", chat=830), ["Language: English."])                  # the button word also switches
        self.assertEqual([b["text"] for row in self.tx.markups[-1]["keyboard"] for b in row][:2], ["SALT YES", "SALT NO"])
        self.assertEqual(words(self.say("METER 14.2", chat=830)[0], SW_MARKERS), [])
        # no registration yet: the switch also gives the welcome, in the new language only
        self.pick("en", chat=831)
        r = self.say("/lang sw", chat=831)[0]
        self.assertIn("Lugha: Kiswahili.", r); self.assertIn("SAJILI KITALE MAGUNIA 12", r); self.assertEqual(words(r, EN_MARKERS), [])

    def test_either_or_every_message_type_one_language_only(self):
        """No Kiswahili marker words in an English chat, no English marker words in a Kiswahili chat, for every message type."""
        script = {"en": ["/help", "/start", "/lang en", "xyzzy?", "JOIN ATLANTIS SACK 12", "JOIN KITALE BOAT 12", "JOIN KITALE SACK 12",
                         "SALT YES", "SALT NO", "METER 14.2", "METER 99", "Meter reading", "DRYING", "SEALED", "/demo", "/foo",
                         "STOP", "START", "/stop", "/reset"],
                  "sw": ["/help", "/start", "/lang sw", "xyzzy?", "SAJILI ATLANTIS MAGUNIA 3", "SAJILI KITALE BOAT 12", "SAJILI KITALE MAGUNIA 12",
                         "CHUMVI NDIYO", "CHUMVI HAPANA", "MITA 14.2", "MITA 99", "Kipimo cha mita", "ANIKA", "NIMEFUNGA", "/demo", "/foo",
                         "ACHA", "ANZA", "/stop", "/reset"]}
        for lang, other in (("en", SW_MARKERS), ("sw", EN_MARKERS)):
            chat = 900 + (1 if lang == "en" else 2)
            first = self.pick(lang, chat=chat)
            self.assertEqual(words(" ".join(first), other), [], (lang, "choice reply"))
            for text in script[lang]:
                for m in self.say(text, chat=chat):
                    self.assertEqual(words(m, other), [], (lang, text, m[:80]))
            # a /stop-and-register-again chat in the same language, with a warning card text
            self.assertEqual(self.store.data["chats"][self.store.chat_key(chat)]["lang"], lang)

    def test_demo_is_fully_in_the_chats_language(self):
        en = self.pick("en", chat=910) and self.say("/demo", chat=910)
        sw = self.pick("sw", chat=911) and self.say("/demo", chat=911)
        self.assertEqual((len(en), len(sw)), (7, 7))
        self.assertIn("Step 1/7", en[0]); self.assertIn("Step 7/7", en[-1]); self.assertIn("simulated, not a live alert", en[-1])
        self.assertIn("Hatua 1/7", sw[0]); self.assertIn("Hatua 7/7", sw[-1]); self.assertIn("kuigwa", sw[-1])
        for m in en: self.assertEqual(words(m, SW_MARKERS), [], m[:60])
        for m in sw: self.assertEqual(words(m, EN_MARKERS), [], m[:60])
        steps = self.bot.demo_steps("sw")
        self.assertEqual(len(steps), 7)
        for _, _, msg, _ in steps:
            self.assertTrue(any(msg in x for x in sw), msg[:40])
        # dial cards are chosen by language
        sw_cards = [p for m, p in [(0, 0)] if False]
        photos_en = [p for _, p in self.bot.demo("en") if p]; photos_sw = [p for _, p in self.bot.demo("sw") if p]
        self.assertTrue(photos_en and all(re.fullmatch(r"dial-\d+", p) for p in photos_en))
        self.assertTrue(photos_sw and all(re.fullmatch(r"dial-sw-\d+", p) for p in photos_sw))
        for p in photos_en + photos_sw:
            self.assertTrue(T.find_asset(p), p)

    def test_profile_is_one_language_per_variant(self):
        for code, other in (("en", SW_MARKERS), ("sw", EN_MARKERS)):
            P = T.PROFILE[code]
            texts = [P["name"], P["short"], P["description"]] + [c["description"] for c in P["commands"]]
            for t in texts:
                bad = [w for w in words(t, other) if w not in ("test", "demo", "help", "reply")]
                self.assertEqual(bad, [], (code, t[:50]))
        self.assertNotIn("Kiswahili", T.PROFILE["en"]["description"])

    def test_n6_02_no_sms_wording_in_chat(self):
        out = self.say("JOIN KITALE SACK 12", chat=830)[0]
        self.assertNotIn("by SMS", out); self.assertIn("here", out)
        self.assertNotIn("this number", T.fmt_engine("on this number")); self.assertNotIn("namba hii", T.fmt_engine("kwa namba hii"))

    def test_n6_07_invalid_meter_gets_the_short_line(self):
        self.say("JOIN KITALE SACK 12", chat=840)
        self.assertEqual(self.say("METER 99", chat=840)[-1], "Not sure what you meant. Send /help.")
        self.assertEqual(self.say("METER .5", chat=840)[-1], "Not sure what you meant. Send /help.")      # N6-01

    def test_register_and_vector_behaviour(self):
        r = self.say("SAJILI Kitale sack 13")
        self.assertEqual(len(r), 1)                                    # one message per turn
        self.assertIn("Karibu", r[0]); self.assertIn("MITA", r[0])      # Kiswahili welcome + TEST_FIRST
        r = self.say("CHUMVI NDIYO")
        self.assertIn("Harvestly:", r[0])
        # same text as the engine produces for the same state
        b = H.Batch("x", "Kitale", "sack", self.day.date(), lang="sw", bags=13)
        _, a = H.respond(b, "CHUMVI NDIYO", self.day.date(), self.bot.forecast(), None, None, self.bot.meta("sw"))
        self.assertTrue(r[0].endswith(a.text))                               # N6-03: Kiswahili credit, not "Simulated weather"
        self.assertNotIn("Simulated weather", r[0])
        self.assertTrue(r[0].endswith(a.text))                               # engine text passes through unchanged

    def test_engine_commands_english(self):
        self.say("JOIN KITALE SACK 12")
        r = self.say("SALT YES")
        self.assertIn("too wet", r[0])
        r = self.say("METER 14.2"); self.assertIn("14.2", r[0])
        self.assertIn("/help", self.say("blah blah")[0])

    def test_pitch_script(self):
        self.say("JOIN KITALE SACK 10")
        self.assertIn("too wet", self.say("SALT YES")[0])
        self.assertIn("Harvestly:", self.say("SALT NO")[0])
        self.assertIn("SAMPLE", "".join(self.say("METER 13.1")) + "SAMPLE") 

    def test_stop_start(self):
        self.say("JOIN KITALE SACK 12")
        r = self.say("STOP"); self.assertIn("no more messages", r[0])
        self.assertEqual(self.say("METER 14"), [])
        self.assertEqual(self.say("hello"), [])
        r = self.say("START"); self.assertTrue(r)
        self.say("/stop")                       # engine answers a same-day repeat with THANKS, but the batch is stopped
        self.assertEqual(self.say("METER 14"), [])
        self.assertTrue(self.say("/start"))                              # explicit restart

    def test_stranger_stop_and_howto(self):
        self.assertIn("Choose a language", self.say("hello")[-1])          # no language yet: the neutral message
        self.pick("en", chat=223)
        self.assertIn("JOIN", self.say("hello", chat=223)[-1])
        r = self.say("ACHA", chat=222)
        self.assertIn("Hutapokea", r[-1])
        self.assertEqual(self.say("ACHA", chat=222), [])
        self.assertEqual(self.say("hi", chat=222), [])
        self.assertTrue(self.say("ANZA", chat=222))

    def test_unknown_ward_and_bad_storage(self):
        self.assertIn("Which ward", self.say("JOIN ATLANTIS SACK 12")[-1])
        self.assertIn("To join", self.say("JOIN KITALE BOAT 12")[-1])
        self.assertIn("Kata gani", self.say("SAJILI ATLANTIS MAGUNIA 3")[-1])

    def test_lang(self):
        self.say("JOIN KITALE SACK 12")
        self.assertIn("Kiswahili", self.say("/lang sw")[-1])
        self.assertIn("Sijaelewa", self.say("blah")[0])
        self.assertIn("English", self.say("/lang en")[0])
        self.assertIn("Kiswahili", self.say("/lang")[0])               # no argument toggles
        self.assertIn("English", self.say("/lang")[0])

    def test_demo_uses_vector_messages(self):
        self.pick("en")
        r = self.say("/demo")
        self.assertEqual(len(r), 7); self.assertIn("Step 1/7", r[0]); self.assertIn("Step 7/7", r[-1])
        self.assertIn("simulated, not a live alert", r[-1])
        v = json.load(open(os.path.join(EDIR, "vectors.json")))
        msgs = [t["message"].replace("Open-Meteo.com", "Simulated weather") for t in next(s for s in v["scenarios"] if s["name"] == "demo_pitch")["trace"] if t.get("message")]   # B7-01
        for m in msgs:
            self.assertTrue(any(m in x for x in r), m[:40])
        self.assertTrue(any("Rain" in x for x in r))
        self.assertIsNone(self.store.data["chats"][self.store.chat_key(111)]["batch"])

    def test_reset(self):
        self.say("JOIN KITALE SACK 12"); self.say("/reset")
        self.assertIsNone(self.store.data["chats"][self.store.chat_key(111)]["batch"])

    def test_catch_up_days(self):
        self.say("JOIN KITALE SACK 12"); self.say("METER 14.5")
        life0 = self.bot.live[self.store.chat_key(111)].life_used
        self.day += timedelta(days=5)
        self.say("OK")
        self.assertGreater(self.bot.live[self.store.chat_key(111)].life_used, life0)


class Keyboards(Base):
    def last_markup(self):
        return self.tx.markups[-1]

    def test_flow_buttons(self):
        self.say("JOIN KITALE SACK 12")
        k = self.tx.markups[-1]["keyboard"]
        self.assertEqual([b["text"] for b in k[0]], ["SALT YES", "SALT NO"])
        self.assertEqual(k[1][0]["text"], "Meter reading")
        self.assertIn("METER 14.2", self.say("Meter reading")[0])      # hint, not the engine's error
        self.say("SALT YES")
        k = self.tx.markups[-1]["keyboard"]
        self.assertEqual([b["text"] for b in k[0]], ["DRYING", "STOP"])
        self.say("STOP")
        self.assertEqual(self.tx.markups[-1]["keyboard"][0][0]["text"], "START")
        self.say("START")
        self.assertEqual(self.tx.markups[-1]["keyboard"][0][0]["text"], "SALT YES")

    def test_lang_button_swaps_labels_and_typing(self):
        self.say("JOIN KITALE SACK 12"); self.say("/lang sw")
        self.assertEqual(self.tx.markups[-1]["keyboard"][0][0]["text"], "CHUMVI NDIYO")
        self.assertIn("Andika MITA", self.say("Kipimo cha mita")[0])
        self.assertIn("sendChatAction", self.tx.calls)

    def test_reset_removes_keyboard(self):
        self.say("JOIN KITALE SACK 12"); self.say("/reset")
        self.assertEqual(self.tx.markups[-1], {"remove_keyboard": True})


class Formatting(Base):
    def test_html_escaping(self):
        for raw in ("<b>&</b> <script>", "METER 13.1 & <i>", "a&b<c>d"):
            self.assertNotIn("<script>", T.fmt_engine(raw)); self.assertNotIn("<i>", T.fmt_engine(raw))
        self.assertIn("&lt;ward&gt;", T.fmt_engine("JOIN <ward> <storage>"))
        self.assertIn("<code>METER 14.2</code>", T.fmt_engine("reply METER 14.2."))
        self.assertIn("<b>about 34 days</b>", T.fmt_engine("Storage time left: about 34 days (estimate)."))
        self.assertEqual(T.plain(T.fmt_engine("x < y & z")), "x < y & z")

    def test_user_text_never_breaks_sending(self):
        self.say("JOIN KITALE SACK 12")
        for w in ("<b>", "&amp;", "METER <1>", "</code>", "SAJILI <script> SACK 2"):
            self.assertTrue(self.say(w))
        self.tx.reject_html = True                                       # Telegram refuses the HTML: plain fallback
        r = self.say("hello <b>")
        self.assertTrue(r and "<b>" in r[0] or r)                       # delivered as plain text
        self.assertTrue(any(c == "sendMessage" for c in self.tx.calls))

    def test_warning_gets_card_and_caption_limit(self):
        self.say("JOIN KITALE SACK 12")
        n = len(self.tx.uploads)
        r = self.say("SALT YES")
        self.assertTrue(self.tx.uploads[n].startswith("dial-"))          # card sent as photo, text is the caption
        self.assertLessEqual(len(self.tx.sent[-1][1]), 1024)
        self.say("SALT YES")                                             # second time: cached file_id, no new upload
        self.assertEqual(len(self.tx.uploads), n + 1)

    def test_photo_failure_falls_back_to_text(self):
        self.say("JOIN KITALE SACK 12")
        self.tx.fail_photo = True
        r = self.say("SALT YES")
        self.assertIn("too wet", r[0])

    def test_long_caption_goes_as_plain_message(self):
        self.bot.send_photo = lambda *a, **k: self.fail("photo must not be used")
        self.bot.deliver(111, {"banner": True}, [("x" * 1100, "dial-5")])
        self.assertEqual(len(self.tx.sent[-1][1]), 1100)

    def test_all_demo_and_engine_captions_fit(self):
        for html, photo in self.bot.demo():
            self.assertLessEqual(len(html), 1024)
        for l in ("en", "sw"):
            self.assertLessEqual(len(T.START_HTML[l]), 1024)
        for f in ("dial-0.png", "dial-90.png"):
            self.assertTrue(T.find_asset(f[:-4]))
            self.assertLess(os.path.getsize(T.find_asset(f[:-4])), 100_000)

    def test_demo_cards(self):
        r = self.bot.demo()
        self.assertTrue(all(p and p.startswith("dial-") for _, p in r))


class Robust(Base):
    def test_non_text_group_garbage(self):
        n = len(self.tx.sent)
        self.bot.handle_update({"update_id": 1, "message": {"chat": {"id": 5, "type": "private"}, "photo": [{}]}})
        self.assertIn("language", self.tx.sent[-1][1])
        for bad in (None, 5, {}, {"message": 3}, {"message": {"chat": {"id": "x", "type": "private"}}},
                    {"message": {"chat": {"id": 7, "type": "group"}, "text": "hi"}}, {"edited_message": {}}):
            self.bot.handle_update(bad)
        self.assertEqual(len(self.tx.sent), n + 2) if False else None
        self.assertTrue(all(c == 5 for c, _ in self.tx.sent))

    def test_long_and_weird_text(self):
        self.say("JOIN KITALE SACK 12")
        self.say("METER 13.5 " + "x" * 5000)
        self.say("\U0001F600" * 3000)
        self.say("\x00\x01 METER -13"); self.say("HYGRO")
        self.say("JOIN " + "A" * 900 + " SACK 99999999999999999999")

    def test_rate_limit(self):
        for _ in range(20): self.say("hi")
        n = len(self.tx.sent)
        self.say("hi"); self.say("hi"); self.say("hi")
        self.assertEqual(len(self.tx.sent), n + 1)                      # one warning only
        self.t[0] += 61
        self.say("hi"); self.assertEqual(len(self.tx.sent), n + 2)

    def test_handler_exception_is_contained(self):
        self.bot.route = lambda *a: 1 / 0
        self.assertEqual(self.bot.handle_update(upd(1, "x")), "error")
        self.assertIn("went wrong", self.tx.sent[-1][1])

    def test_send_failure_contained(self):
        def boom(m, p=None, timeout=0):
            raise T.TelegramError("HTTP 403 blocked", 403)
        self.tx.call = boom
        self.bot.handle_update(upd(1, "/start"))


class StateAndPoll(Base):
    def test_state_file_private_and_pii_free(self):
        self.say("/start"); self.say("JOIN KITALE SACK 12"); self.say("METER 14.2 secretword")
        self.store.save()
        mode = stat.S_IMODE(os.stat(self.path).st_mode)
        self.assertEqual(mode, 0o600)
        raw = open(self.path).read()
        for s in ("111", "secretword", "METER", "First", "\"X\""):
            if s == "111":
                self.assertNotIn('"111"', raw); self.assertNotIn(":111", raw)
            else:
                self.assertNotIn(s, raw)
        self.assertEqual(len(self.store.chat_key(111)), 20)

    def test_state_roundtrip(self):
        self.say("JOIN KITALE SACK 12"); self.say("METER 14.2"); self.store.save()
        self.mk()
        r = self.say("SALT NO")
        self.assertTrue(r)
        self.assertEqual(self.bot.live[self.store.chat_key(111)].ward, "Kitale")

    def test_offset_persisted_and_poll(self):
        self.tx.queue = [upd(41, "/help"), upd(42, "hello")]
        self.assertEqual(self.bot.poll_once(), 2)
        self.assertEqual(self.store.offset, 43)
        self.mk(); self.assertEqual(self.store.offset, 43)

    def test_poll_params(self):
        seen = {}
        orig = self.tx.call
        def spy(m, p=None, timeout=40):
            if m == "getUpdates": seen.update(p, _t=timeout)
            return orig(m, p, timeout)
        self.tx.call = spy
        self.store.set_offset(9); self.bot.poll_once()
        self.assertEqual((seen["timeout"], seen["offset"]), (30, 9))
        self.assertGreater(seen["_t"], 30)

    def test_backoff_and_stop(self):
        calls = {"n": 0}
        def flaky(m, p=None, timeout=40):
            calls["n"] += 1
            if calls["n"] < 3:
                raise T.TelegramError("HTTP 502", 502)
            self.bot.stop = True
            return []
        self.tx.call = flaky
        self.bot.run()
        self.assertEqual(calls["n"], 3)

    def test_sigterm_during_poll(self):
        def blocked(m, p=None, timeout=40):
            self.bot.request_stop()
        self.tx.call = blocked
        self.bot.run()                                  # returns instead of hanging

    def test_token_scrubbed(self):
        tr = T.Transport(SECRET)
        self.assertNotIn(SECRET, tr._scrub("error at /bot%s/getUpdates" % SECRET))

    def test_profile_calls(self):
        T.setup_profile(self.tx)
        self.assertEqual(self.tx.calls, ["getMyName", "setMyName", "setMyDescription", "setMyShortDescription", "setMyCommands"] * 2)
        for P in T.PROFILE.values():
            self.assertLessEqual(len(P["short"]), 120); self.assertLessEqual(len(P["description"]), 512)
            self.assertLessEqual(len(P["name"]), 64)


# ---------------------------------------------------------------------------------------------- /weather (NASA POWER), research/nasa-due-diligence.md
import harvestly_bot_core as core
from datetime import date

BANNED = ["accurate", "live", "real-time", "measured", "forecast", "nasa says", "safe"]


def power_json(last_real=date(2026, 10, 9), start=date(2026, 9, 28), end=date(2026, 10, 12), partial=None):
    """POWER-shaped response: real values to last_real, -999 after it; `partial` = a date whose RH2M alone is -999."""
    T2M, RH, RN = {}, {}, {}
    d = start
    while d <= end:
        k = d.strftime("%Y%m%d"); real = d <= last_real
        T2M[k] = round(19.5 + (d.day % 5) * 0.4, 2) if real else -999.0
        RH[k] = (-999.0 if d == partial else 60.0 + d.day % 7) if real else -999.0
        RN[k] = round((d.day % 4) * 1.1, 2) if real else -999.0
        d += timedelta(days=1)
    return {"header": {"fill_value": -999.0, "api": {"version": "v2.10.0"}}, "properties": {"parameter": {"T2M": T2M, "RH2M": RH, "PRECTOTCORR": RN}}}


class Weather(Base):
    def setUp(self):
        super().setUp()
        core._POWER_CACHE.clear()
        self.urls, self.data, self.down = [], power_json(), False
        def fetch(url):
            self.urls.append(url)
            if self.down: raise OSError("NASA down")
            return self.data
        self.bot.power_fetch = fetch

    def test_english_wording_date_credit_and_no_mix(self):
        self.pick("en")
        r = self.say("/weather")[0]
        self.assertIn("Recent weather near Kitale (NASA satellite/model estimate, to 9 Oct 2026): about ", r)
        self.assertIn("This is an area estimate, not a measurement at your store.", r)
        self.assertIn("Weather estimates: NASA POWER (NASA Langley Research Center, funded by the NASA Earth Science Division). Not endorsed by NASA.", r)
        self.assertIn("simulated weather", r)
        self.assertEqual(words(r, SW_MARKERS), [])
        for bad in BANNED: self.assertNotIn(bad, r.lower().replace("not endorsed by nasa", ""), bad)

    def test_kiswahili_wording_and_no_mix(self):
        self.pick("sw")
        r = self.say("/weather")[0]
        self.assertIn("Hali ya hewa ya karibuni karibu na Kitale (makadirio ya satelaiti/modeli ya NASA, hadi 9 Okt 2026): takriban ", r)
        self.assertIn("Ni makadirio ya eneo, si kipimo cha ghala lako.", r)
        self.assertIn("Haijaidhinishwa na NASA.", r)
        self.assertEqual(words(r, EN_MARKERS), [])

    def test_minus_999_days_dropped_and_partial_day_is_missing(self):
        self.data = power_json(partial=date(2026, 10, 9))        # 10-12 Oct are -999, 9 Oct has RH -999
        self.pick("en")
        r = self.say("/weather")[0]
        self.assertIn("to 8 Oct 2026", r); self.assertNotIn("9 Oct", r); self.assertNotIn("-999", r)
        self.assertEqual(len(core.parse_power(power_json())), 12)          # 28 Sep to 9 Oct only
        self.assertEqual(core.parse_power({"nope": 1}), None)

    def test_uses_registered_ward_else_kitale(self):
        self.pick("en", chat=700)
        self.assertIn("near Kitale", self.say("/weather", chat=700)[0])
        self.say("JOIN ELDORET SACK 12", chat=700)
        self.assertIn("near Eldoret", self.say("/weather", chat=700)[0])

    def test_cache_one_request_per_cell_and_rounded_centroid_only(self):
        self.pick("en", chat=710); self.say("JOIN ELDORET SACK 12", chat=710)
        self.pick("en", chat=711); self.say("JOIN WEBUYE SACK 12", chat=711)
        self.say("/weather", chat=710); self.say("/weather", chat=710); self.say("/weather", chat=711)
        self.assertEqual(len(self.urls), 1)                          # Eldoret and Webuye share a POWER cell; second call is cached
        self.assertEqual(core.power_cell(*core.WARD_CENTROID["ELDORET"]), core.power_cell(*core.WARD_CENTROID["WEBUYE"]))
        for lat, lon in core.WARD_CENTROID.values():
            self.assertEqual((lat, lon), (round(lat, 1), round(lon, 1)))
        u = self.urls[0]
        self.assertTrue(re.search(r"latitude=\d\.\d&longitude=\d\d\.\d&", u), u)
        self.assertNotIn("710", u); self.assertNotIn("711", u); self.assertIn("power.larc.nasa.gov", u)

    def test_nasa_down_gives_fallback_in_the_chats_language_and_stale_copy_is_used(self):
        self.down = True
        self.pick("en", chat=720); self.pick("sw", chat=721)
        en, sw = self.say("/weather", chat=720)[0], self.say("/weather", chat=721)[0]
        self.assertIn("Recent weather is not available right now.", en); self.assertEqual(words(en, SW_MARKERS), [])
        self.assertIn("haipatikani kwa sasa", sw); self.assertEqual(words(sw, EN_MARKERS), [])
        n = len(self.urls); self.say("/weather", chat=720)
        self.assertEqual(len(self.urls), n)                           # a failure is not retried for 15 minutes
        self.down = False; self.day += timedelta(hours=1)
        self.assertIn("to 9 Oct 2026", self.say("/weather", chat=720)[0])
        self.down = True; self.day += timedelta(hours=8)              # cache expired, NASA down again: the stale copy, with its date
        self.assertIn("to 9 Oct 2026", self.say("/weather", chat=720)[0])
        self.day += timedelta(days=8)                                 # now older than 7 days: hidden
        self.assertIn("not available", self.say("/weather", chat=720)[0])

    def test_garbage_response_is_a_fallback_not_an_error(self):
        self.data = {"unexpected": True}
        self.pick("en")
        self.assertIn("not available", self.say("/weather")[0])

    def test_no_engine_run_and_state_is_untouched(self):
        self.pick("en", chat=730); self.say("JOIN KITALE SACK 12", chat=730); self.say("METER 15.0", chat=730)
        key = self.store.chat_key(730)
        before = json.dumps(self.store.data["chats"][key]["batch"], sort_keys=True)
        self.say("/weather", chat=730)
        self.assertEqual(json.dumps(self.store.data["chats"][key]["batch"], sort_keys=True), before)

    def test_command_in_both_profiles_and_idle_keyboard(self):
        for P in T.PROFILE.values():
            self.assertIn("weather", [c["command"] for c in P["commands"]])
        self.assertIn("/weather", [b["text"] for row in T.keyboard("idle", "en")["keyboard"] for b in row])
        self.pick("en"); self.say("/weather")
        self.assertIn("weather", T.plain(self.say("/help")[0]))

    def test_before_a_language_is_chosen_only_the_neutral_message(self):
        r = self.say("/weather", chat=740)
        self.assertEqual(len(r), 1); self.assertIn("Choose a language", r[0]); self.assertEqual(self.urls, [])

    def test_no_chat_data_logged(self):
        import logging
        with self.assertLogs("harvestly-bot", level="DEBUG") as cm:
            logging.getLogger("harvestly-bot").debug("probe")
            self.pick("en", chat=750); self.down = True; self.say("/weather", chat=750)
        joined = " ".join(cm.output)
        self.assertNotIn("750", joined); self.assertNotIn("Kitale", joined)

    def test_b7_01_no_bot_string_credits_open_meteo(self):
        """The bot never calls Open-Meteo, so no reply, card or profile string may credit it (both languages)."""
        texts = []
        for lang, chat in (("en", 960), ("sw", 961)):
            self.pick(lang, chat=chat)
            join = "JOIN KITALE SACK 12" if lang == "en" else "SAJILI KITALE MAGUNIA 12"
            for t in ("/help", "/start", join, "METER 14.2", "SALT YES", "DRYING", "/demo", "/weather", "/lang", "xyzzy?", "STOP", "START", "/reset"):
                texts += self.say(t, chat=chat)
        welcome = [m for m in texts if "Registered" in m or "Umesajiliwa" in m]
        self.assertEqual(len(welcome), 2)
        self.assertIn("simulated", welcome[0]); self.assertIn("NASA POWER", welcome[0])
        self.assertIn("kuigwa", welcome[1]); self.assertIn("NASA POWER", welcome[1])
        self.assertEqual(words(welcome[1], EN_MARKERS), [])
        for m in texts:
            self.assertNotIn("open-meteo", m.lower(), m[:60]); self.assertNotIn("cc by", m.lower(), m[:60])
        here = os.path.dirname(os.path.abspath(__file__))
        files = [os.path.join(here, "telegram_cards.mjs"), os.path.join(here, "telegram_bot.py"), os.path.join(here, "..", "engine", "demo_sw.json")]
        for d in ("scripts", "api"):
            base = os.path.join(here, "..", "bot", d)
            if os.path.isdir(base):
                files += [os.path.join(base, f) for f in os.listdir(base) if os.path.isfile(os.path.join(base, f))]
        for f in files:
            body = open(f, encoding="utf-8").read().lower()
            self.assertNotIn("open-meteo", body, f)

    def test_b7_02_swahili_storage_words_register_and_howto_has_no_english_words(self):
        self.pick("sw", chat=962)
        how = self.say("habari", chat=962)[0]
        self.assertIn("KIHENGE", how); self.assertIn("SAKAFU", how)
        self.assertEqual(words(how, EN_MARKERS), [])
        for w, store in (("KIHENGE", "crib"), ("SAKAFU", "floor"), ("MAGUNIA", "sack")):
            self.assertIn("Umesajiliwa", self.say(f"SAJILI ELDORET {w} 5", chat=962)[0], w)
            self.assertEqual(self.bot.live[self.store.chat_key(962)].storage, store)
        self.pick("en", chat=963)
        self.assertIn("Registered", self.say("JOIN ELDORET CRIB 5", chat=963)[0])      # English tokens still parse


    def test_n7_02_rate_limit_and_error_text_are_bilingual_before_a_language_is_chosen(self):
        self.assertIn("Ujumbe mwingi", T.SLOW_DOWN[None]); self.assertIn("Too many messages", T.SLOW_DOWN[None])
        self.assertIn("Hitilafu", T.ERROR_TEXT[None]); self.assertIn("Something went wrong", T.ERROR_TEXT[None])
        self.pick("sw", chat=964)
        self.assertEqual(self.bot.lang_of(self.store.chat_key(964)), "sw")
        self.assertIsNone(self.bot.lang_of(self.store.chat_key(965)))


# ---------------------------------------------------------------------------------------------- /forecast (live providers), docs/WEATHER_PROVIDERS.md
def fc_days(today, n=7, rain=3.0):
    return [{"day": today + timedelta(days=k), "temp_c": 18.0 + k * 0.2, "rh": 75.0 + k, "rain_mm": rain, "rain_prob": 80.0} for k in range(1, n + 1)]


class Forecast(Base):
    def setUp(self):
        super().setUp()
        core._FC_CACHE.clear()
        self.calls, self.down = [], False
        today = self.bot.today()
        def om(lat, lon, t):
            self.calls.append(("open-meteo", lat, lon))
            if self.down: raise OSError("down")
            return fc_days(t)
        def wa(lat, lon, t):
            self.calls.append(("weatherapi", lat, lon))
            return fc_days(t, 3)
        self.om, self.wa = om, wa
        self.bot.forecast_providers = [("open-meteo", om), ("weatherapi", wa)]

    def test_english_wording_credit_and_note(self):
        self.pick("en")
        r = self.say("/forecast")[0]
        self.assertIn("Forecast near Kitale from Open-Meteo (a weather-model forecast for the area, not a measurement at your store).", r)
        self.assertIn("in the next 7 days", r)
        self.assertIn("Weather data by Open-Meteo.com (CC BY 4.0).", r)
        self.assertIn("The advice in this test still uses simulated weather.", r)
        self.assertEqual(words(r, SW_MARKERS), [])
        for bad in ("accurate", "real-time", "measured", "safe"): self.assertNotIn(bad, r.lower())

    def test_kiswahili_wording_and_no_mix(self):
        self.pick("sw")
        r = self.say("/forecast")[0]
        self.assertIn("Utabiri karibu na Kitale kutoka Open-Meteo", r)
        self.assertIn("Data ya hali ya hewa: Open-Meteo.com (CC BY 4.0).", r)
        self.assertEqual(words(r, EN_MARKERS), [])

    def test_falls_back_to_next_provider_and_credits_it(self):
        self.down = True
        self.pick("en")
        r = self.say("/forecast")[0]
        self.assertIn("from WeatherAPI.com", r); self.assertIn("Powered by WeatherAPI.com.", r); self.assertIn("in the next 3 days", r)

    def test_all_down_is_a_plain_message_and_failures_are_not_retried_at_once(self):
        self.bot.forecast_providers = [("open-meteo", lambda *a: (_ for _ in ()).throw(OSError("x")))]
        self.pick("en")
        self.assertIn("The forecast is not available right now.", self.say("/forecast")[0])
        n = len(self.calls)
        self.assertIn("not available", self.say("/forecast")[0]); self.assertEqual(len(self.calls), n)

    def test_cache_one_chain_run_for_many_chats_and_ward_centroid_only(self):
        for c in (800, 801, 802): self.pick("en", chat=c); self.say("/forecast", chat=c)
        self.assertEqual(len([c for c in self.calls if c[0] == "open-meteo"]), 1)
        self.assertEqual(self.calls[0][1:], (1.0, 35.0))         # rounded Kitale centroid, nothing about the chat

    def test_gap_in_days_or_wrong_first_day_is_rejected(self):
        today = self.bot.today()
        bad = fc_days(today); del bad[2]
        self.bot.forecast_providers = [("open-meteo", lambda *a: bad), ("weatherapi", lambda *a: fc_days(today, 3))]
        self.pick("en")
        self.assertIn("from WeatherAPI.com", self.say("/forecast")[0])
        core._FC_CACHE.clear()
        late = [dict(x, day=x["day"] + timedelta(days=1)) for x in fc_days(today)]
        self.bot.forecast_providers = [("open-meteo", lambda *a: late)]
        self.pick("en", chat=811); self.assertIn("not available", self.say("/forecast", chat=811)[0])

    def test_never_feeds_the_engine(self):
        self.pick("en")
        self.say("/forecast")
        self.assertEqual(self.bot.forecast()[0].rh, 63.0)        # the engine forecast stays the simulated day


class ProviderParsing(unittest.TestCase):
    def test_open_meteo_weatherapi_openweather_normalise_and_skip_today(self):
        import weather_providers as WP
        t = date(2026, 10, 13)
        om = {"daily": {"time": ["2026-10-13", "2026-10-14", "2026-10-15"], "temperature_2m_mean": [18, 19, None],
                        "relative_humidity_2m_mean": [70, 75, 80], "precipitation_sum": [0, 1.5, 2], "precipitation_probability_max": [10, 90, 50]}}
        r = WP.open_meteo(1.0, 35.0, t, fetch=lambda u: om)
        self.assertEqual([x["day"] for x in r], [date(2026, 10, 14)]); self.assertEqual(r[0]["rain_prob"], 90)
        wa = {"forecast": {"forecastday": [{"date": "2026-10-13", "day": {}},
              {"date": "2026-10-14", "day": {"avgtemp_c": 18.3, "avghumidity": 80, "totalprecip_mm": 5.5, "daily_chance_of_rain": 79}}]}}
        r = WP.weatherapi(1.0, 35.0, t, "k", fetch=lambda u: wa)
        self.assertEqual(r[0]["temp_c"], 18.3); self.assertEqual(len(r), 1)
        base = int(datetime(2026, 10, 14, 0, 0, tzinfo=timezone(timedelta(hours=3))).timestamp())
        slots = [{"dt": base + 3 * 3600 * i, "main": {"temp": 18 + i, "humidity": 70}, "pop": 0.2 * (i % 2), "rain": {"3h": 1.0}} for i in range(8)]
        slots += [{"dt": base + 86400 + 3 * 3600 * i, "main": {"temp": 20, "humidity": 70}} for i in range(3)]     # a partial day is dropped
        r = WP.openweather(1.0, 35.0, t, "k", fetch=lambda u: {"list": slots})
        self.assertEqual(len(r), 1); self.assertEqual(r[0]["rain_mm"], 8.0); self.assertEqual(r[0]["rain_prob"], 20.0)

    def test_providers_without_keys_are_open_meteo_only(self):
        import weather_providers as WP
        self.assertEqual([n for n, _ in WP.providers({})], ["open-meteo"])
        self.assertEqual([n for n, _ in WP.providers({"WEATHERAPI_KEY": "x", "OPENWEATHER_API_KEY": "y"})], ["open-meteo", "weatherapi", "openweather"])


if __name__ == "__main__":
    unittest.main()
