#!/usr/bin/env python3
"""
Конвертер русского «Тафсир аль-Куртуби» (пер. Исмаила Хаертдинова) из .docx-томов
в формат приложения: {сура:{аят:markdown}}.

Источник: Obsidian-вольт пользователя (5 томов = 5 сур: 16,17,18,19,36).
Каждый файл назван по НОМЕРУ СУРЫ. Разметка внутри — заголовки-секции вида
«Тафсир суры «X» N аят.» / «… N-M аят.» / «Сура X N аят.» (формулировка плавает).

РАЗБИВКА ПОАЯТНО (без блоков):
  • одиночный заголовок (N)      → весь текст секции идёт в аят N;
  • диапазон (N-M)               → секция дробится по АРАБСКИМ ЦИТАТАМ-леммам:
        каждую арабскую цитату сопоставляем с каноническим _arabic_clean,
        определяем номер аята и «пришиваем» к нему следующий комментарий;
        вводная (полная цитата диапазона + перевод) идёт в первый аят N.
  • материал до первого заголовка (фадаиль/вступление) → ключ "0" суры.

Запуск:  python3 build_qurtubi_ru.py [--sura N]
Далее :  split уже встроен (пишем чанки сразу); затем
         python3 build_index.py qurtubi_ru && cp data/index/qurtubi_ru.json r2-data/index/
         python3 compute_fill.py && python3 build_coverage.py && python3 sync_config.py
"""
import zipfile, re, json, os, glob, sys, unicodedata, shutil
from xml.etree import ElementTree as ET

ROOT = os.path.dirname(os.path.abspath(__file__))
VAULT = "/home/qaadiy/obsid/qaadiy/Ислам/Коран/Тафсир/Куртуби"
R2_TAF = os.path.join(ROOT, "r2-data", "tafsirs")
DATA_TAF = os.path.join(ROOT, "data", "tafsirs")
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
ID = "qurtubi_ru"

SURAS = {16: "Ан-Нахль", 17: "Аль-Исра", 18: "Аль-Кахф", 19: "Марьям", 36: "Йа Син"}

CLEAN = json.load(open(os.path.join(DATA_TAF, "_arabic_clean.json"), encoding="utf-8"))

HEADER = re.compile(r'^(?:Тафсир|Толкование|Сура)\b.{0,45}?(\d+)\s*(?:[-–—]\s*(\d+))?\s*аят\.?\s*$', re.I)
BOILER = re.compile(r'Тафсир аль-Куртуби|الجامع لأحكام|^Автор:|^Годы жизни|Перевел|^\(\d+[–-]\d+/|^Сура .{0,40}\.\s*$', re.I)


def paras(path):
    root = ET.fromstring(zipfile.ZipFile(path).read("word/document.xml").decode("utf-8"))
    return ["".join(t.text or "" for t in pn.iter(W + "t")) for pn in root.iter(W + "p")]


def norm_ar(s):
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    s = s.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه",
                                   "ى": "ي", "ؤ": "و", "ئ": "ي", "ء": ""}))
    return re.sub(r'[^ء-ي]', '', s)


def is_arabic(t):
    al = [c for c in t if c.isalpha()]
    ar = [c for c in al if '؀' <= c <= 'ۿ']
    return len(ar) >= 4 and len(ar) >= 0.6 * len(al)


# Маркеры эпилога переводчика (послесловие/лицензия/подпись/дата). Ищем их ТОЛЬКО
# внутри последней секции (после последнего заголовка) — так легитимный тафсир не
# режется. Заголовок эпилога плавает: «…слово переводчика» (36/17/19),
# «Уведомление о правах» (18); у сур без послесловия (16) — только дата в конце.
EPI = re.compile(
    r'(Послесловие|Заключительн\w+ слово|Завершающ\w+ слово|СЛОВО ПЕРЕВОДЧИКА'
    r'|Уведомление о правах|Обратная связь|обратной связи|С уважением'
    r'|Хаертдинов|Валиулла|@|коммерческ\w+ использ|интеллектуальн\w+ труд'
    r'|Просим у читателей|\b\d{2}\.\d{2}\.\d{4}\b'
    r'|^\d+\s+(Шавваль|Шаввал|Рамадан|Раби|Джумад|Зуль|Мухаррам|Сафар|Раджаб|Ша[аъ]бан))', re.I)


