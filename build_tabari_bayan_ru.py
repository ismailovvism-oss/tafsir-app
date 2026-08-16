#!/usr/bin/env python3
"""
«Ат-Табари: ясное изложение» (tabari_bayan_ru) — сборка монолита.

Что это: НЕ построчный перевод «Джами' аль-баяна» и НЕ машинная выжимка. Тафсир
аята читается ЦЕЛИКОМ (data/tafsirs/tabari_ar/<s>.json — на R2, локальное
зеркало r2-data/tafsirs/tabari_ar/) и излагается по-русски заново: ясно, связно,
без тяжеловесных оборотов и без утраты глубины. Из этого источника затем
выводится наш собственный перевод Корана (`tabari_tarjuma`).

ИСТОРИЯ: до 2026-08-16 источник назывался `tabari_tarjih_ru` («Пересказ
ат-Табари») и собирался из машинного скелета (перифраза + тарджих). Подход
отменён: обрубок терял контекст и читался тяжело. Скелет (`build_tabari_skeleton.py`)
и арабский спутник (`tabari_tarjih_ar`) удалены.

ВНИМАНИЕ к именам: `tabari_ru` ЗАРЕЗЕРВИРОВАН за переводом ПОЛНОГО тафсира
(отдельная будущая работа), `alqasawi` — за авторским переводом мейнтейнера.

Конвейер:
  build_tabari_ar.py         → r2-data/tafsirs/tabari_ar/<s>.json  (полный арабский)
  ИЗЛОЖЕНИЕ (агенты/руками)  → data/translation/tabari_bayan_ru/<s>.json = {"<ayah>": "md"}
  build_tabari_bayan_ru.py   → data/tafsirs/tabari_bayan_ru.json

Изложения лежат ПО СУРАМ в data/translation/ — НЕ в data/_sources/ (тот gitignored):
это наш собственный текст, и его история правок обязана быть в git. Монолит
data/tafsirs/tabari_bayan_ru.json — производный, собирается отсюда.

Правила изложения — в TABARI_BAYAN.md (источник истины по стилю).

Использование:
  python3 build_tabari_bayan_ru.py            # ru/*.json → монолит
  python3 build_tabari_bayan_ru.py --status   # что изложено, а что нет
Дальше: split.py tabari_bayan_ru && build_index.py tabari_bayan_ru && compute_fill.py
        && build_coverage.py && sync_config.py
"""
import os, sys, json, glob

ROOT = os.path.dirname(os.path.abspath(__file__))
ARABIC_DIR = os.path.join(ROOT, "data", "tafsirs", "_arabic")
RU = os.path.join(ROOT, "data", "translation", "tabari_bayan_ru")
OUT = os.path.join(ROOT, "data", "tafsirs", "tabari_bayan_ru.json")


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
    print(f"изложено {done} из {total} аятов ({100 * done / total:.1f}%), сур начато: {len(out)}")
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
        print("нет текстов в data/translation/tabari_bayan_ru/ — нечего собирать")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    ayat = sum(len(v) for v in out.values())
    print(f"  ✓ монолит: {len(out)} сур, {ayat} аятов, "
          f"{os.path.getsize(OUT) / 1e6:.2f} МБ → {OUT}")
    print("Дальше: python3 split.py tabari_bayan_ru && python3 build_index.py tabari_bayan_ru "
          "&& python3 compute_fill.py && python3 build_coverage.py && python3 sync_config.py")


if __name__ == "__main__":
    main()
