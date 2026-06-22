#!/usr/bin/env python3
"""Build the word-by-word translation + morphology layers for the tafsir app.

Two data layers, both keyed by the SAME word address "surah:ayah:word"
(e.g. "2:4:10"), so a clickable word only needs to carry its address and the
card / gloss are pulled from these files on the fly:

  data/wbw/words.json  -> per word: {"en": <gloss>, "ru": <gloss>}
  data/wbw/morph.json  -> per word: [ {segment}, {segment}, ... ]

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

Word-by-word translation (English & Russian glosses):
  data-quran — https://github.com/hablullah/data-quran
  Collected by the Hablullah team from quran.com / Tanzil / QuranEnc.
  Licensed under CC BY-NC-ND 4.0.

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

    # global index (1-based) -> address, to attach the aligned glosses.
    # data-quran marks gaps (mostly in the Russian set) with "[[MISSING]]";
    # blank them so the UI can fall back to the English gloss.
    def clean(v):
        return "" if v == "[[MISSING]]" else v
    words = {}
    for i, key in enumerate(order, start=1):
        words[key] = {"en": clean(en[str(i)]), "ru": clean(ru[str(i)])}

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "words.json"), "w", encoding="utf-8") as f:
        json.dump(words, f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(OUT_DIR, "morph.json"), "w", encoding="utf-8") as f:
        json.dump(morph, f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(OUT_DIR, "ATTRIBUTION.txt"), "w", encoding="utf-8") as f:
        f.write(ATTRIBUTION)

    # --- verification ------------------------------------------------------
    assert len(words) == len(morph) == 77429
    print(f"wrote data/wbw/words.json  ({len(words)} keys)")
    print(f"wrote data/wbw/morph.json  ({len(morph)} keys)")
    print("\nsample 2:4:10")
    print("  en:", words["2:4:10"]["en"])
    print("  ru:", words["2:4:10"]["ru"])
    for seg in morph["2:4:10"]:
        print("  seg:", json.dumps(seg, ensure_ascii=False))

if __name__ == "__main__":
    main()
