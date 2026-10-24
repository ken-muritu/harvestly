"""Write golden test vectors (vectors.json) from the Python reference engine.

The PL/SQL (or any other) port must reproduce every value: EMC and AST to 1e-6, days_left
exactly, and each scenario's message sequence exactly. Scenarios are driven through the same
entry points production uses: respond() for farmer replies during the day, daily_run() at 17:00.

Run:  python3 make_vectors.py
"""
import json
from datetime import date, timedelta

import harvestly_engine as H

D0 = date(2026, 10, 12)


def weather_list(today, wx):
    """Daily weather from today-2 to today+7 as issued on `today`:
    wx(issued, day) -> (temp, rh, rain_mm, rain_prob). Letting the forecast depend on the issue
    date reproduces what a farmer actually experiences: a wet spell appears in the forecast."""
    return [H.WeatherDay(today + timedelta(days=k), *wx(today, today + timedelta(days=k)))
            for k in range(-2, 8)]


def scenario(name, storage, days, wx, replies):
    """replies: {day_offset: [text, ...]} sent during that day, before the evening run."""
    b = H.Batch(name, "Kitale", storage, D0)
    trace = []
    for off in range(days):
        today = D0 + timedelta(days=off)
        wl = weather_list(today, wx)
        forecast = [w for w in wl if w.day > today]
        for text in replies.get(off, []):
            cmd, a = H.respond(b, text, today, forecast)
            trace.append({"day": today.isoformat(), "event": "reply", "text": text, "cmd": cmd,
                          "code": a.code if a else None, "message": a.text if a else None})
        a, d = H.daily_run(b, today, wl)
        # moisture / life_used_pct are the DISPLAY strings (one rounding rule, half-up on the decimal);
        # *_exact are the unrounded values to 9 decimals, so accumulated drift is tested, not only its rounding.
        trace.append({"day": today.isoformat(), "event": "evening", "code": a.code if a else None,
                      "level": d["level"], "days_left": d["days_left"], "moisture": d["moisture"],
                      "life_used_pct": d["life_used_pct"],
                      "moisture_s": H.fmt1(d["moisture_raw"]), "life_used_pct_s": H.fmt1(100 * d["life_used_raw"]),
                      "moisture_exact": round(d["moisture_raw"], 9), "life_used_exact": round(d["life_used_raw"], 9),
                      "message": a.text if a else None})
    return {"name": name, "storage": storage, "start": D0.isoformat(), "days": days,
            "weather": "see make_vectors.py", "trace": trace}


