#!/usr/bin/env python3
"""
Подстановка арабского текста в порции ИИ-тафсиров (детям/подросткам).

Промт v2: автор ставит в файле порции маркеры `> {{ayah:С:А}}`, арабский текст
НИКОГДА не генерируется — только механически копируется из канонического JSON
(data/tafsirs/_arabic.json). Этот скрипт и есть та «программная запись»:

  > {{ayah:78:1}}   ->   > بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ
                         > عَمَّ يَتَسَآءَلُونَ ﴿١﴾

Правила:
  - номер аята — арабо-индийскими цифрами в скобках ﴿…﴾ (как в готовых порциях);
  - у первого аята суры басмала выносится ОТДЕЛЬНОЙ строкой цитаты
    (в _arabic.json она — префикс текста аята 1; сура 1 — сама басмала, сура 9 — нет);
  - скрипт идемпотентен: маркеров после прогона не остаётся, повторный прогон — no-op;
  - после подстановки предупреждает об арабских символах вне строк-цитат
    (кроме ﷺ и подобных лигатур-символов).

Запуск: python3 subst_ai_ayahs.py [файл.md ...]
Без аргументов — обходит весь вольт (детям + подросткам).
"""
import json
import os
import re
import sys

VAULT = os.path.expanduser("~/obsid/qaadiy/Ислам/Коран/Тафсир/ИИ")
ARABIC_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "data", "tafsirs", "_arabic.json")

MARKER_RE = re.compile(r"^(>\s*)\{\{ayah:(\d+):(\d+)\}\}\s*$")
# арабское письмо БЕЗ Presentation Forms-A (там ﷺ и пр. лигатуры) и без ۩ (саджда)
AR_STRICT = re.compile(r"[؀-۪ۧ-ۿݐ-ݿࢠ-ࣿﹰ-ﻼ]")

DIGITS = "٠١٢٣٤٥٦٧٨٩"


def arnum(n):
    return "".join(DIGITS[int(d)] for d in str(n))


def load_quran():
    return json.load(open(ARABIC_JSON, encoding="utf-8"))


def subst_file(path, quran, basmala):
    lines = open(path, encoding="utf-8").read().split("\n")
    out, n_subst, errors = [], 0, []
    for line in lines:
        m = MARKER_RE.match(line.strip())
        if not m:
            out.append(line)
            continue
        prefix, s, a = "> ", m.group(2), m.group(3)
        text = quran.get(s, {}).get(a)
        if text is None:
            errors.append(f"{path}: нет аята {s}:{a} в JSON")
            out.append(line)
            continue
        if a == "1" and s not in ("1", "9") and text.startswith(basmala):
            rest = text[len(basmala):].strip()
            out.append(prefix + basmala)
            out.append(prefix + rest + " ﴿" + arnum(a) + "﴾")
        else:
            out.append(prefix + text + " ﴿" + arnum(a) + "﴾")
        n_subst += 1
    if n_subst:
        open(path, "w", encoding="utf-8").write("\n".join(out))
    # предупреждение (не ошибка): арабское письмо вне строк-цитат
    warns = []
    for i, line in enumerate(open(path, encoding="utf-8"), 1):
        if not line.lstrip().startswith(">") and AR_STRICT.search(line):
            warns.append(f"{path}:{i}: арабские символы вне цитаты: {line.strip()[:60]}")
    # ОШИБКА: вложенные/несбалансированные <span> — конвертер их не переварит
    depth = 0
    text = open(path, encoding="utf-8").read()
    for m in re.finditer(r"<span\b[^>]*>|</span>", text):
        if m.group().startswith("</"):
            depth -= 1
            if depth < 0:
                errors.append(f"{path}: лишний </span> (несбалансировано)")
                depth = 0
        else:
            depth += 1
            if depth > 1:
                errors.append(f"{path}: вложенный <span> — распрямить (…{text[max(0,m.start()-40):m.start()]!r})")
                depth = 1
    if depth != 0:
        errors.append(f"{path}: незакрытый <span>")
    return n_subst, errors, warns


def main():
    quran = load_quran()
    basmala = quran["1"]["1"]
    if len(sys.argv) > 1:
        files = sys.argv[1:]
    else:
        files = []
        for folder in ("детям", "подросткам"):
            root = os.path.join(VAULT, folder)
            for sura in sorted((d for d in os.listdir(root) if d.isdigit()), key=int):
                sdir = os.path.join(root, sura)
                files += [os.path.join(sdir, f) for f in sorted(os.listdir(sdir))
                          if re.match(r"^\d+-\d+\.md$", f)]
    total, all_errors, all_warns = 0, [], []
    for path in files:
        n, errs, warns = subst_file(path, quran, basmala)
        total += n
        all_errors += errs
        all_warns += warns
        if n:
            print(f"{path}: подставлено {n}")
    print(f"Итого подстановок: {total}")
    if all_warns:
        print("\n?? Предупреждения (арабский вне цитат — проверить глазами):")
        for w in all_warns:
            print(" ", w)
    if all_errors:
        print("\n!! ОШИБКИ:")
        for e in all_errors:
            print(" ", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
