#!/usr/bin/env python3
"""Apply the Russian word-by-word gloss to data/wbw/words/*.json.

Two sources (per-token override wins over the phrase dictionary):
  data/wbw/ru_gloss.json    {"s:a:w": "<ru>"}   hand-checked, verse-specific
  data/wbw/ru_phrases.json  {"<en>": "<ru>"}    literal phrase dictionary
For every word: ru = override[s:a:w]  or  phrases[en].  Writes "ru" back into
words/*.json and prints coverage. Run after editing either source file.
"""
import json, glob, os
ROOT = os.path.dirname(os.path.abspath(__file__))
W = os.path.join(ROOT, "data", "wbw")
ov = json.load(open(os.path.join(W, "ru_gloss.json"), encoding="utf-8")) if os.path.exists(os.path.join(W,"ru_gloss.json")) else {}
ph = json.load(open(os.path.join(W, "ru_phrases.json"), encoding="utf-8")) if os.path.exists(os.path.join(W,"ru_phrases.json")) else {}
tot = done = 0
for fn in glob.glob(os.path.join(W, "words", "*.json")):
    d = json.load(open(fn, encoding="utf-8"))
    for a, ws in d.items():
        for w, rec in ws.items():
            tot += 1
            s = os.path.basename(fn)[:-5]
            key = f"{s}:{a}:{w}"
            ru = ov.get(key) or ph.get((rec.get("en") or "").strip())
            if ru:
                rec["ru"] = ru; done += 1
            elif "ru" in rec:
                # больше не резолвится ни из override, ни из словаря — убираем устаревший глосс
                del rec["ru"]
    json.dump(d, open(fn, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(f"ru filled: {done}/{tot} = {done*100//tot}%   (overrides {len(ov)}, phrases {len(ph)})")
