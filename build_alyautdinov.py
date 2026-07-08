#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сборка источника «Коран. Богословский перевод» Шамиля Аляутдинова (id: alyautdinov).

Вход — 4 тома .txt в кодировке cp1251 (SRC_DIR). Разметка источника:
  • «Сура N. «название»»            — заголовок суры (иногда с переносом:
                                       «Сура 28\\n\\n. «аль-Касас»»);
  • строка-маркер  N:M  или  N:M–K — блок аятов (Аляутдинов группирует аяты);
  • сноски встроены в текст как  [14 - текст…]  (номер, дефис, текст),
    внутри бывают вложенные [ ] — тащим балансировкой скобок;
  • вставки-пояснения  [именем Бога…]  (без номера) — часть перевода, оставляем;
  • хвосты  ***  и «Милостью Всевышнего тафсир N-й главы… подошёл к концу» — режем.

Выход:
  • data/tafsirs/alyautdinov.json  — монолит {сура:{аят:md}}:
      – текст блока N:M–K кладётся в аят M;
      – аяты M+1..K получают отсылку «*Перевод аятов M–K — см. аят M.*»
        (как в fix_kathir_blocks.py — чтобы покрытие/счётчик их учитывали);
      – вступление к суре (текст до первого маркера) → ключ "0";
      – сноски перенумерованы локально в родные сноски приложения  слово[^1]
        + строкой  [^1]: текст.
  • data/about/alyautdinov.md — книжная мукаддима (вступление из начала т.1).

После сборки:
  python3 split.py alyautdinov && python3 build_index.py alyautdinov \\
    && python3 compute_fill.py && python3 build_coverage.py && python3 sync_config.py
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = "/home/qaadiy/obsid/qaadiy/Ислам/Коран/Чтение Корана/Разные форматы/еще разное"
VOLS = [f"Богословский перевод. Том {n}.txt" for n in (1, 2, 3, 4)]

OUT_MONO = os.path.join(ROOT, "data", "tafsirs", "alyautdinov.json")
OUT_ABOUT = os.path.join(ROOT, "data", "about", "alyautdinov.md")

DASH, SEP = "–", "—"

# Заголовок суры: «Сура N ... «название»» (перенос строки между номером и точкой
# допускается; имя не используем, поэтому не требуем корректной закрывающей » —
# в источнике встречается опечатка «аш-Шу‘ара’ «). Заголовок = до конца своей строки.
RE_SURA = re.compile(r"(?m)^Сура\s+(\d+)[.\s]*«[^\n]*")
# Маркер блока аятов на отдельной строке. Аляутдинов группирует аяты по-разному:
#   N:M   |   N:M–K (диапазон)   |   N:M, K, L (список)   |   их смесь.
RE_BLOCK = re.compile(r"(?m)^[ \t]*(\d+):(\d+(?:[ \t]*[–—,-][ \t]*\d+)*)[ \t]*$")


def parse_spec(spec):
    """'1–5' / '6, 7' / '1, 3–5' → отсортированный список номеров аятов."""
    nums = []
    for part in spec.split(","):
        part = part.strip()
        m = re.match(r"^(\d+)\s*[–—-]\s*(\d+)$", part)
        if m:
            nums.extend(range(int(m.group(1)), int(m.group(2)) + 1))
        elif part.isdigit():
            nums.append(int(part))
    return sorted(set(nums))
# Служебная концовка суры
RE_CLOSING = re.compile(r"(?m)^.*Милостью Всевышнего тафсир .*подош[её]л к концу.*$")
# Начало сноски внутри текста: [ digits <dash> <space>
RE_FN_START = re.compile(r"\[(\d+)\s*[-–—]\s")


def grab_balanced(s, i):
    """Вернуть подстроку s[i:j+1] от '[' до парной ']' с учётом вложенности."""
    depth = 0
    j = i
    while j < len(s):
        c = s[j]
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return s[i:j + 1]
        j += 1
    return None  # незакрытая скобка — не трогаем


