#!/usr/bin/env python3
"""
Чинит дыру в данных kathir_ru: блоки «формата A» (суры 1–8 старой экстракции),
где разбор нескольких аятов лежит в ПЕРВОМ аяте блока с инлайн-маркерами «(N)»,
а ключи остальных аятов блока вовсе отсутствуют (нет ни текста, ни отсылки).

Формат B (новые суры) уже создаёт отсылки «*Толкование к аятам X–Y — см. аят Z.*»
для всех аятов блока. Этот скрипт дозаполняет недостающие аяты формата A такими же
отсылками, чтобы покрытие/счётчик их учитывали и в режиме источника была отсылка
с переходом.

Эвристика (data-driven): для каждого разрыва между соседними ключами lo и hi
(hi>lo+1) берём текст ключа lo и идём вверх k=lo+1, lo+2, … пока «(k)» встречается
в тексте lo (это инлайн-маркер аята: за ним следует перевод этого аята). Найденный
непрерывный участок lo+1..to — это аяты блока; заполняем их отсылкой на lo.
Если «(k)» нет — разрыв настоящий (источник реально пропустил аят), не трогаем.

Идемпотентно: заполняет только ОТСУТСТВУЮЩИЕ ключи.

Запуск:  python3 fix_kathir_blocks.py
Затем:   python3 split.py kathir_ru && python3 build_index.py kathir_ru \
         && python3 compute_fill.py && python3 build_coverage.py
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
MONO = os.path.join(ROOT, "data", "tafsirs", "kathir_ru.json")
DASH, SEP = "–", "—"   # – (диапазон) и — (разделитель) как в формате B


def ref_text(lo, to):
    return f"*Толкование к аятам {lo}{DASH}{to} {SEP} см. аят {lo}.*"


def main():
    data = json.load(open(MONO, encoding="utf-8"))
    added = []
    for sk in sorted(data, key=lambda x: int(x)):
        sd = data[sk]
        keys = sorted(int(k) for k in sd
                      if k != "0" and (sd[k] or "").strip()
                      and not sd[k].strip().startswith("※"))
        for i in range(len(keys) - 1):
            lo, hi = keys[i], keys[i + 1]
            if hi <= lo + 1:
                continue
            txt = sd[str(lo)]
            run = []
            k = lo + 1
            while k < hi and f"({k})" in txt:
                run.append(k)
                k += 1
            if not run:
                continue                       # настоящий пропуск — оставляем дырой
            to = run[-1]
            for a in run:
                sd[str(a)] = ref_text(lo, to)
                added.append(f"{sk}:{a}→блок {lo}{DASH}{to}")

    json.dump(data, open(MONO, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Заполнено блочными отсылками: {len(added)} аятов")
    for a in added:
        print("  " + a)
    if not added:
        print("  (нечего заполнять — данные уже консистентны)")


if __name__ == "__main__":
    main()
