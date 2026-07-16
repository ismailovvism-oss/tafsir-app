#!/usr/bin/env python3
"""Build the root concordance index for the tafsir app.

Конкорданс = «тап по слову → корень → все остальные слова Корана с этим корнем».
Корень у каждого слова УЖЕ есть в data/wbw/morph/<s>.json (сегмент-основа, поле
"root"), но разложен по 114 файлам-сурам: чтобы собрать все вхождения корня,
телефону пришлось бы скачать морфологию всего Корана (~7 МБ). Поэтому обратная
карта корень→адреса строится здесь, на сборке, одним лёгким файлом:

  data/wbw/roots.json  ->  {"<корень>": {"n": <всего вхождений>,
                                         "g": [<русские глоссы>, ...],
                                         "f": [[<форма слова>, "<адреса>"], ...]}}

  "n" — сколько раз корень встречается в Коране (сумма по формам).
  "g" — до GLOSS_MAX самых частых русских глоссов слов этого корня. Список из
        1651 голого арабского корня русскоязычному читателю нечитаем, поэтому
        корень подписывается смыслом («رحم · Милостивого · Милосердного»), и по
        этим же словам корень ищется в указателе — набирать арабский с телефона
        мало кто станет. Глоссы берутся из data/wbw/words/<s>.json (поле "ru",
        покрытие 100%); это ЧЕРНОВОЙ пословный глосс, не перевод аята.
  "f" — формы слова с этим корнем, ОТ ЧАСТОЙ К РЕДКОЙ (так список в карточке
        читается сверху вниз: сначала то, что человек уже видел). Форма — склейка
        сегментов слова (بِ + سْمِ = بِسْمِ), т.е. слово ровно как в тексте.
  Адреса — "сура:аят:слово" через пробел, в порядке мусхафа (как в data/index/,
        инвертированном индексе поиска: строка вместо массива — заметно короче).

Позиция слова в адресе хранится, хотя переход сейчас ведёт на аят: она нужна,
чтобы потом подсветить конкретное слово (режим Слова/слой) без пересборки.

ИСТОЧНИК — только собственные данные (data/wbw/morph, сборка build_morph.py из
Quranic Arabic Corpus, © Kais Dukes, GPL, атрибуция — data/wbw/ATTRIBUTION.txt).
Сеть не нужна. Скрипт идемпотентен: читает морфологию, пишет один файл.

Слова без корня (частицы, местоимения, союзы — ~35% словоупотреблений) в индекс
не попадают: у них корня нет и в самом корпусе, показывать в карточке нечего.

Запуск:  python3 build_concordance.py
"""
import json
import os
import glob
import collections

ROOT = os.path.dirname(os.path.abspath(__file__))
MORPH_DIR = os.path.join(ROOT, "data", "wbw", "morph")
WORDS_DIR = os.path.join(ROOT, "data", "wbw", "words")
OUT_PATH = os.path.join(ROOT, "data", "wbw", "roots.json")
GLOSS_MAX = 4  # сколько русских глоссов подписывать корню (подсказка смысла + поиск)


def word_form(segs):
    """Слово целиком — склейка арабских сегментов (префиксы+основа+суффиксы)."""
    return "".join(s.get("ar", "") for s in segs)


def word_root(segs):
    """Корень слова — из сегмента-основы (у аффиксов корня нет). None, если корня нет."""
    for s in segs:
        if s.get("root"):
            return s["root"]
    return None


def loc_key(loc):
    """Сортировка адресов в порядке мусхафа: 2:37:11 идёт после 2:5:4, а не по строке."""
    return tuple(int(x) for x in loc.split(":"))


def top_glosses(counter):
    """До GLOSS_MAX самых частых глоссов корня, без падежных повторов.

    Глоссы — словоформы («Милостивого», «Милостивый»), и без свёртки список
    подписи выродится в один пересклоняемый вариант. Схлопываем по первым
    OVERLAP буквам, оставляя самый частый вариант группы, — грубо, но именно
    для подписи и поиска по подстроке этого достаточно.
    """
    if not counter:
        return []
    OVERLAP = 5
    seen, out = set(), []
    for word, _ in counter.most_common():
        # у непереводимых слов (частицы-связки) глосс — прочерк; в подписи он пуст
        if not any(ch.isalpha() for ch in word):
            continue
        key = word.lower()[:OVERLAP]
        if key in seen:
            continue
        seen.add(key)
        out.append(word)
        if len(out) >= GLOSS_MAX:
            break
    return out


def main():
    files = sorted(glob.glob(os.path.join(MORPH_DIR, "*.json")))
    if not files:
        raise SystemExit(
            "Нет data/wbw/morph/*.json — сперва собери морфологию: python3 build_morph.py"
        )

    # корень -> форма -> [адреса];  корень -> глосс -> сколько раз
    roots = collections.defaultdict(lambda: collections.defaultdict(list))
    glosses = collections.defaultdict(collections.Counter)
    words_total = 0
    for path in files:
        surah = os.path.basename(path)[:-5]
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        gl_path = os.path.join(WORDS_DIR, "%s.json" % surah)
        gl = {}
        if os.path.exists(gl_path):
            with open(gl_path, encoding="utf-8") as f:
                gl = json.load(f)
        for ayah, words in data.items():
            for pos, segs in words.items():
                words_total += 1
                root = word_root(segs)
                if not root:
                    continue
                roots[root][word_form(segs)].append("%s:%s:%s" % (surah, ayah, pos))
                ru = (gl.get(ayah, {}).get(pos, {}) or {}).get("ru")
                if ru:
                    glosses[root][ru.strip()] += 1

    out = {}
    for root, forms in roots.items():
        # формы — по убыванию частоты, внутри формы адреса — по порядку мусхафа
        ordered = sorted(forms.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        out[root] = {
            "n": sum(len(v) for v in forms.values()),
            "g": top_glosses(glosses.get(root)),
            "f": [[form, " ".join(sorted(locs, key=loc_key))] for form, locs in ordered],
        }
    # корни — по убыванию частоты: файл читается человеком сверху, да и diff стабилен
    out = dict(sorted(out.items(), key=lambda kv: (-kv[1]["n"], kv[0])))

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    occ = sum(v["n"] for v in out.values())
    size = os.path.getsize(OUT_PATH)
    print("data/wbw/roots.json:")
    print("  корней:      %d" % len(out))
    print("  вхождений:   %d из %d словоупотреблений (%.1f%% — остальные без корня)"
          % (occ, words_total, 100.0 * occ / words_total))
    print("  форм слова:  %d" % sum(len(v["f"]) for v in out.values()))
    print("  размер:      %.0f КБ" % (size / 1024.0))
    top = list(out.items())[:5]
    print("  частотные:   " + ", ".join("%s (%d)" % (r, v["n"]) for r, v in top))


if __name__ == "__main__":
    main()
