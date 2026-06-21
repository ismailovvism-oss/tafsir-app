#!/usr/bin/env python3
"""
Разрезает монолитные тафсиры data/tafsirs/<id>.json на чанки по сурам:
  data/tafsirs/<id>/<surah>.json   = { "<ayah>": "text", ... }
  data/tafsirs/<id>/index.json     = [список номеров сур, которые есть]

Это даёт ленивую загрузку: приложение качает только нужную суру, а не весь
Коран целиком. Масштабируется на сотни тафсиров.

Использование:
  python3 split.py                # разрезать все *.json в data/tafsirs
  python3 split.py kuliev osmanov # разрезать только указанные id
"""

import json, sys, os

TAFSIRS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "tafsirs")


def split_one(tid):
    src = os.path.join(TAFSIRS_DIR, tid + ".json")
    if not os.path.isfile(src):
        print(f"  ✗ нет файла {src}")
        return False
    with open(src, encoding="utf-8") as f:
        data = json.load(f)

    out_dir = os.path.join(TAFSIRS_DIR, tid)
    os.makedirs(out_dir, exist_ok=True)

    surahs = sorted((int(s) for s in data.keys()))
    for s in surahs:
        chunk = data[str(s)]
        with open(os.path.join(out_dir, f"{s}.json"), "w", encoding="utf-8") as f:
            json.dump(chunk, f, ensure_ascii=False, separators=(",", ":"))

    with open(os.path.join(out_dir, "index.json"), "w", encoding="utf-8") as f:
        json.dump(surahs, f, separators=(",", ":"))

    total_ayat = sum(len(v) for v in data.values())
    print(f"  ✓ {tid}: {len(surahs)} сур, {total_ayat} аятов → {out_dir}/")
    return True


def main():
    ids = sys.argv[1:]
    if not ids:
        ids = sorted(
            f[:-5] for f in os.listdir(TAFSIRS_DIR)
            if f.endswith(".json") and not f.startswith("_index")
        )
    print(f"Разрезаю {len(ids)} тафсир(ов)...")
    ok = 0
    for tid in ids:
        if split_one(tid):
            ok += 1
    print(f"Готово: {ok}/{len(ids)}")


if __name__ == "__main__":
    main()
