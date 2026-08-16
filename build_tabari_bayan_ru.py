#!/usr/bin/env python3
"""
«Ат-Табари: толкования и предпочтения» по-русски (tabari_tarjih_ru) — сборка монолита.

Что это: перевод НЕ всего «Джами' аль-баяна», а того, что говорит сам Табари, —
его перифразы аята и его тарджиха (сырьё готовит build_tabari_skeleton.py).
Из этого источника затем выводится наш собственный перевод Корана.

ВНИМАНИЕ к именам: `tabari_ru` ЗАРЕЗЕРВИРОВАН за переводом ПОЛНОГО тафсира
(отдельная будущая работа) — этот источник называется `tabari_tarjih_ru`, а его
арабский спутник (тот же извлечённый текст, но в оригинале) — `tabari_tarjih_ar`.

Конвейер:
  build_tabari_ar.py        → data/_sources/tabari_ar/<s>/<a>.json   (кеш арабского)
  build_tabari_skeleton.py  → data/_sources/tabari_tarjih_ru/skeleton/<s>.json
  ПЕРЕВОД (агенты/руками)   → data/translation/tabari_tarjih_ru/<s>.json = {"<ayah>": "md"}
  build_tabari_tarjih_ru.py        → data/tafsirs/tabari_tarjih_ru.json

Переводы лежат ПО СУРАМ в data/translation/ — НЕ в data/_sources/ (тот gitignored):
это наш собственный текст, и его история правок обязана быть в git. Монолит
data/tafsirs/tabari_tarjih_ru.json — производный, собирается отсюда.

Оформление (согласовано с мейнтейнером):
  **«фрагмент аята»** — перифраза Табари;
  *Предпочтение ат-Табари:* … — его тарджих;
  *Итог ат-Табари:* … — его итоговая формула «فتأويل الكلام إذًا…»;
  сноска [^1] — если тарджих Табари относится к чтению, отличному от Хафса
  (в тексте перевода всегда следуем Хафсу — он же набран в мусхафе).

Использование:
  python3 build_tabari_tarjih_ru.py            # ru/*.json → монолит
  python3 build_tabari_tarjih_ru.py --status   # что переведено, а что нет
Дальше: split.py tabari_tarjih_ru && build_index.py tabari_tarjih_ru && compute_fill.py
        && build_coverage.py && sync_config.py
"""
import os, sys, json, glob

ROOT = os.path.dirname(os.path.abspath(__file__))
ARABIC_DIR = os.path.join(ROOT, "data", "tafsirs", "_arabic")
RU = os.path.join(ROOT, "data", "translation", "tabari_tarjih_ru")
OUT = os.path.join(ROOT, "data", "tafsirs", "tabari_tarjih_ru.json")


def ayah_counts():
    c = {}
    for su in range(1, 115):
        with open(os.path.join(ARABIC_DIR, f"{su}.json"), encoding="utf-8") as f:
            c[su] = max(int(k) for k in json.load(f))
    return c


def load():
    out, bad = {}, []
    for path in sorted(glob.glob(os.path.join(RU, "*.json")),
                       key=lambda p: int(os.path.basename(p)[:-5])):
        su = os.path.basename(path)[:-5]
        try:
            chunk = json.load(open(path, encoding="utf-8"))
        except Exception as e:
            bad.append(f"{su}.json: {e}")
            continue
        clean = {a: t.strip() for a, t in chunk.items() if isinstance(t, str) and t.strip()}
        if clean:
            out[su] = clean
    return out, bad


def status(out):
    counts = ayah_counts()
    done = sum(len(v) for v in out.values())
    total = sum(counts.values())
    print(f"переведено {done} из {total} аятов ({100 * done / total:.1f}%), сур начато: {len(out)}")
    for su in sorted(out, key=int):
        n, all_ = len(out[su]), counts[int(su)]
        mark = "✓" if n == all_ else " "
        print(f"  {mark} сура {su:>3}: {n}/{all_}")


def main():
    out, bad = load()
    for b in bad:
        print(f"  ⚠ {b}")
    if "--status" in sys.argv[1:]:
        status(out)
        return
    if not out:
        print("нет переводов в data/translation/tabari_tarjih_ru/ — нечего собирать")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    ayat = sum(len(v) for v in out.values())
    print(f"  ✓ монолит: {len(out)} сур, {ayat} аятов, "
          f"{os.path.getsize(OUT) / 1e6:.2f} МБ → {OUT}")
    print("Дальше: python3 split.py tabari_tarjih_ru && python3 build_index.py tabari_tarjih_ru "
          "&& python3 compute_fill.py && python3 build_coverage.py && python3 sync_config.py")


if __name__ == "__main__":
    main()
