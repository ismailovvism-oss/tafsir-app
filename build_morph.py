#!/usr/bin/env python3
"""Build the word-by-word translation + morphology layers for the tafsir app.

Two data layers, both keyed by the word address "surah:ayah:word" (e.g.
"2:4:10") and split PER SURAH (like data/qpc/v1/surah/<s>.json) so a phone
only loads the surah being read. A clickable word carries only its address;
the card / gloss are pulled from these chunks on the fly. Shape {ayah:{word:..}}:

  data/wbw/words/<s>.json  -> per word: {"en": <gloss>, "ru_ref"?: <ref>, "ru"?: <our gloss>}
                              ("ru" merged from data/wbw/ru_gloss.json, Step 4)
  data/wbw/morph/<s>.json  -> per word: [ {segment}, {segment}, ... ]

"en"     is shown verbatim under each word (display-only, CC BY-NC-ND).
"ru_ref" is the data-quran Russian gloss kept ONLY as a hidden cross-check
         reference (low quality) — never shown as our translation.
"ru"     (our real Russian gloss) is a SEPARATE later pipeline (Step 4) and is
         intentionally NOT produced here; "ru" and "ru_ref" are never mixed.

A segment looks like (stem carries lemma/root/grammar, affixes are lean):

  {"ar":"ءَاخِرَةِ","pos":"N","type":"stem",
   "root":"أخر","lemma":"آخِر","gender":"F","number":"S","case":"GEN"}

SOURCES (all fetched from raw.githubusercontent.com; cached in data/_sources/):

  * Morphology  — mustafa0x/quran-morphology  (quran-morphology.txt)
      Arabic-script rewrite of the Quranic Arabic Corpus (corpus.quran.com).
      One line per SEGMENT: "s:a:w:seg\\tFORM\\tCAT\\tFEATURES".
      Licensed GNU GPL — attribution to http://corpus.quran.com is required
      and kept in data/wbw/ATTRIBUTION.txt.

  * Word glosses — hablullah/data-quran  (word-translation/{en,ru}-qurancom.json)
      Word-by-word English + Russian, scraped from quran.com. Keyed by the
      global word index 1..77429, which lines up 1:1 with the corpus word
      order (verified: identical 77429 words, zero drift). CC BY-NC-ND 4.0.

All three sources have exactly 77429 words and the same ordering, so the
global index <-> "s:a:w" mapping is built straight from the corpus.

Run:  python3 build_morph.py
"""
import json, os, re, sys, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(ROOT, "data", "_sources")
OUT_DIR = os.path.join(ROOT, "data", "wbw")

SOURCES = {
    "corpus.txt": "https://raw.githubusercontent.com/mustafa0x/quran-morphology/master/quran-morphology.txt",
    "en.json":    "https://raw.githubusercontent.com/hablullah/data-quran/master/word-translation/en-qurancom.json",
    "ru.json":    "https://raw.githubusercontent.com/hablullah/data-quran/master/word-translation/ru-qurancom.json",
}
# hablullah/data-quran is currently only reachable via the abolma44 mirror in
# some environments; fall back to it if the canonical host is blocked.
MIRRORS = {
    "en.json": "https://raw.githubusercontent.com/abolma44/data-quran/master/word-translation/en-qurancom.json",
    "ru.json": "https://raw.githubusercontent.com/abolma44/data-quran/master/word-translation/ru-qurancom.json",
}

ATTRIBUTION = """\
Word-by-word data sources
=========================

Morphology (segments, part of speech, root, lemma, grammar):
  Quranic Arabic Corpus — http://corpus.quran.com
  Arabic-script edition: https://github.com/mustafa0x/quran-morphology
  Licensed under the GNU General Public License.

Word-by-word translation (English gloss shown under each word):
  data-quran — https://github.com/hablullah/data-quran
  Collected by the Hablullah team from quran.com / Tanzil / QuranEnc.
  Licensed under CC BY-NC-ND 4.0.
  The English gloss is displayed VERBATIM (no modifications), non-commercially,
  with attribution — as required by the No-Derivatives term.

  The Russian gloss from this source is kept only as a hidden reference field
  ("ru_ref") for cross-checking; it is NOT shown to users and NOT redistributed
  as a modified/derivative dataset.

This attribution must be kept and shown to users (corpus.quran.com requires a
link back to the source).
"""

