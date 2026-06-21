#!/usr/bin/env python3
"""
Строит предсобранный инвертированный индекс для поиска.

Для каждого тафсира data/tafsirs/<id>.json создаёт:
  data/index/<id>.json = { "<слово>": "s:a s:a ...", ... }

где слово — нормализованный токен (нижний регистр, арабская нормализация,
без огласовок), а значение — список ссылок "сура:аят", где это слово встречается.

Поиск в приложении грузит этот индекс (меньше полного текста), находит аяты
по словам запроса (AND + подстрока по словам индекса), и подтягивает текст
только для найденных аятов из чанков. Полные тексты тафсиров при поиске больше
не качаются.

Использование:
  python3 build_index.py            # все тафсиры
  python3 build_index.py kuliev     # только указанные
"""

import json, sys, os, re

ROOT = os.path.dirname(os.path.abspath(__file__))
TAFSIRS_DIR = os.path.join(ROOT, "data", "tafsirs")
INDEX_DIR = os.path.join(ROOT, "data", "index")

# Должно совпадать с normalizeSearch() в index.html (явные \u-коды, как в JS-регэкспах)
AR_DIACRITICS = re.compile("[ؐ-ًؚ-ٰٟۖ-ۜ۟-۪ۨ-ۭ࣓-ࣿ]")
AR_TATWEEL = re.compile("ـ")
ALIF = re.compile("[أإآٱ]")
WORD = re.compile(r"\w+", re.UNICODE)


def normalize(s):
    s = AR_DIACRITICS.sub("", s)
    s = AR_TATWEEL.sub("", s)
    s = ALIF.sub("ا", s)
    s = s.replace("ة", "ه")
    s = s.replace("ى", "ي")
    return s.lower()


def build_one(tid):
    src = os.path.join(TAFSIRS_DIR, tid + ".json")
    if not os.path.isfile(src):
        print(f"  x нет файла {src}")
        return False
    with open(src, encoding="utf-8") as f:
        data = json.load(f)

    inv = {}  # word -> list of "s:a"
    for s in data:
        for a, text in data[s].items():
            ref = f"{s}:{a}"
            for w in set(WORD.findall(normalize(text))):
                if len(w) >= 2:
                    inv.setdefault(w, []).append(ref)

    os.makedirs(INDEX_DIR, exist_ok=True)
    out = {w: " ".join(refs) for w, refs in inv.items()}
    out_path = os.path.join(INDEX_DIR, tid + ".json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = os.path.getsize(out_path) / 1024
    print(f"  ok {tid}: {len(inv)} слов -> {out_path} ({size_kb:.0f} КБ)")
    return True


def main():
    ids = sys.argv[1:]
    if not ids:
        ids = sorted(
            f[:-5] for f in os.listdir(TAFSIRS_DIR)
            if f.endswith(".json")
        )
    print(f"Строю индекс для {len(ids)} тафсир(ов)...")
    ok = 0
    for tid in ids:
        if build_one(tid):
            ok += 1
    print(f"Готово: {ok}/{len(ids)}")


if __name__ == "__main__":
    main()
