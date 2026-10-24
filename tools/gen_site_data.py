"""Build site/assets/js/data.js from the engine: replays the three vectors.json scenarios through
respond() and daily_run() (same code as make_vectors.py), keeps the SMS text in English and
Kiswahili (straight from the engine's TEMPLATES), and checks the result against vectors.json.
Run from anywhere:  python3 tools/gen_site_data.py

Output notes (both are written into data.js for the pages to show):
  * The demo weather is SIMULATED, so demo SMS text carries the credit "Simulated weather", never "Open-Meteo".
    Pages that show real weather must carry the linked attribution in ATTRIBUTION (Open-Meteo CC BY 4.0).
  * days_left 365 is HORIZON_DAYS, the longest the engine looks ahead. Events carry capped=true for it:
    show it as "365+ (the tool stops looking)", never as a prediction.
  * ASSUMPTIONS is the engine's own labelled assumption list (SOURCE / CALIBRATION / PROGRAMME / UNVALIDATED)."""
import json, sys, pathlib
from datetime import date, timedelta
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine"))
import harvestly_engine as H
import make_vectors as M

SW_REPLY = [("SALT YES", "CHUMVI NDIYO"), ("SALT NO", "CHUMVI HAPANA"), ("SEALED", "NIMEFUNGA"),
            ("DRYING", "ANIKA"), ("METER", "MITA")]
def sw(t):
    for a, b in SW_REPLY:
        if t.startswith(a): return b + t[len(a):]
    return t

DEMO_CREDIT = "Simulated weather"
DEMO_CREDIT_SW = "Hali ya hewa ya kuigwa"      # N6-03: Kiswahili bubbles credit the simulation in Kiswahili (the bot does the same)


def run(name, storage, days, wx, replies, lang):
    b = H.Batch(name, "Kitale", storage, M.D0); b.lang = lang
    out = []
    for off in range(days):
        today = M.D0 + timedelta(days=off)
        wl = M.weather_list(today, wx)
        fc = [w for w in wl if w.day > today]
        for text in replies.get(off, []):
            t = sw(text) if lang == "sw" else text
            cmd, a = H.respond(b, t, today, fc, meta=H.WeatherMeta(today, 0.0, DEMO_CREDIT))
            out.append(dict(day=off, date=today.isoformat(), kind="reply", reply=t, cmd=cmd,
                            code=a.code if a else None, text=a.text if a else None))
        a, d = H.daily_run(b, today, wl, meta=H.WeatherMeta(today, 0.0, DEMO_CREDIT))
        out.append(dict(day=off, date=today.isoformat(), kind="evening", code=a.code if a else None,
                        text=a.text if a else None, level=d["level"], days_left=d["days_left"],
                        capped=d["days_left_capped"], moisture=d["moisture"], life=d["life_used_pct"]))
    return out

def demo_wx(issued, d):
    k = (d - M.D0).days
    if 4 <= k <= 11 and (issued - M.D0).days >= 3:
        return (18.0, 88.0, 12.0 if k == 9 else 0.0, 80.0 if k == 9 else 20.0)
    return (18.0, 63.0, 0.0, 10.0)

def wx_rows(days, wx, with_fc=False):
    """What the weather actually was each day (as issued that day) and the 7-day forecast issued that evening."""
    out = []
    for off in range(days):
        today = M.D0 + timedelta(days=off)
        t, rh, mm, p = wx(today, today)
        fc = [dict(zip(("t", "rh", "mm", "p"), wx(today, today + timedelta(days=k)))) for k in range(1, 8)]
        out.append(dict(day=off, t=t, rh=rh, mm=mm, p=p, **({"fc": fc} if with_fc else {})))
    return out

