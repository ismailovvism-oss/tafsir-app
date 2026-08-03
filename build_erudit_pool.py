#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_erudit_pool.py — служебные данные модуля «🎓 Эрудит» (упражнение «Аяты»).

Зачем. Упражнение спрашивает «из какой это суры?». Но 169 аятов дословно
повторяются В РАЗНЫХ сурах (муката'ат «حم» в 40–46, «فَبِأَيِّ آلَاءِ رَبِّكُمَا»
и т. п.) — у такого вопроса нет одного честного ответа, и предъявлять его нельзя.
Повторы ВНУТРИ одной суры безобидны: ответ всё равно один.

Определить это можно только глядя на весь Коран сразу, а модуль грузит суры
чанками по требованию — поэтому список считается заранее, здесь.

Результат: data/erudit/pool.json
    {"ambiguous": ["2:1", ...],            # плоский список — для быстрой проверки
     "groups": [["40:1","41:1",...], ...]} # группы одинаковых текстов (для будущего
                                           # задания «в каких сурах стоит الم?»)
Сети не требует, идемпотентен.
"""
import json, os, re, collections

SRC = "data/tafsirs/_arabic.json"
OUT_DIR = "data/erudit"
OUT = os.path.join(OUT_DIR, "pool.json")

# Сравниваем БЕЗ огласовок и с унификацией алифов/йа/та-марбуты: иначе
# «حم» в разных сурах разошлись бы по мелким различиям записи и остались бы
# в пуле как якобы уникальные.
DIAC = re.compile(r"[ً-ْٰٓ-ٕـۖ-ۭ]")


def norm(t: str) -> str:
    t = DIAC.sub("", t)
    t = re.sub(r"[آأإٱ]", "ا", t).replace("ى", "ي").replace("ة", "ه")
    return re.sub(r"\s+", " ", t).strip()


def main():
    with open(SRC, encoding="utf-8") as f:
        quran = json.load(f)

    by_text = collections.defaultdict(list)
    for sura, ayahs in quran.items():
        for ayah, text in ayahs.items():
            by_text[norm(text)].append((int(sura), int(ayah)))

    groups = []
    for keys in by_text.values():
        if len({s for s, _ in keys}) > 1:                 # межсурный повтор
            groups.append([f"{s}:{a}" for s, a in sorted(keys)])
    groups.sort(key=lambda g: (-len(g), g[0]))

    ambiguous = sorted({k for g in groups for k in g},
                       key=lambda k: (int(k.split(":")[0]), int(k.split(":")[1])))

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"ambiguous": ambiguous, "groups": groups}, f,
                  ensure_ascii=False, separators=(",", ":"))

    print(f"групп межсурных повторов: {len(groups)}")
    print(f"аятов исключено из «какая сура»: {len(ambiguous)}")
    print(f"→ {OUT} ({os.path.getsize(OUT)} байт)")


if __name__ == "__main__":
    main()