def extract_footnotes(text):
    """Вырезать сноски [N - …], заменить на [^k], вернуть (текст, [(k, note)…])."""
    out = []
    notes = []
    k = 0
    pos = 0
    while True:
        m = RE_FN_START.search(text, pos)
        if not m:
            out.append(text[pos:])
            break
        span = grab_balanced(text, m.start())
        if span is None:
            # незакрытая — оставляем как есть, идём дальше
            out.append(text[pos:m.start() + 1])
            pos = m.start() + 1
            continue
        # внутренность после «N - »
        inner = span[1:-1]
        note = re.sub(r"^\s*\d+\s*[-–—]\s*", "", inner, count=1)
        note = re.sub(r"\s+", " ", note).strip()
        k += 1
        notes.append((k, note))
        out.append(text[pos:m.start()])
        out.append(f"[^{k}]")
        pos = m.start() + len(span)
    return "".join(out), notes


def clean_body(text):
    """Нормализовать пробелы, убрать концовки и *** ↦ ---."""
    text = RE_CLOSING.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # *** (разделитель разделов) → горизонтальная линия
    text = re.sub(r"(?m)^[ \t]*\*\*\*[ \t]*$", "\n---\n", text)
    # свернуть 3+ переводов строки в абзацный разрыв
    text = re.sub(r"\n[ \t]*\n([ \t]*\n)+", "\n\n", text)
    return text.strip()


def render_unit(raw):
    """Сырой кусок текста → готовый markdown с родными сносками (или '')."""
    body, notes = extract_footnotes(raw)
    body = clean_body(body)
    if notes:
        defs = "\n".join(f"[^{k}]: {note}" for k, note in notes)
        body = (body + "\n\n" + defs).strip()
    return body


def ref_text(lo, hi):
    return f"*Перевод аятов {lo}{DASH}{hi} {SEP} см. аят {lo}.*"


def parse_surah(num, region, data):
    """Разобрать текст одной суры: intro (ключ '0') + блоки аятов."""
    sd = data.setdefault(str(num), {})
    marks = list(RE_BLOCK.finditer(region))
    # вступление к суре — до первого маркера
    if marks:
        intro_raw = region[:marks[0].start()]
    else:
        intro_raw = region
    intro = render_unit(intro_raw)
    if intro:
        sd["0"] = intro
    for idx, m in enumerate(marks):
        s_no = int(m.group(1))
        if s_no != num:
            continue  # чужой маркер (перекрёстная ссылка) — пропускаем
        ayahs = parse_spec(m.group(2))
        if not ayahs:
            continue
        end = marks[idx + 1].start() if idx + 1 < len(marks) else len(region)
        body = render_unit(region[m.end():end])
        if not body:
            continue
        a_lo, a_hi = ayahs[0], ayahs[-1]
        sd[str(a_lo)] = body
        for a in ayahs[1:]:
            sd.setdefault(str(a), ref_text(a_lo, a_hi))
    return sd


def main():
    data = {}
    book_intro = None
    for vi, fname in enumerate(VOLS):
        path = os.path.join(SRC_DIR, fname)
        s = open(path, "rb").read().decode("cp1251").replace("\r\n", "\n").replace("\r", "\n")
        heads = list(RE_SURA.finditer(s))
        if vi == 0 and heads:
            # книжная мукаддима = текст до «Сура 1.»
            book_intro = s[:heads[0].start()]
        for hi, h in enumerate(heads):
            num = int(h.group(1))
            end = heads[hi + 1].start() if hi + 1 < len(heads) else len(s)
            parse_surah(num, s[h.end():end], data)

    # монолит
    os.makedirs(os.path.dirname(OUT_MONO), exist_ok=True)
    data = {k: data[k] for k in sorted(data, key=int)}
    json.dump(data, open(OUT_MONO, "w", encoding="utf-8"),
              ensure_ascii=False, indent=0)

    # about / мукаддима
    if book_intro:
        md = render_unit(book_intro)
        os.makedirs(os.path.dirname(OUT_ABOUT), exist_ok=True)
        open(OUT_ABOUT, "w", encoding="utf-8").write(md + "\n")

    # статистика
    n_sur = len(data)
    n_ayah = sum(1 for sd in data.values() for k in sd if k != "0")
    n_intro = sum(1 for sd in data.values() if "0" in sd)
    print(f"alyautdinov: сур={n_sur}, аятов(ключей)={n_ayah}, вступлений={n_intro}")
    print(f"  → {OUT_MONO}")
    print(f"  → {OUT_ABOUT}")


if __name__ == "__main__":
    main()