def convert_sura(num):
    path = os.path.join(VAULT, f"Куртуби {num}.docx")
    P = [p.rstrip() for p in paras(path)]
    hpre = [i for i, t in enumerate(P) if HEADER.match(t.strip())]
    if hpre:  # отсечь эпилог переводчика (только в пределах последней секции)
        last = hpre[-1]
        epcut = next((i for i in range(last + 1, len(P)) if EPI.search(P[i].strip())), len(P))
        P = P[:epcut]
    # индексы заголовков-секций
    hidx = [i for i, t in enumerate(P) if HEADER.match(t.strip())]
    out = {}
    # вступление до первого заголовка (без служебной шапки)
    intro = [t for t in P[:hidx[0]] if t.strip() and not BOILER.search(t.strip())]
    if intro:
        out["0"] = "\n\n".join(intro).strip()
    sura_total = max((int(a) for a in CLEAN.get(str(num), {})), default=300)
    canon = {a: norm_ar(CLEAN.get(str(num), {}).get(str(a), "")) for a in range(1, sura_total + 1)}
    # стартовые аяты (lo) всех секций — надёжны; верхнюю границу анкеринга берём
    # по началу СЛЕДУЮЩЕЙ секции (для последней — конец суры), а не из заголовка
    # (заголовочный hi иногда занижен: последний блок вмещает хвост суры).
    los = [int(HEADER.match(P[i].strip()).group(1)) for i in hidx]

    for hi_i, start in enumerate(hidx):
        m = HEADER.match(P[start].strip())
        lo = int(m.group(1)); hdr_hi = int(m.group(2)) if m.group(2) else lo
        cap = (los[hi_i + 1] - 1) if hi_i + 1 < len(hidx) else sura_total
        hi = max(hdr_hi, cap, lo)
        end = hidx[hi_i + 1] if hi_i + 1 < len(hidx) else len(P)
        body = [t for t in P[start + 1:end] if t.strip()]
        if hi <= lo:  # одиночный аят (следующая секция сразу за ним)
            _put(out, lo, "\n\n".join(body))
            continue
        # диапазон: дробим по арабским леммам
        cur = lo
        first_ar = True  # вводная (полнодиапазонная) цитата всегда идёт в аят lo
        for t in body:
            if is_arabic(t):
                frag = norm_ar(t)
                if first_ar:
                    first_ar = False
                    _put(out, cur, t)
                    continue
                if len(frag) >= 4:
                    hit = None
                    # ищем аят из [cur..hi], чьи слова содержат фрагмент (или наоборот)
                    for a in range(cur, hi + 1):
                        c = canon.get(a, "")
                        if c and (frag[:24] in c or c[:24] in frag or frag in c):
                            hit = a; break
                    if hit is None:  # вдруг назад (перекрёстная цитата этого же диапазона)
                        for a in range(lo, hi + 1):
                            c = canon.get(a, "")
                            if c and frag[:24] in c:
                                hit = a; break
                    if hit is not None:
                        cur = hit
            _put(out, cur, t)
    return out, len(hidx)


def _put(out, ayah, text):
    text = text.strip()
    if not text:
        return
    k = str(ayah)
    out[k] = (out[k] + "\n\n" + text) if k in out else text


def main():
    only = None
    if "--sura" in sys.argv:
        only = int(sys.argv[sys.argv.index("--sura") + 1])
    mono = {}
    for num in sorted(SURAS):
        if only and num != only:
            continue
        sd, nsec = convert_sura(num)
        mono[str(num)] = sd
        aykeys = sorted(int(k) for k in sd if k != "0")
        total = len([a for a in CLEAN.get(str(num), {})])
        filled = len(aykeys)
        gaps = [a for a in range(1, (max(aykeys) if aykeys else 0) + 1) if a not in aykeys]
        print(f"сура {num:>2} {SURAS[num]:<10}: {nsec} секций → аятов с текстом {filled}/{total}"
              f"  intro={'да' if '0' in sd else 'нет'}  пропуски={gaps[:15]}{'…' if len(gaps)>15 else ''}")

    if only:  # тестовый прогон — не пишем в данные
        json.dump(mono, open(os.path.join(ROOT, "scratch_qurtubi.json"), "w"),
                  ensure_ascii=False, indent=1)
        print("\n[тест] записан scratch_qurtubi.json (данные НЕ тронуты)")
        return

    # запись: монолит (build-side) + чанки (r2-data) + монолит r2
    json.dump(mono, open(os.path.join(DATA_TAF, ID + ".json"), "w"), ensure_ascii=False)
    json.dump(mono, open(os.path.join(R2_TAF, ID + ".json"), "w"), ensure_ascii=False)
    outdir = os.path.join(R2_TAF, ID)
    os.makedirs(outdir, exist_ok=True)
    suras = sorted(int(s) for s in mono)
    for s in suras:
        json.dump(mono[str(s)], open(os.path.join(outdir, f"{s}.json"), "w"),
                  ensure_ascii=False, separators=(",", ":"))
    json.dump(suras, open(os.path.join(outdir, "index.json"), "w"), separators=(",", ":"))
    print(f"\nЗаписано: {len(suras)} сур → {ID} (data + r2-data)")


if __name__ == "__main__":
    main()
