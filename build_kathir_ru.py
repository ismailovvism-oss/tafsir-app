#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Нормализация русского перевода тафсира Ибн Касира (Мухтасар, пер. Вахитова)
из TXT (pdftotext) в чистый Markdown по сурам.

Два формата экстракции:
  A (т1,2,3,5): центрированная проза, арабский в presentation-forms (визуальный
               порядок) -> реверс+NFKC, скелет без огласовок. Сноски внизу страниц.
  B (т4,8):     двухколоночная вёрстка (слева RU-перевод с номерами аятов, справа
               арабский с огласовками). Арабский в нормальной форме.

Этот файл пока реализует путь A. Путь B (per-аят) — отдельно.

Вывод: data/_sources/kathir_ru/<сура>.md  (+ _intro.md, _report.md)
"""
import re, sys, os, unicodedata
from pathlib import Path

SRC = Path("/home/qaadiy/obsid/qaadiy/Ислам/Коран/Тафсир/Ибн Касир/Перевод Ибн Касира/1")
OUT = Path("data/_sources/kathir_ru")

VOLS_A = {
    "т1": "893345485-Тафсир-Ибн-Касира-1.txt",
    "т2": "886524548-Mukhtasar-Tafsir-Ibn-Kasir-Tom-2.txt",
    "т3": "886524557-Mukhtasar-Tafsir-Ibn-Kasir-Tom-3.txt",
}
VOLS_B = {
    "т4": "801794368-Том-4.txt",
    "т8": "801794850-Том-8.txt",
}

# ── арабский ───────────────────────────────────────────────────────────────
ARAB = re.compile(r'[؀-ۿﭐ-﷿ﹰ-﻿]')
ARAB_RUN = re.compile(r'[؀-ۿﭐ-﷿ﹰ-﻿][؀-ۿﭐ-﷿ﹰ-﻿\s]*')
HARAKAT = re.compile('[ؐ-ًؚ-ٰٟۖ-ۭـ]')
BIDI = re.compile('[‎‏‪-‮⁦-⁩؜]')

def fix_arabic_A(seg):
    """Формат A: визуальный порядок presentation-forms -> логический скелет."""
    s = unicodedata.normalize('NFKC', seg[::-1])
    s = HARAKAT.sub('', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def fix_line_arabic_A(line):
    line = BIDI.sub('', line)
    if not ARAB.search(line):
        return line
    return ARAB_RUN.sub(lambda m: fix_arabic_A(m.group(0)), line)

# ── структура ────────────────────────────────────────────────────────────────
def is_pagenum(line):
    return bool(re.fullmatch(r'\s*\d{1,4}\s*', line.replace('\x0c', ' ')))

SURA_HDR = re.compile(r'^\s*Сура\s*(?:\d+\s*)?[(«]')
SENTENCE = re.compile(r'(ниспослан|была|состоит|мекканск|мединск|аят)', re.I)

def detect_surah(line):
    st = line.strip()
    if len(st) > 55 or '…' in st or '....' in st:
        return None
    if not SURA_HDR.match(line):
        return None
    if SENTENCE.search(st):
        return None
    if re.search(r'\d\s*$', st):       # строка оглавления: имя ... номер страницы
        return None
    return st

# таблица: очищенное имя (без не-букв, ё->е) -> номер. translit (с артиклем) + рус.
SURA_NUM = {
    'альфатиха': 1, 'открывающая': 1,
    'альбакара': 2, 'корова': 2,
    'альимран': 3, 'семействоимрана': 3,
    'анниса': 4, 'женщины': 4,
    'альмаида': 5, 'трапеза': 5,
    'альанам': 6, 'скот': 6,
    'альараф': 7, 'преграды': 7,
    'альанфал': 8, 'добыча': 8,
    'аттауба': 9, 'покаяние': 9,
    'юнус': 10, 'юунус': 10,
    'худевер': 11, 'худ': 11,
    'юсуфиосиф': 12, 'юсуф': 12,
    'аррад': 13, 'гром': 13,
    'ибрахимавраам': 14, 'ибрахим': 14,
    'альхиджр': 15,
    'аннахльпчелы': 16, 'аннахль': 16, 'пчелы': 16, 'пчел': 16,
    'альисра': 17, 'альисраперенос': 17, 'переносночью': 17,
    'алькахфпещера': 18, 'алькахф': 18, 'пещера': 18,
    'марьяммария': 19, 'марьям': 19,
}
def _clean(s):
    return re.sub(r'[^a-zа-я]', '', s.lower().replace('ё', 'е'))

def slug_num(hdr):
    # явный номер ("Сура 11 ...")
    m = re.search(r'Сура\s*(\d+)', hdr)
    if m:
        return int(m.group(1))
    # translit в первых скобках (...), затем рус. в «...»
    for m in re.findall(r'\(([^)]*)\)', hdr) + re.findall(r'«([^»]*)»', hdr):
        c = _clean(m)
        if c in SURA_NUM:
            return SURA_NUM[c]
    # на крайний случай — по очищенному всему заголовку без слова "сура"
    c = _clean(re.sub(r'сура', '', hdr, flags=re.I))
    for key, n in SURA_NUM.items():
        if len(key) >= 5 and key in c:
            return n
    return None

# ── переборка строк ──────────────────────────────────────────────────────────
TERMINAL = ('.', '!', '?', '»', '…', ':')

def tidy_punct(s):
    s = re.sub(r'\s+([,.;:!?»])', r'\1', s)          # пробел перед знаком
    s = re.sub(r'([«(\[])\s+', r'\1', s)              # пробел после открывающей
    s = re.sub(r'\s+([)\]])', r'\1', s)               # пробел перед закрывающей
    s = re.sub(r'\s*([–—])\s*', r' \1 ', s)           # тире с пробелами
    s = re.sub(r'\s{2,}', ' ', s)
    return s.strip()

def join_para(lines):
    out = ''
    for t in lines:
        t = t.strip()
        if not t:
            continue
        if not out:
            out = t; continue
        if out.endswith('-'):
            out = out[:-1] + t if t[:1].islower() else out + t
        else:
            out += ' ' + t
    return tidy_punct(out)

def tidy_header(hdr, num):
    h = re.sub(r'^\s*Сура\s*\d*\s*', '', hdr)         # убрать "Сура N"
    h = re.sub(r'\(\s*', '(', h); h = re.sub(r'\s*\)', ')', h)
    h = re.sub(r'«\s*', '«', h); h = re.sub(r'\s*»', '»', h)
    h = re.sub(r'\s*-\s*', '-', h)                    # "Аль - Бакара" -> "Аль-Бакара"
    h = re.sub(r'\s{2,}', ' ', h).strip()
    return f"Сура {num}. {h}" if num else f"Сура. {h}"

def reflow(lines):
    """Возвращает [(тип, текст)] где тип in {'h1','para'}."""
    blocks = []
    buf = []
    def flush():
        if buf:
            p = join_para(buf)
            if p:
                blocks.append(('para', p))
            buf.clear()
    for raw in lines:
        clean = raw.replace('\x0c', '')
        if clean.strip() == '':
            flush(); continue
        if is_pagenum(raw):
            continue
        hdr = detect_surah(clean)
        if hdr:
            flush()
            blocks.append(('h1', hdr))
            continue
        t = clean.strip()
        buf.append(t)
        if len(t) < 58 and t.endswith(TERMINAL):
            flush()
    flush()
    return blocks

# ── обработка тома ────────────────────────────────────────────────────────────
def process_volume_A(path):
    lines = [fix_line_arabic_A(l) for l in path.read_text(encoding='utf-8').split('\n')]
    return reflow(lines)

# ── формат B (т4/т8): двухколоночный, арабский с огласовками ──────────────────
QURAN_BR = re.compile('[﴾﴿]')
FURNITURE_B = re.compile(r'Комментарии к Великому Корану|^\s*аят\s*\d+\s*[-–]\s*\d+|\bаят\s*\d+\s*[-–]\s*\d+\s*$')
AYAH_NUM = re.compile(r'^\s*(\d{1,3})\.\s+\S')

def strip_arabic_B(line):
    """Убрать арабский (он будет ре-сорситься из Tanzil), оставить русский глосс."""
    line = BIDI.sub('', line)
    line = QURAN_BR.sub('', line)
    line = ARAB_RUN.sub(' ', line)
    return re.sub(r'\s{2,}', ' ', line).rstrip()

def is_furniture_B(line):
    s = line.replace('\x0c', ' ')
    if is_pagenum(s):
        return True
    if FURNITURE_B.search(s):
        return True
    return False

def reflow_B(lines):
    """Юстированная проза: абзацы по отступу/пустой строке; номера аятов — отд. абзацы."""
    blocks = []
    buf = []
    def flush():
        if buf:
            p = join_para(buf)
            if p:
                blocks.append(('para', p))
            buf.clear()
    prev_ind = None
    for raw in lines:
        if is_furniture_B(raw):
            continue
        ruline = strip_arabic_B(raw)
        if ruline.strip() == '':
            # пустая строка ИЛИ строка была чисто арабской — мягкая граница
            if raw.replace('\x0c', '').strip() == '':
                flush(); prev_ind = None
            continue
        hdr = detect_surah(ruline)
        if hdr:
            flush(); blocks.append(('h1', hdr)); prev_ind = None; continue
        t = ruline.strip()
        ind = len(ruline) - len(ruline.lstrip(' '))
        # начало абзаца: номер аята, либо красная строка после строк без отступа
        if buf:
            new_para = bool(AYAH_NUM.match(ruline))
            prev = buf[-1].strip()
            if len(prev) < 58 and prev.endswith(TERMINAL):
                new_para = True
            if prev_ind is not None and ind - prev_ind >= 3 and prev_ind <= 4:
                new_para = True
            if new_para:
                flush()
        buf.append(t)
        prev_ind = ind
    flush()
    return blocks

def process_volume_B(path):
    return reflow_B(path.read_text(encoding='utf-8').split('\n'))

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = []
    all_surahs = {}      # num -> {title, blocks}
    intro_blocks = []
    vols = [(v, f, 'A') for v, f in VOLS_A.items()] + [(v, f, 'B') for v, f in VOLS_B.items()]
    for vi, (vol, fname, fmt) in enumerate(vols):
        blocks = process_volume_A(SRC / fname) if fmt == 'A' else process_volume_B(SRC / fname)
        # разрезать по h1 (заголовкам сур)
        cur = None
        for typ, txt in blocks:
            if typ == 'h1':
                num = slug_num(txt)
                cur = num
                all_surahs.setdefault(num, {'title': txt, 'blocks': []})
                report.append(f"{vol}: сура {num} <- {txt!r}")
            else:
                if cur is None:
                    # предисловие идентично во всех томах — берём только из первого
                    if vi == 0:
                        intro_blocks.append((typ, txt))
                else:
                    all_surahs[cur]['blocks'].append((typ, txt))
    # запись
    if intro_blocks:
        (OUT / "_intro.md").write_text(
            "# Введение\n\n" + "\n\n".join(t for _, t in intro_blocks), encoding='utf-8')
    for num, data in sorted(all_surahs.items(), key=lambda x: (x[0] is None, x[0])):
        body = f"# {tidy_header(data['title'], num)}\n\n" + "\n\n".join(t for _, t in data['blocks'])
        name = f"{num}.md" if num else "_unmapped.md"
        (OUT / name).write_text(body, encoding='utf-8')
    (OUT / "_report.md").write_text("\n".join(report), encoding='utf-8')
    print("Готово. Суры:", sorted(k for k in all_surahs if k))
    print("Интро-блоков:", len(intro_blocks))
    print("Файлы:", sorted(p.name for p in OUT.glob("*.md")))

if __name__ == '__main__':
    main()
