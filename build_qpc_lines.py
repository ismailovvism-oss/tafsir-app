#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_qpc_lines.py — разметка СТРОК страницы мусхафа: какие слова каких аятов
лежат на каждой строке.

Зачем. Границы страниц в проекте были и раньше (qpc/meta.json → pageStart), а
вот строк — нет. Без них не собрать методы, которые ходят по строкам: «Снизу
вверх» (строки страницы с последней к первой) и «Полстраницы».

Откуда берётся. Прямой связи «строка → аят» в данных QPC НЕТ: второе число у
глифа — это номер СТРАНИЦЫ, а не аята, а `starts` в файле страницы перечисляет
начала СУР. Зато обе стороны описаны одними и теми же глифами:

  data/qpc/v1/page/N.json   → {"lines": {"3": [[глиф, стр], …], …}}   строка → глифы
  data/qpc/v1/surah/S.json  → {"12": {"w": [[глиф, стр], …], "e": …}} аят → слова

Склеиваем глифы страницы в одну строку, склеиваем глифы её аятов в другую — они
СОВПАДАЮТ посимвольно (проверено на всех 604 страницах). Дальше пересекаем
диапазоны символов: где лежит строка и где лежит слово — там и связь.

Нумерация слов совпадает с той, по которой их считает приложение (текст аята из
_arabic.json, разбитый по пробелам, без знаков вакфа и без приклеенной басмалы):
сверено по всем 6236 аятам, расходятся ЧЕТЫРЕ — 2:181, 8:6, 13:37, 37:130, где
QPC склеивает два слова в одно начертание. Такие аяты на строки не режем: аят
целиком приписывается строке, на которой начался, и помечается в meta.approx.

Выход: data/qpc_lines.json
  {"meta": {…}, "pages": {"<стр>": {"<строка>": [[сура, аят, от, до], …]}}}
  «от»/«до» — индексы слов внутри аята, с нуля, включительно.

Идемпотентно. Запуск: python3 build_qpc_lines.py
"""
import json, os, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.join(ROOT, "data", "qpc", "v1")
ARAB = os.path.join(ROOT, "data", "tafsirs", "_arabic.json")
OUT  = os.path.join(ROOT, "data", "qpc_lines.json")

# Аяты, где QPC склеивает два слова текста в одно начертание: нумерация слов
# после склейки разъезжается, поэтому режем такие аяты только целиком.
GLUED = {(2, 181), (8, 6), (13, 37), (37, 130)}


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def main():
    if not os.path.isdir(PACK):
        sys.exit("нет каталога %s — данные мусхафа не разложены" % PACK)
    meta = load(os.path.join(PACK, "meta.json"))
    pages = meta["pages"]
    pstart = meta["pageStart"]

    sur_cache = {}
    def surah(s):
        if s not in sur_cache:
            sur_cache[s] = load(os.path.join(PACK, "surah", "%d.json" % s))
        return sur_cache[s]

    nayah = {s: len(surah(s)) for s in range(1, 115)}

    def ayahs_of_page(p):
        """Аяты страницы: от её первого до аята перед первым аятом следующей."""
        st = pstart[str(p)]
        nx = pstart.get(str(p + 1))
        out, s, a = [], st["surah"], st["ayah"]
        while s <= 114:
            if nx and (s, a) == (nx["surah"], nx["ayah"]):
                break
            out.append((s, a))
            if a < nayah[s]:
                a += 1
            else:
                s, a = s + 1, 1
        return out

    out_pages = {}
    mismatch = []
    for p in range(1, pages + 1):
        pg = load(os.path.join(PACK, "page", "%d.json" % p))
        lines = pg["lines"]
        # Символьные границы строк в общем потоке глифов страницы.
        span, pos = [], 0
        for ln in sorted(lines, key=int):
            txt = "".join(g[0] for g in lines[ln])
            span.append((int(ln), pos, pos + len(txt)))
            pos += len(txt)
        page_glyphs = "".join("".join(g[0] for g in lines[ln]) for ln in sorted(lines, key=int))

        # Символьные границы СЛОВ в потоке глифов аятов страницы.
        words, apos, ayah_txt = [], 0, []
        for (s, a) in ayahs_of_page(p):
            v = surah(s)[str(a)]
            for i, w in enumerate(v["w"]):
                g = w[0]
                words.append((s, a, i, apos, apos + len(g)))
                ayah_txt.append(g)
                apos += len(g)
            e = v.get("e")
            if e:
                ayah_txt.append(e[0])
                apos += len(e[0])
        if "".join(ayah_txt) != page_glyphs:
            mismatch.append(p)
            continue

        per_line = {}
        for (ln, lo, hi) in span:
            acc = {}
            for (s, a, i, w0, w1) in words:
                if w1 <= lo or w0 >= hi:          # слово целиком вне строки
                    continue
                acc.setdefault((s, a), []).append(i)
            if not acc:
                continue                          # строка из одних разделителей аятов
            per_line[str(ln)] = [[s, a, min(idx), max(idx)] for (s, a), idx in acc.items()]
        # Склеенные аяты не режем: приписываем целиком строке, где начались.
        for (s, a) in GLUED:
            seen = [ln for ln, items in per_line.items() if any(x[0] == s and x[1] == a for x in items)]
            if len(seen) > 1:
                first = min(seen, key=int)
                n = len(surah(s)[str(a)]["w"]) - 1
                for ln in seen:
                    per_line[ln] = [x for x in per_line[ln] if not (x[0] == s and x[1] == a)]
                per_line[first].append([s, a, 0, n])
                per_line[first].sort(key=lambda x: (x[0], x[1], x[2]))
        out_pages[str(p)] = per_line

    data = {
        "meta": {
            "description": "Разметка строк мусхафа: какие слова каких аятов лежат на строке.",
            "source": "data/qpc/v1 (page/*.json + surah/*.json), сведено сопоставлением глифов",
            "pack": "v1",
            "pages": pages,
            "word_index": "индексы слов внутри аята, с нуля, включительно; нумерация как в _arabic.json без вакфа и без приклеенной басмалы",
            "approx": ["%d:%d" % t for t in sorted(GLUED)],
            "approx_why": "QPC склеивает в них два слова текста в одно начертание — такие аяты приписаны целиком строке, где начались",
        },
        "pages": out_pages,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    nl = sum(len(v) for v in out_pages.values())
    print("страниц: %d, строк: %d" % (len(out_pages), nl))
    if mismatch:
        print("НЕ СОШЛИСЬ глифы на страницах: %s" % mismatch[:10])
    print("→ %s (%.1f КБ)" % (OUT, os.path.getsize(OUT) / 1024))


if __name__ == "__main__":
    main()
