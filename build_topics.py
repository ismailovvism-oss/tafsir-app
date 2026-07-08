#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_topics.py — сборка данных «Тематического указателя» (фихрист).

Источник: онтология тем Quranic Arabic Corpus (corpus.quran.com), извлечённая
в SQLite (data/_sources/topics/topics.db, GNU GPL, © Kais Dukes). Мы берём
ТЕМАТИЧЕСКУЮ иерархию (флаг thematic=1) — 3 корня: Doctrine / Stories / The
Unseen — как готовый указатель «тема → аяты».

Выход (data/topics/):
  tree.json    — вложенное дерево {id,name,ar,n,children}. name — русское, если
                 есть перевод в names_ru.json, иначе английское (из names.json).
  verses.json  — {topic_id: ["2:3", ...]} только для узлов, у которых есть аяты.
  byAyah.json  — обратная карта {"2:3": [topic_id, ...]} для бейджей у аята.
  meta.json    — счётчики + атрибуция.

Промежуточное (data/_sources/topics/):
  names.json   — {id: {"en":..., "ar":...}} — ПЛОСКИЙ список для перевода.

Перевод названий: заполняется в data/topics/names_ru.json = {id: "рус. имя"}
(отдельным шагом, мультиагент). Скрипт применяет его, если файл есть.

Идемпотентно. Запуск: python3 build_topics.py
"""
import json, os, sqlite3, re

ROOT = os.path.dirname(os.path.abspath(__file__))
DB   = os.path.join(ROOT, "data", "_sources", "topics", "topics.db")
OUT  = os.path.join(ROOT, "data", "topics")
SRC  = os.path.join(ROOT, "data", "_sources", "topics")
RU   = os.path.join(OUT, "names_ru.json")

THEMATIC_ROOTS = [1882, 1883, 1884]  # Doctrine / Stories / The Unseen
AYAH_RE = re.compile(r"^\d+:\d+$")

def clean_name(s):
    s = (s or "").strip()
    # мелкие опечатки оригинала
    return {"Doctraine": "Doctrine"}.get(s, s)

def parse_ayahs(raw):
    if not raw:
        return []
    out, seen = [], set()
    for tok in raw.split(","):
        t = tok.strip()
        if AYAH_RE.match(t) and t not in seen:
            seen.add(t); out.append(t)
    return out

def main():
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
    rows = {r["topic_id"]: r for r in con.execute(
        "SELECT topic_id,name,arabic_name,thematic,thematic_parent_id,ayahs "
        "FROM topics WHERE thematic=1")}
    con.close()

    # дети по тематическому родителю
    kids = {}
    for tid, r in rows.items():
        p = r["thematic_parent_id"] or 0
        kids.setdefault(p, []).append(tid)

    ru = {}
    if os.path.exists(RU):
        ru = {int(k): v for k, v in json.load(open(RU, encoding="utf-8")).items()}

    verses, by_ayah, names = {}, {}, {}

    def node(tid):
        r = rows[tid]
        en = clean_name(r["name"])
        ar = (r["arabic_name"] or "").strip()
        names[tid] = {"en": en, "ar": ar}
        ay = parse_ayahs(r["ayahs"])
        if ay:
            verses[str(tid)] = ay
            for a in ay:
                by_ayah.setdefault(a, []).append(tid)
        ch = [node(c) for c in sorted(kids.get(tid, []),
                                      key=lambda c: clean_name(rows[c]["name"]).lower())]
        total = len(ay) + sum(c["t"] for c in ch)   # аяты во всём поддереве
        d = {"id": tid, "name": ru.get(tid, en), "ar": ar, "n": len(ay), "t": total}
        if ch:
            d["children"] = ch
        return d

    tree = [node(root) for root in THEMATIC_ROOTS]

    os.makedirs(OUT, exist_ok=True)
    dump(os.path.join(OUT, "tree.json"), tree)
    dump(os.path.join(OUT, "verses.json"), verses)
    dump(os.path.join(OUT, "byAyah.json"), by_ayah)
    dump(os.path.join(SRC, "names.json"),
         {str(k): v for k, v in sorted(names.items())})
    meta = {
        "source": "Quranic Arabic Corpus — Topic Index (corpus.quran.com)",
        "author": "Kais Dukes",
        "license": "GNU GPL",
        "roots": len(tree),
        "topics": len(names),
        "topicsWithAyahs": len(verses),
        "translated": len(ru),
    }
    dump(os.path.join(OUT, "meta.json"), meta)

    tr = f"{len(ru)}/{len(names)}" if ru else "0 (названия ещё англ.)"
    print(f"тем: {len(names)}  с аятами: {len(verses)}  "
          f"аятов-ключей: {len(by_ayah)}  перевод: {tr}")

def dump(path, obj):
    json.dump(obj, open(path, "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))

if __name__ == "__main__":
    main()
