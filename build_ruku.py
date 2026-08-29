#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_ruku.py — сборка деления Корана на рукуʿ (смысловые отрезки).

Рукуʿ (ركوع) — значок ع на полях индо-пакистанских мусхафов. В отличие от
джуза, хизба и страницы, границы рукуʿ проведены ПО СМЫСЛУ, а не по объёму:
их задача — дать чтецу остановиться, не разорвав тему. Это единственное
КАНОНИЧЕСКОЕ тематическое деление Корана, у которого есть машиночитаемые
данные; всё остальное (тематические мусхафы, заголовки переводов) существует
только на бумаге либо под несвободной лицензией.

Источник: data/_sources/ruku/quran-data.xml — метаданные проекта Tanzil
(tanzil.net, лицензия CC-BY). В нём <ruku index sura aya> отмечает НАЧАЛО
отрезка; конец выводится как аят перед началом следующего (в пределах суры).

Выход: data/ruku.json
  {
    "meta":   {...атрибуция и счётчики...},
    "rukus":  [[сура, от, до], ...]        # 556 троек в порядке текста
  }
Тройками, а не объектами: файл читается на каждом открытии суры, а сура/от/до
— это всё, что нужно; остальное (номер в суре, длина) выводится на месте.

Русские заголовки к отрезкам — отдельным файлом data/ruku_titles_ru.json
{"<номер рукуʿ>": "заголовок"}; скрипт подмешивает его, если он есть, и не
падает, если нет. Границы — канонические и проверяемые; заголовок — ярлык,
его ошибка видна и правится, поэтому только он и отдаётся на откуп ИИ.

Идемпотентно. Запуск: python3 build_ruku.py
"""
import json, os, re, xml.etree.ElementTree as ET

ROOT   = os.path.dirname(os.path.abspath(__file__))
SRC    = os.path.join(ROOT, "data", "_sources", "ruku", "quran-data.xml")
TITLES = os.path.join(ROOT, "data", "ruku_titles_ru.json")
OUT    = os.path.join(ROOT, "data", "ruku.json")

def main():
    if not os.path.exists(SRC):
        raise SystemExit("нет исходника: " + SRC +
                         "\nскачать: curl -sSL -o '%s' https://tanzil.net/res/text/metadata/quran-data.xml" % SRC)
    root = ET.parse(SRC).getroot()

    # Число аятов в каждой суре — из того же файла, чтобы закрывать последний
    # рукуʿ суры без внешней таблицы.
    ayas = {}
    for s in root.findall("./suras/sura"):
        ayas[int(s.get("index"))] = int(s.get("ayas"))
    if len(ayas) != 114:
        raise SystemExit("ожидалось 114 сур, получено %d" % len(ayas))

    starts = [(int(r.get("sura")), int(r.get("aya")))
              for r in root.findall("./rukus/ruku")]
    if not starts:
        raise SystemExit("в исходнике нет элементов <ruku>")

    rukus = []
    for i, (su, a) in enumerate(starts):
        nxt = starts[i + 1] if i + 1 < len(starts) else None
        # Конец — аят перед следующим началом, но только если оно в ТОЙ ЖЕ суре;
        # иначе рукуʿ дотягивается до конца своей суры.
        to = (nxt[1] - 1) if (nxt and nxt[0] == su) else ayas[su]
        if to < a:
            raise SystemExit("рукуʿ %d: конец (%d) раньше начала (%d) в суре %d" % (i + 1, to, a, su))
        rukus.append([su, a, to])

    # Сверка на полноту: рукуʿ обязаны покрыть каждую суру целиком и без нахлёстов.
    cover = {}
    for su, a, to in rukus:
        cover.setdefault(su, []).append((a, to))
    for su, segs in cover.items():
        segs.sort()
        if segs[0][0] != 1:
            raise SystemExit("сура %d: первый рукуʿ начинается с аята %d" % (su, segs[0][0]))
        if segs[-1][1] != ayas[su]:
            raise SystemExit("сура %d: последний рукуʿ кончается на %d, а аятов %d" % (su, segs[-1][1], ayas[su]))
        for (a1, b1), (a2, _) in zip(segs, segs[1:]):
            if a2 != b1 + 1:
                raise SystemExit("сура %d: разрыв или нахлёст между %d и %d" % (su, b1, a2))
    if len(cover) != 114:
        raise SystemExit("рукуʿ покрывают %d сур из 114" % len(cover))

    titles = {}
    if os.path.exists(TITLES):
        titles = json.load(open(TITLES, encoding="utf-8"))

    lens = [to - a + 1 for _, a, to in rukus]
    data = {
        "meta": {
            "description": "Деление Корана на рукуʿ (ركوع) — смысловые отрезки, значок ع на полях "
                           "индо-пакистанских мусхафов. Границы проведены по смыслу, а не по объёму.",
            "source": "Tanzil.net Quran metadata (quran-data.xml)",
            "license": "CC-BY",
            "count": len(rukus),
            "ayah_count_basis": "куфийский счёт (Хафс), сумма 6236",
            "len_min": min(lens), "len_max": max(lens),
            "len_avg": round(sum(lens) / len(lens), 1),
            "titles_ru": len(titles),
        },
        "rukus": rukus,
    }
    if titles:
        data["titles"] = titles

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    print("рукуʿ: %d" % len(rukus))
    print("длина: от %d до %d аятов, в среднем %.1f" % (min(lens), max(lens), sum(lens) / len(lens)))
    print("покрытие: все 114 сур, без разрывов и нахлёстов")
    print("заголовков по-русски: %d" % len(titles))
    print("→ %s (%.1f КБ)" % (OUT, os.path.getsize(OUT) / 1024))

if __name__ == "__main__":
    main()