SC = [("demo_pitch", "sack", 13, demo_wx, {0: ["SALT YES"], 4: ["DRYING"], 12: ["SALT NO", "METER 13.1", "SEALED"]}),
      ("salt_pass_then_seal", "drying", 22, lambda i, d: (18.0, 70.0, 0.0, 10.0), {0: ["SALT NO"], 1: ["SEALED"], 20: ["METER 13.2"]}),
      ("dry_grain_rewets", "sack", 70, lambda i, d: (19.0, 92.0, 0.0, 10.0), {0: ["METER 13.0"]})]
ref = json.load(open(ROOT / "engine" / "vectors.json"))["scenarios"]
res = []
for (n, st, days, wx, rep), r in zip(SC, ref):
    en = run(n, st, days, wx, rep, "en"); s = run(n, st, days, wx, rep, "sw")
    # 1. identical to the published reference vectors
    got = [(e["date"], e["code"]) for e in en]; want = [(t["day"], t["code"]) for t in r["trace"]]
    assert got == want, n
    for e, t in zip([e for e in en if e["kind"] == "evening"], [t for t in r["trace"] if t["event"] == "evening"]):
        assert (e["level"], e["days_left"], e["moisture"], e["life"]) == (t["level"], t["days_left"], t["moisture"], t["life_used_pct"]), n
    # 2. Kiswahili replies drive the engine to the same decisions
    assert [(e["code"], e.get("days_left")) for e in en] == [(e["code"], e.get("days_left")) for e in s], n
    res.append(dict(name=n, storage=st, days=days, start=M.D0.isoformat(), weather=wx_rows(days, wx, n == "demo_pitch"),
                    events=[dict(e, text_sw=(x["text"] or "").replace(DEMO_CREDIT, DEMO_CREDIT_SW) or None, reply_sw=x.get("reply")) for e, x in zip(en, s)]))
# Kiswahili /demo for the Telegram bot: the same steps as vectors.json demo_pitch, but run through the engine in Kiswahili
# (replies in Kiswahili, Kiswahili templates, Kiswahili credit). Written next to vectors.json; bot/sync-engine.sh copies it.
_d = res[0]
_left = {e["day"]: e["days_left"] for e in _d["events"] if e["kind"] == "evening"}
_steps = [dict(day=e["day"], said=e.get("reply_sw"), text=e["text_sw"], left=_left.get(e["day"]) if e["kind"] == "evening" else None)   # as vectors.json: only evening alerts carry a dial
          for e in _d["events"] if e["text_sw"]]
_ref = [t for t in ref[0]["trace"] if t.get("message")]
assert len(_steps) == len(_ref), "Kiswahili demo has a different number of steps than vectors.json"
assert [(st["said"] is not None) for st in _steps] == [(t["event"] == "reply") for t in _ref]
(ROOT / "engine" / "demo_sw.json").write_text(json.dumps(dict(lang="sw", scenario="demo_pitch", steps=_steps), ensure_ascii=False, indent=1) + "\n")
tpl = {k: {"en": v[0], "sw": v[1]} for k, v in H.TEMPLATES.items()}
out = ROOT / "site/assets/js/data.js"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text("// Generated by tools/gen_site_data.py from the engine. Do not edit.\nexport const SCENARIOS=" + json.dumps(res, ensure_ascii=False, separators=(",", ":"))
               + ";\nexport const TEMPLATES=" + json.dumps(tpl, ensure_ascii=False, separators=(",", ":")) + ";\n"
               + "export const ATTRIBUTION=" + json.dumps(H.ATTRIBUTION) + ";\n"
               + "export const ASSUMPTIONS=" + json.dumps([dict(id=i, label=l, text=t) for i, l, t in H.ASSUMPTIONS],
                                                           ensure_ascii=False, separators=(",", ":")) + ";\n")
(ROOT / "tools" / "site-src" / "templates.json").parent.mkdir(parents=True, exist_ok=True)
(ROOT / "tools" / "site-src" / "templates.json").write_text(json.dumps(tpl, ensure_ascii=False, indent=1))
print("ok", [len(r["events"]) for r in res], out.stat().st_size)
