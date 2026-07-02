#!/usr/bin/env python3
"""
Тафсир аль-Багави (рус.) — конвертация из docx в данные библиотеки.

Источник: data/_sources/baghawi/тафсир/<sura>.docx  (суры 58–114, набор Ismail'а).
Перевод аятов Ismail'а уже ВСТРОЕН в тафсир как заголовки аятов — используем его
(Кулиева нет). Отдельный перевод — data/_sources/baghawi/аяты/*переводбаг.docx.

ДВА ФОРМАТА docx:
  A (джузы 28,30 = 58–66, 78–114): строка "N) «перевод»" затем комментарий до
    следующего "N)". Чисто.
  B (джуз 29 = 67–77): "<арабский>N. <перевод>" склеены, аяты идут диапазонами,
    комментарий на диапазон, разделители вида "Власть 3-4".

Выход: data/tafsirs/baghawi.json = {"<sura>": {"<ayah>": "md", "0": "интро"}}.

Использование:
  python3 build_baghawi.py --sample 112 90 58 67   # печать md, без записи
  python3 build_baghawi.py                          # собрать монолит
Дальше: split.py baghawi && build_index.py baghawi && compute_fill.py && build_coverage.py
"""
import os, re, sys, json, zipfile
from xml.etree import ElementTree as ET

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "data", "_sources", "baghawi", "тафсир")
OUT = os.path.join(ROOT, "data", "tafsirs", "baghawi.json")
NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

AR = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
def arabic_ratio(s):
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return 0.0
    return sum(bool(AR.match(c)) for c in letters) / len(letters)

def paras(path):
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml")
    out = []
    for p in ET.fromstring(xml).iter(NS + "p"):
        s = "".join(t.text or "" for t in p.iter(NS + "t")).strip()
        if s:
            out.append(s)
    return out

_AR_SEQ = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿‏‎]+")
def drop_arabic(s):
    """Убрать арабские фрагменты, схлопнуть пробелы (сохранив пунктуацию)."""
    return re.sub(r"\s{2,}", " ", _AR_SEQ.sub(" ", s)).strip()

def strip_arabic(s):
    """Как drop_arabic, но ещё срезать обрамляющие пробелы/точки (для интро/коммента)."""
    return drop_arabic(s).strip(" .")

# ---------- разбор шапки суры → интро ----------
def parse_header(P):
    """Вернуть (intro_md, idx) — idx = индекс первой строки после шапки."""
    name = mecca = None
    i = 0
    # имя суры
    for j in range(min(4, len(P))):
        m = re.search(r"Сура\s*[«\"]([^»\"]+)[»\"]", P[j])
        if m:
            name = m.group(1).strip(); break
    # мекканская/мединская + число аятов
    for j in range(min(5, len(P))):
        if re.search(r"(Мекканская|Мединская)", P[j]):
            m = re.search(r"(Мекканская|Мединская)[^.]*\.\s*(?:Состоит[^.]*\.)?", P[j])
            mecca = strip_arabic(m.group(0)).strip() if m else strip_arabic(P[j])
            break
    # пропустить шапку: имя, статус, басмалу(ар), басмалу(ру)
    i = 0
    while i < len(P):
        l = P[i]
        if (re.search(r"Тафсир Багави Сура", l) or re.search(r"Сура\s*[«\"]", l)
                or re.search(r"(Мекканская|Мединская)", l) or arabic_ratio(l) > 0.5
                or re.search(r"именем Аллаха|имя Аллаха", l, re.I)):
            i += 1; continue
        break
    intro_parts = []
    if name:
        intro_parts.append("**Сура «%s»**" % name)
    if mecca:
        intro_parts.append(mecca)
    intro = "\n\n".join(intro_parts)
    return intro, i

# ---------- ФОРМАТ A: "N) «перевод»" ----------
def parse_A(P):
    intro, i = parse_header(P)
    out = {}
    if intro:
        out["0"] = intro
    cur = None; buf = []
    def flush():
        if cur is not None:
            out[str(cur)] = "\n\n".join(x for x in buf if x).strip()
    for l in P[i:]:
        m = re.match(r"^(\d{1,3})\)\s*(.*)$", l)
        if m:
            flush()
            cur = int(m.group(1)); buf = []
            head = m.group(2).strip()
            if head:
                buf.append("**%s**" % head)  # перевод аята — жирным
        else:
            if cur is not None:
                buf.append(l)
    flush()
    return out

