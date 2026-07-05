#!/usr/bin/env python3
"""Build per-sura tajweed span data for TEXT rendering (phase B of tajweed).

Источник разметки — cpfair/quran-tajweed (MIT): 60k спанов правил таджвида
с посимвольными индексами по снапшоту текста Танзиль-усмани 2017 г. Наш
_arabic.json — современный Танзиль, который с тех пор слегка сменил состав
комбинирующих знаков (напр. ۟ U+06DF), поэтому индексы переносятся на наш
текст ПОСИМВОЛЬНЫМ выравниванием (difflib) для каждого аята.

Вход (кэшируется в data/_sources/tajweed/, gitignored):
  cpfair.json        — output/tajweed.hafs.uthmani-pause-sajdah.json
  quran-uthmani.txt  — референс-текст cpfair (снапшот Танзиля от 2017-04-06)

Выход: data/tajweed/<sura>.json = {ayah: [[start, end, ruleIdx], ...]}
       data/tajweed/meta.json   = {"rules": [имена правил по индексам]}
Спаны отсортированы, пересечения обрезаны (правый спан начинается не раньше
конца левого), индексы — в кодпоинтах нашего _arabic.json (0-базные).
Запуск: python3 build_tajweed.py  (идемпотентен)
"""
import difflib, json, os, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "data", "_sources", "tajweed")
OUT = os.path.join(BASE, "data", "tajweed")
ARABIC = os.path.join(BASE, "data", "tafsirs", "_arabic.json")
CPFAIR_URL = "https://raw.githubusercontent.com/cpfair/quran-tajweed/master/output/tajweed.hafs.uthmani-pause-sajdah.json"
TEXT_URL = "https://github.com/cpfair/quran-tajweed/files/7281388/quran-uthmani.txt"

RULES = ["ghunnah", "hamzat_wasl", "idghaam_ghunnah", "idghaam_mutajanisayn",
         "idghaam_mutaqaribayn", "idghaam_no_ghunnah", "idghaam_shafawi",
         "ikhfa", "ikhfa_shafawi", "iqlab", "lam_shamsiyyah",
         "madd_2", "madd_246", "madd_6", "madd_munfasil", "madd_muttasil",
         "qalqalah", "silent"]

def fetch(url, name):
    path = os.path.join(SRC, name)
    if not os.path.exists(path) or os.path.getsize(path) < 1000:
        print(f"скачиваю {name}…", flush=True)
        req = urllib.request.Request(url, headers={"User-Agent": "tafsir-app-build"})
        with urllib.request.urlopen(req, timeout=120) as r, open(path, "wb") as f:
            f.write(r.read())
    return path

def offset_map(src, dst):
    """Отображение индексов src→dst по difflib; None вне общих блоков."""
    m = [None] * (len(src) + 1)
    sm = difflib.SequenceMatcher(None, src, dst, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1 + 1):
                m[i1 + k] = j1 + k
        else:  # replace/delete: прижать к началу целевого блока, конец — к его концу
            for k in range(i1, i2 + 1):
                if m[k] is None:
                    m[k] = j1 if k < i2 else j2
    if m[len(src)] is None:
        m[len(src)] = len(dst)
    return m

def main():
    os.makedirs(SRC, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    cp = json.load(open(fetch(CPFAIR_URL, "cpfair.json"), encoding="utf-8"))
    ref = {}
    for line in open(fetch(TEXT_URL, "quran-uthmani.txt"), encoding="utf-8"):
        line = line.strip("\n")
        if not line or line.startswith("#"):
            continue
        parts = line.split("|", 2)
        if len(parts) == 3 and parts[0].isdigit():
            ref[(int(parts[0]), int(parts[1]))] = parts[2]
    arabic = json.load(open(ARABIC, encoding="utf-8"))
    print(f"референс: {len(ref)} аятов; спанов на входе: "
          f"{sum(len(e['annotations']) for e in cp)}")

    QLQ = set("قطبجد")
    out = {}          # sura -> {ayah: [[s,e,ri],...]}
    identical = moved = dropped = sem_bad = 0
    for e in cp:
        s, a = e["surah"], e["ayah"]
        rt = ref.get((s, a))
        ours = arabic[str(s)][str(a)]
        if rt is None:
            raise SystemExit(f"{s}:{a}: нет в референс-тексте")
        if rt == ours:
            mp = None
            identical += 1
        else:
            mp = offset_map(rt, ours)
            moved += 1
        spans = []
        for an in sorted(e["annotations"], key=lambda x: (x["start"], x["end"])):
            st, en = an["start"], an["end"]
            if mp is not None:
                st, en = mp[st], mp[en]
            if en <= st:
                dropped += 1
                continue
            # обрезать пересечение с предыдущим спаном (их ~40 на весь Коран)
            if spans and st < spans[-1][1]:
                st = spans[-1][1]
                if en <= st:
                    dropped += 1
                    continue
            seg = ours[st:en]
            r = an["rule"]
            if ((r == "hamzat_wasl" and "ٱ" not in seg) or
                (r == "lam_shamsiyyah" and "ل" not in seg) or
                (r == "qalqalah" and not (set(seg) & QLQ))):
                sem_bad += 1
            spans.append([st, en, RULES.index(r)])
        if spans:
            out.setdefault(s, {})[str(a)] = spans
    total = sum(len(v) for su in out.values() for v in su.values())
    print(f"аятов 1-в-1: {identical}, с переносом индексов: {moved}; "
          f"спанов на выходе: {total}, отброшено: {dropped}, "
          f"семантических несоответствий: {sem_bad}")

    for s, ayat in out.items():
        with open(os.path.join(OUT, f"{s}.json"), "w", encoding="utf-8") as f:
            json.dump(ayat, f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8") as f:
        json.dump({"rules": RULES}, f, separators=(",", ":"))
    print(f"готово: {len(out)} сур -> data/tajweed/", flush=True)

if __name__ == "__main__":
    main()