# --- fetch -----------------------------------------------------------------
def fetch(name, tries=4):
    path = os.path.join(SRC_DIR, name)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    os.makedirs(SRC_DIR, exist_ok=True)
    urls = [SOURCES[name]] + ([MIRRORS[name]] if name in MIRRORS else [])
    last = None
    for url in urls:
        for i in range(tries):
            try:
                print(f"  downloading {name} <- {url}", flush=True)
                req = urllib.request.Request(url, headers={"User-Agent": "tafsir-app-build"})
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = r.read()
                with open(path, "wb") as f:
                    f.write(data)
                return path
            except (urllib.error.URLError, TimeoutError) as e:
                last = e
    raise SystemExit(f"failed to fetch {name}: {last}")

# --- morphology parsing ----------------------------------------------------
# Part-of-speech tags that may appear as the FIRST feature token. When the
# first token is one of these it IS the part of speech; otherwise the coarse
# category column (N / V / P) is used (plain noun / verb).
POS_LABELS = {
    # particles & function words
    "P", "DET", "CONJ", "REM", "NEG", "ACC", "EMPH", "COND", "INTG", "SUB",
    "VOC", "RES", "CIRC", "CAUS", "AMD", "EXP", "EXL", "RSLT", "SUP", "PRO",
    "PREV", "ATT", "ANS", "RET", "EXH", "INT", "COM", "INC", "SUR", "AVR",
    "CERT", "FUT", "PRP", "EQ", "INL", "DIST", "ADDR",
    # nominals
    "PRON", "PN", "REL", "DEM", "T", "LOC", "VN", "ACT_PCPL", "PASS_PCPL",
    "IMPN",
}
# non-POS feature keys (so a stray gender/number token is never misread)
RESERVED = {
    "ROOT", "LEM", "VF", "PERF", "IMPF", "IMPV", "PASS", "ACT", "NOM", "ACC",
    "GEN", "INDEF", "MOOD", "DET", "PREF", "SUFF", "ADJ", "FAM",
}
GNP = re.compile(r"^([123])?([MF])?([SDP])?$")  # person / gender / number

def parse_segment(form, cat, feats):
    toks = feats.split("|")
    keys = [t.split(":", 1)[0] for t in toks]
    typ = "prefix" if "PREF" in keys else ("suffix" if "SUFF" in keys else "stem")

    f0 = keys[0]
    if cat == "V":
        pos = "V"
    elif f0 in POS_LABELS:
        pos = f0
    else:
        pos = cat  # plain noun (N) — first token is ROOT:/LEM:/grammar
    # the corpus marks adjectives as a trailing ADJ feature on a noun
    if pos == "N" and "ADJ" in keys:
        pos = "ADJ"

    seg = {"ar": form, "pos": pos, "type": typ}

    # parse grammatical features; skip the leading POS token itself (so an
    # accusative *particle* (ACC) is never recorded as accusative *case*)
    feat_toks = toks[1:] if (pos == f0) else toks
    for t in feat_toks:
        k, _, v = t.partition(":")
        if k == "ROOT":
            seg["root"] = v
        elif k == "LEM":
            seg["lemma"] = v
        elif k == "VF":
            seg["form"] = v  # verb form / порода, 1..10 -> rendered I..X client-side
        elif k in ("PERF", "IMPF", "IMPV"):
            seg["aspect"] = k
        elif k == "PASS":
            seg["voice"] = "PASS"
        elif k == "ACT":
            seg["voice"] = "ACT"
        elif k in ("NOM", "ACC", "GEN"):
            seg["case"] = k
        elif k == "INDEF":
            seg["indef"] = True
        elif ":" not in t and t not in RESERVED:
            m = GNP.fullmatch(t)
            if m and any(m.groups()):
                if m.group(1):
                    seg["person"] = m.group(1)
                if m.group(2):
                    seg["gender"] = m.group(2)
                if m.group(3):
                    seg["number"] = m.group(3)
    # affixes stay lean: only a one-letter particle's lexical info is noise, so
    # drop root/lemma/case/etc on prefixes & suffixes (pronoun person/gender/
    # number are kept — they carry the meaning of a suffix like ـكَ)
    if typ != "stem":
        for k in ("root", "lemma", "case", "indef", "form", "aspect", "voice"):
            seg.pop(k, None)
    return seg