def main():
    emc = [{"temp_c": t, "rh": rh, "emc": round(H.emc(t, rh)[0], 6)}
           for t in (10, 15, 18, 18.3, 21, 24, 30) for rh in (40, 55, 63, 70, 85, 90, 95)]
    ast = [{"temp_c": t, "mc": m, "days": round(H.ast_days(t, m)[0], 6)}
           for t in (10, 15, 18, 21, 24, 26) for m in (12, 13.5, 14.5, 15, 16.4, 18, 20, 23, 28, 32)]

    def demo_wx(issued, d):   # a wet El Nino spell (days 4-11) first appears in the day-3 forecast;
        k = (d - D0).days     # heavy rain is forecast for day 9
        if 4 <= k <= 11 and (issued - D0).days >= 3:
            return (18.0, 88.0, 12.0 if k == 9 else 0.0, 80.0 if k == 9 else 20.0)
        return (18.0, 63.0, 0.0, 10.0)

    scenarios = [
        scenario("demo_pitch", "sack", 13, demo_wx,
                 {0: ["SALT YES"], 4: ["DRYING"], 12: ["SALT NO", "METER 13.1", "SEALED"]}),
        scenario("salt_pass_then_seal", "drying", 22, lambda i, d: (18.0, 70.0, 0.0, 10.0),
                 {0: ["SALT NO"], 1: ["SEALED"], 20: ["METER 13.2"]}),
        scenario("dry_grain_rewets", "sack", 70, lambda i, d: (19.0, 92.0, 0.0, 10.0),
                 {0: ["METER 13.0"]}),
    ]
    # rounding: exact display strings. ties (13.25, 5.05 ...) are where ports used to disagree.
    ties = [5.05, 13.25, 13.35, 13.45, 13.5, 13.54, 13.95, 14.0, 14.04, 14.96, 15.0, 5.0, 40.0, 0.05, 12.349999999]
    rounding = [{"x": x, "fmt1": H.fmt1(x), "fmt2": H.fmt2(x)} for x in ties]
    rounding += [{"x": x, "fmt0": H.fmt0(x)} for x in (0.0, 0.4, 0.5, 1.5, 2.5, 6.5, 59.5, 60.0, 79.5, 100.0)]
    # evidence strings as the farmer sees them for a meter reading (includes the 2-decimal rule near a limit)
    b = H.Batch("E", "Kitale", "sack", D0)
    evidence = []
    for r in (13.25, 13.3, 13.46, 13.5, 13.54, 13.96, 14.0, 14.04, 14.96, 15.0, 15.04, 5.05, 40.0):
        b.record_meter(D0, r)
        evidence.append({"reading": r, "en": H._evidence(b, "en"), "sw": H._evidence(b, "sw")})
    optout = [{"text": t, "norm": H.normalise(t), "optout": H.is_optout(H.normalise(t))} for t in (
        "STOP", "stop", "Stop.", "UNSUBSCRIBE", "cancel", "END", "quit", "ACHA", "sitisha", "SIMAMISHA",
        "PLEASE STOP", "please stop!", "Tafadhali acha", "STOP ALL", "STOPP", "METER 13.5", "ENDING", "NO MORE",
        "hello", "", "  ", "STOP\u00a0NOW", "SALT YES", "PLEASE", "I WANT TO STOP", "no more please", "OPT OUT",
        "sitaki tena", "Nisitishie", "SEALED STOP", "the rain came and the maize is wet so what do I do and when can I stop")]
    long_text = "METER 13.5 " + "x" * 2000
    normalise = [{"text_len": len(t), "norm_len": len(H.normalise(t))} for t in (long_text, "\U0001F600" * 1500)]
    pepper = "test-pepper"
    addresses = [{"addr": a, "canonical": H.normalise_address(a), "hash": H.address_hash(a, pepper)} for a in (
        "+254712345678", "0712 345 678", "254712345678", "00254712345678", "tg:123456789", "TG:123456789")]
    # days_left over varying forecasts, every storage type, near thresholds (the JS port replays these)
    cases = []
    for storage in ("sack", "crib", "hermetic", "drying"):
        for m in (12.0, 13.5, 14.5, 15.0, 17.3, 18.0, 22.0):
            for life in (0.0, 0.45, 0.79, 0.99):
                fcs = [(18.0 + (k * 1.7) % 6, 55.0 + (k * 11) % 40) for k in range(7)]
                b = H.Batch("c", "K", storage, D0, moisture=m, source="meter", life_used=life)
                f = [H.WeatherDay(D0 + timedelta(k + 1), t, rh) for k, (t, rh) in enumerate(fcs)]
                left = H.days_left(b, f)
                cases.append({"storage": storage, "moisture": m, "life": life, "forecast": fcs, "left": left,
                              "level": H.risk_level(life, left)})
    cases.append({"storage": "sack", "moisture": 14.0, "life": 0.0, "forecast": [], "left": None, "level": "UNKNOWN"})
    out = {"engine": "harvestly_engine v4", "emc": emc, "ast": ast, "scenarios": scenarios,
           "rounding": rounding, "evidence": evidence, "optout": optout, "normalise": normalise,
           "pepper": pepper, "addresses": addresses, "days_left_cases": cases}
    with open("vectors.json", "w") as f:
        json.dump(out, f, indent=1)
    print(f"wrote vectors.json: {len(emc)} EMC, {len(ast)} AST, {len(scenarios)} scenarios")
    for s in scenarios:
        print(" ", s["name"] + ":", ", ".join(
            f"d{(date.fromisoformat(t['day']) - D0).days}:{t.get('text') or 'eve'}->{t['code']}"
            for t in s["trace"] if t["code"]))


if __name__ == "__main__":
    main()