# ---------- ФОРМАТ B: арабский+"N."+перевод, комментарий на диапазон ----------
_DECL = re.compile(r"(\d{1,3})\.\s*(.+?)(?=\s*\d{1,3}\.\s|$)")
def parse_B(P):
    intro, i = parse_header(P)
    out = {}
    if intro:
        out["0"] = intro
    # группируем: блок объявлений аятов (арабский+N.+перевод) + следующий за ним
    # комментарий = одна группа (комментарий Багави идёт на диапазон аятов).
    groups = []       # {'ayahs':[(n,tr)], 'comment':[str]}
    cur = None
    for l in P[i:]:
        # структурный разделитель "Власть 3-4" — закрывает группу
        if re.match(r"^[А-ЯЁ][а-яё][а-яё\- ]*\s+\d+(\s*[-–]\s*\d+)?$", l):
            if cur and (cur['ayahs'] or cur['comment']):
                groups.append(cur); cur = None
            continue
        is_decl = (bool(re.match(r'^["“\s]*\d{1,3}\.\s', l))
                   or (arabic_ratio(l) > 0.12 and re.search(r"\d{1,3}\.", l)))
        if is_decl:
            if cur and cur['comment']:            # начались новые аяты после коммента
                groups.append(cur); cur = None
            if cur is None:
                cur = {'ayahs': [], 'comment': []}
            for m in _DECL.finditer(drop_arabic(l)):
                n = int(m.group(1)); tr = m.group(2).strip().strip('"«».  ')
                if 1 <= n <= 300 and tr:
                    cur['ayahs'].append((n, tr))
        else:
            comm = drop_arabic(l).strip().strip('"')
            if not comm:
                continue
            if cur is None:
                cur = {'ayahs': [], 'comment': []}
            cur['comment'].append(comm)
    if cur and (cur['ayahs'] or cur['comment']):
        groups.append(cur)
    # раскладка: первый аят диапазона получает переводы всех аятов группы +
    # комментарий; прочие аяты — свой перевод + отсылка к диапазону.
    for g in groups:
        ns = [n for n, _ in g['ayahs']]
        if not ns:
            continue
        first = min(ns)
        rng = "%d–%d" % (min(ns), max(ns)) if len(set(ns)) > 1 else str(first)
        heads = "\n".join("**«%s»**" % tr for _, tr in g['ayahs'])
        comment = "\n\n".join(g['comment']).strip()
        out[str(first)] = (heads + ("\n\n" + comment if comment else "")).strip()
        for n, tr in g['ayahs']:
            if n == first:
                continue
            ptr = "\n\n*(См. толкование аятов %s)*" % rng if comment else ""
            out[str(n)] = ("**«%s»**" % tr + ptr).strip()
    return out

def detect_and_parse(path):
    P = paras(path)
    # формат A, если есть заметное число маркеров "N) «"
    a_markers = sum(bool(re.match(r"^\d{1,3}\)\s*[«\"]", l)) for l in P)
    return (parse_A if a_markers >= 3 else parse_B)(P), ("A" if a_markers >= 3 else "B")

# ---------- перевод аятов Ismail'а (для дозаполнения формата B) ----------
AYAT_DIR = os.path.join(ROOT, "data", "_sources", "baghawi", "аяты")
_AYAH_MARK = re.compile(r"(?:^|\s)(\d{1,3})[\).]\s*([^0-9].*?)(?=(?:\s\d{1,3}[\).]\s)|$)")
def load_ayah_tr():
    """{сура: {аят: перевод}} из аяты/*переводбаг.docx (оба формата заголовков)."""
    res = {}
    if not os.path.isdir(AYAT_DIR):
        return res
    for fn in sorted(os.listdir(AYAT_DIR)):
        if not fn.endswith(".docx"):
            continue
        cur = None
        for l in paras(os.path.join(AYAT_DIR, fn)):
            h = re.search(r"Сура\s*(\d{1,3})", l) or re.match(r"\s*(\d{1,3})\s+Сура", l)
            if h and "Сура" in l:
                cur = int(h.group(1)); res.setdefault(cur, {}); continue
            if cur is None:
                continue
            for m in _AYAH_MARK.finditer(drop_arabic(l)):
                n = int(m.group(1)); t = m.group(2).strip().strip('"«».  ')
                if 1 <= n <= 300 and t and n not in res[cur]:
                    res[cur][n] = t
    return res

# ---------- сборка / выборка ----------
def sura_path(s):
    return os.path.join(SRC, "%d.docx" % s)

def canon_counts():
    res = {}
    for s in range(1, 115):
        af = os.path.join(ROOT, "data", "tafsirs", "_arabic", "%d.json" % s)
        if os.path.isfile(af):
            res[s] = max(int(k) for k in json.load(open(af)))
    return res

def build_all():
    data = {}
    stats = []
    ayah_tr = load_ayah_tr()
    canon = canon_counts()
    filled = 0
    for s in range(58, 115):
        p = sura_path(s)
        if not os.path.isfile(p):
            continue
        chunk, fmt = detect_and_parse(p)
        # дозаполнение пропусков формата B переводом аятов Ismail'а
        if fmt == "B" and s in ayah_tr:
            for n in range(1, canon.get(s, 0) + 1):
                if str(n) not in chunk and n in ayah_tr[s]:
                    chunk[str(n)] = ("**«%s»**\n\n*(толкование — в составе соседних аятов)*"
                                     % ayah_tr[s][n])
                    filled += 1
        ayahs = [k for k in chunk if k != "0"]
        data[str(s)] = chunk
        stats.append((s, fmt, len(ayahs)))
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print("монолит:", OUT)
    for s, fmt, n in stats:
        print("  сура %3d [%s]: %3d аятов" % (s, fmt, n))
    tot = sum(n for _, _, n in stats)
    print("итого сур %d, аятов %d (дозаполнено из твоих аятов: %d)" % (len(stats), tot, filled))

def sample(sids):
    canon = {}
    for s in sids:
        af = os.path.join(ROOT, "data", "tafsirs", "_arabic", "%s.json" % s)
        if os.path.isfile(af):
            canon[int(s)] = max(int(k) for k in json.load(open(af)))
    for s in sids:
        p = sura_path(int(s))
        chunk, fmt = detect_and_parse(p)
        ayahs = sorted(int(k) for k in chunk if k != "0")
        need = canon.get(int(s), "?")
        print("\n================ сура %s [формат %s] — %d/%s аятов ================" %
              (s, fmt, len(ayahs), need))
        if "0" in chunk:
            print("  [0 интро] %s" % chunk["0"].replace("\n", " ")[:120])
        for k in [str(x) for x in ayahs[:3]]:
            print("  [%s] %s" % (k, chunk[k].replace("\n", " ⏎ ")[:300]))

if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--sample":
        sample(args[1:])
    else:
        build_all()
