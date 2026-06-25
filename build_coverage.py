#!/usr/bin/env python3
"""
Строит ИНДЕКС ПОКРЫТИЯ: какие аяты покрывает каждый источник.

Результат — data/coverage.json:
    {
      "total": 6236,
      "names": { "<id>": "Имя источника", ... },
      "sources": {
        "<id>": {
          "n": <всего покрытых аятов>,
          "kind": "tafsir|translation",
          "s": { "<сура>": [a1,a2, a3,a4, ...] }   # ПАРЫ = включительные диапазоны
        }, ...
      }
    }

Единица покрытия — аят. Диапазон хранится парами (началоN,конецN) — для блочных
тафсиров все аяты диапазона физически присутствуют как ключи (текст на первом,
на остальных — компактная отсылка «см. аят N»), поэтому отдельной разметки
диапазонов не нужно: предикат «реальный аят» покрывает их автоматически.

Предикат «реальный аят» СИНХРОНИЗИРОВАН с compute_fill.py:
  пропускаем «суру 0» (мукаддима) и ключ «0» внутри суры (вступление к суре);
  реальный = непустой текст, не начинающийся с «※» (маркер отсутствующего аята).

В индекс попадают только переводы и тафсиры (kind translation|tafsir).
Тексты Корана (kind quran) и сканы (kind image) исключены: счётчик «Тафсиров: N»
считает именно толкования/переводы, а не сам аят и не картинку.

Запуск:  python3 build_coverage.py
"""
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
TAF = os.path.join(ROOT, "data", "tafsirs")
TOTAL = 6236  # аятов в стандартной нумерации Корана


def is_real(txt):
    t = (txt or "").strip()
    return bool(t) and not t.startswith("※")


def covered_ranges(tid):
    """{сура: [пары границ диапазонов]} по реальным аятам источника."""
    path = os.path.join(TAF, tid + ".json")
    if not os.path.isfile(path):
        return {}, 0
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out = {}
    total = 0
    for sk, s in data.items():
        if sk == "0":                       # мукаддима книги
            continue
        ayahs = sorted(
            int(ak) for ak, txt in s.items()
            if ak != "0" and is_real(txt)    # ключ "0" = вступление к суре
        )
        if not ayahs:
            continue
        total += len(ayahs)
        # сжать подряд идущие в диапазоны (плоские пары)
        pairs = []
        start = prev = ayahs[0]
        for a in ayahs[1:]:
            if a == prev + 1:
                prev = a
            else:
                pairs += [start, prev]
                start = prev = a
        pairs += [start, prev]
        out[sk] = pairs
    return out, total


def main():
    cfg = json.load(open(os.path.join(ROOT, "data", "config.json"), encoding="utf-8"))
    sources = {}
    names = {}
    for t in cfg["tafsirs"]:
        if t.get("kind") not in ("tafsir", "translation"):
            continue
        ranges, n = covered_ranges(t["id"])
        if n == 0:
            continue                          # демо-заглушки (только ※) не покрывают ничего
        sources[t["id"]] = {"n": n, "kind": t["kind"], "s": ranges}
        names[t["id"]] = t.get("name", t["id"])

    out = {"total": TOTAL, "names": names, "sources": sources}
    dest = os.path.join(ROOT, "data", "coverage.json")
    json.dump(out, open(dest, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

    # offline-зеркало (как config.js): window.TL_COVERAGE = {...};
    dest_js = os.path.join(ROOT, "data", "coverage.js")
    open(dest_js, "w", encoding="utf-8").write(
        "window.TL_COVERAGE=" + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n")

    size = os.path.getsize(dest)
    for tid in sorted(sources, key=lambda k: -sources[k]["n"]):
        print(f"  {tid:16} {sources[tid]['n']:5} аятов  ({sources[tid]['n']*100//TOTAL}%)")
    print(f"Готово: {len(sources)} источников в индексе, {size//1024} КБ.")


if __name__ == "__main__":
    main()