# --- main ------------------------------------------------------------------
def main():
    corpus = fetch("corpus.txt")
    en = json.load(open(fetch("en.json"), encoding="utf-8"))
    ru = json.load(open(fetch("ru.json"), encoding="utf-8"))

    morph = {}      # "s:a:w" -> [segments]
    order = []      # word addresses in corpus order (global index -> address)
    seen = set()

    for raw in open(corpus, encoding="utf-8"):
        raw = raw.rstrip("\n")
        if not raw:
            continue
        parts = raw.split("\t")
        if len(parts) < 4:
            continue
        addr, form, cat, feats = parts[0], parts[1], parts[2], parts[3]
        s, a, w, seg_no = addr.split(":")
        key = f"{s}:{a}:{w}"
        if key not in seen:
            seen.add(key)
            order.append(key)
            morph[key] = []
        morph[key].append(parse_segment(form, cat, feats))

    n = len(order)
    print(f"corpus words: {n}")
    assert n == len(en) == len(ru) == 77429, \
        f"word count mismatch: corpus={n} en={len(en)} ru={len(ru)}"

    # --- attach glosses ----------------------------------------------------
    # The English gloss is shown verbatim (CC BY-NC-ND: display only, no edits).
    # The Russian gloss from data-quran is LOW QUALITY (translated via English,
    # no cases, no settled Quranic terminology) — it is kept ONLY as a hidden
    # reference field "ru_ref" for cross-checking, never shown as "our" Russian.
    # Our real Russian gloss ("ru") is a SEPARATE later pipeline (Step 4) and is
    # intentionally left out here — "ru" and "ru_ref" must never be mixed.
    # data-quran marks gaps with "[[MISSING]]"; drop those so nothing leaks.
    def clean(v):
        return "" if v == "[[MISSING]]" else v
    # Step 4: our own Russian word-by-word gloss (hand-translated from the
    # English gloss, cross-checked against Kuliev for case/wording). Lives in
    # data/wbw/ru_gloss.json as {"s:a:w": "<ru>"} so it survives rebuilds.
    ru_gloss = {}
    rg_path = os.path.join(OUT_DIR, "ru_gloss.json")
    if os.path.exists(rg_path):
        with open(rg_path, encoding="utf-8") as f:
            ru_gloss = json.load(f)

    words = {}
    for i, key in enumerate(order, start=1):
        rec = {"en": clean(en[str(i)])}
        ru_ref = clean(ru[str(i)])
        if ru_ref:
            rec["ru_ref"] = ru_ref
        if ru_gloss.get(key):
            rec["ru"] = ru_gloss[key]
        words[key] = rec

    # --- split per surah (like data/qpc/v1/surah/<s>.json) -----------------
    # Single-file morph.json was ~12.6 MB; per-surah chunks load lazily so a
    # phone only fetches the surah being read. Shape: {ayah:{word:value}}.
    words_by_surah, morph_by_surah = {}, {}
    for key in order:
        s, a, w = key.split(":")
        words_by_surah.setdefault(s, {}).setdefault(a, {})[w] = words[key]
        morph_by_surah.setdefault(s, {}).setdefault(a, {})[w] = morph[key]

    words_dir = os.path.join(OUT_DIR, "words")
    morph_dir = os.path.join(OUT_DIR, "morph")
    os.makedirs(words_dir, exist_ok=True)
    os.makedirs(morph_dir, exist_ok=True)
    for s in words_by_surah:
        with open(os.path.join(words_dir, f"{s}.json"), "w", encoding="utf-8") as f:
            json.dump(words_by_surah[s], f, ensure_ascii=False, separators=(",", ":"))
        with open(os.path.join(morph_dir, f"{s}.json"), "w", encoding="utf-8") as f:
            json.dump(morph_by_surah[s], f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(OUT_DIR, "ATTRIBUTION.txt"), "w", encoding="utf-8") as f:
        f.write(ATTRIBUTION)

    # --- verification ------------------------------------------------------
    assert len(words) == len(morph) == 77429
    print(f"wrote {len(words_by_surah)} surah chunks to data/wbw/words/ and data/wbw/morph/")
    print(f"total words: {len(words)}  (== {len(morph)} == 77429)")
    print("\nsample 2:4:10")
    print("  en:    ", words["2:4:10"]["en"])
    print("  ru_ref:", words["2:4:10"].get("ru_ref", ""))
    for seg in morph["2:4:10"]:
        print("  seg:", json.dumps(seg, ensure_ascii=False))

if __name__ == "__main__":
    main()
