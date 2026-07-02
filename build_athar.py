#!/usr/bin/env python3
"""
Извлекает по-аятный тафсир ОТДЕЛЬНОГО учёного-саляфа из свода
`mawsua_masur` («Аль-Мавсу'а фи-т-тафсир аль-ма'сур»).

Идея: в Мавсу'а каждый аят сопровождается пронумерованными асарами
(`NNN- عن <учёный> -من طريق <иснад>- … [[تخريج]]. (ссылка)`), сквозная
нумерация через всю книгу. Учёный, которому приписан асар, стоит сразу после
первого `عن`/`قال` (с возможной ведущей `و` — со-передатчик). Помимо асаров есть
СНОСКИ МУХАККИКА (отдельная нумерация `N <текст>`, ссылаются на Ибн Атыйю,
ат-Табари, Ибн Кайима, Ибн Таймию) и заголовки/преамбулы аята.

Чтобы получить «Тафсир <учёного>», оставляем:
  • асары, чья ПЕРВИЧНАЯ приписка = этот учёный;
  • ВСЕ сноски-тафсиры мухаккика;
  • заголовки/преамбулы аятов.
и выкидываем асары прочих передатчиков.

Источник — локальное зеркало R2 (`r2-data/tafsirs/mawsua_masur/<sura>.json`).
Результат — монолит `data/tafsirs/<id>.json`; дальше как обычно:
  python3 split.py <id> && python3 build_index.py <id>
  python3 compute_fill.py && python3 build_coverage.py && python3 sync_config.py

Использование:
  python3 build_athar.py --stats           # таблица: сколько асаров у каждого
  python3 build_athar.py ibn_abbas         # собрать монолит для id из реестра
  python3 build_athar.py ibn_abbas mujahid # несколько сразу
"""

import json, os, re, sys, glob

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "r2-data", "tafsirs", "mawsua_masur")
OUT = os.path.join(ROOT, "data", "tafsirs")

# ── Реестр учёных ─────────────────────────────────────────────────────────
# match   — префиксы первичной приписки, считающиеся ЭТИМ учёным;
# exclude — префиксы, которые надо исключить (омонимичные приписки).
SCHOLARS = {
    "ibn_abbas": {"name": "Тафсир Ибн Аббаса", "nameAr": "تفسير ابن عباس",
                  "match": ["عبد الله بن عباس", "عبد الله بن العباس", "عبدالله بن عباس", "ابن عباس"],
                  "exclude": ["عكرمة"]},  # عكرمة مولى ابن عباس — это Икрима, не Ибн Аббас
    "mujahid":   {"name": "Тафсир Муджахида", "nameAr": "تفسير مجاهد",
                  "match": ["مجاهد بن جبر", "مجاهد"], "exclude": []},
    "qatada":    {"name": "Тафсир Катады", "nameAr": "تفسير قتادة",
                  "match": ["قتادة بن دعامة", "قتادة"], "exclude": []},
    "ikrima":    {"name": "Тафсир Икримы", "nameAr": "تفسير عكرمة",
                  "match": ["عكرمة"], "exclude": []},
    "hasan":     {"name": "Тафсир аль-Хасана аль-Басри", "nameAr": "تفسير الحسن البصري",
                  "match": ["الحسن البصري", "الحسن"], "exclude": []},
    "suddi":     {"name": "Тафсир ас-Судди", "nameAr": "تفسير السدي",
                  "match": ["إسماعيل السدي", "إسماعيل السُّدِّيّ", "السدي", "السُّدِّيّ"], "exclude": []},
    "saeed":     {"name": "Тафсир Саида ибн Джубайра", "nameAr": "تفسير سعيد بن جبير",
                  "match": ["سعيد بن جبير"], "exclude": []},
    "dahhak":    {"name": "Тафсир ад-Даххака", "nameAr": "تفسير الضحاك",
                  "match": ["الضحاك بن مزاحم", "الضحاك"], "exclude": []},
    "ibn_masud": {"name": "Тафсир Ибн Масуда", "nameAr": "تفسير ابن مسعود",
                  "match": ["عبد الله بن مسعود", "ابن مسعود"], "exclude": []},
    "ata":       {"name": "Тафсир Аты ибн Аби Рабаха", "nameAr": "تفسير عطاء",
                  "match": ["عطاء بن أبي رباح", "عطاء"], "exclude": ["عطاء الخراساني", "عطاء الخُراسانيّ", "عطية"]},
    "muqatil":   {"name": "Тафсир Мукатиля ибн Сулеймана", "nameAr": "تفسير مقاتل بن سليمان",
                  "match": ["مقاتل بن سليمان"], "exclude": []},
}

# ── Разбор разметки ───────────────────────────────────────────────────────
foot_rx = re.compile(r'\[\[.*?\]\]', re.S)          # инлайн-сноска (تخريج)
asar_head = re.compile(r'^([٠-٩]+)\s*-\s*')          # NNN-  (асар)
note_head = re.compile(r'^([٠-٩]+)\s+\S')            # NNN␣  (сноска мухаккика)
_DIAC = re.compile("[ؐ-ًؚ-ٰٟۖ-ۜ۟-۪ۨ-ۭ]")


def _norm(s):
    s = _DIAC.sub("", s).replace("ـ", "")
    s = re.sub("[أإآٱ]", "ا", s)
    return re.sub(r"\s+", " ", s).strip()


def primary_name(body):
    s = re.sub(r'^و\s*', '', body.strip())                       # ведущая و
    s = re.sub(r'^(?:عن|قال|قالت|عَنْ|عَن)\s+', '', s)            # عن / قال
    s = s.lstrip('[').strip()
    m = re.match(r'(.+?)\s*(?:[-–—]\s*من\s*طريق|[-–—]\s*كما|،|:|\[|﴿|$)', s)
    return _norm(m.group(1) if m else s[:40])


def matcher(spec):
    match = [_norm(x) for x in spec["match"]]
    excl = [_norm(x) for x in spec["exclude"]]
    def hit(name):
        if any(name.startswith(x) for x in excl):
            return False
        return any(name.startswith(x) for x in match)
    return hit


def filter_text(t, hit):
    masks = []
    masked = foot_rx.sub(lambda m: (masks.append(m.group(0)) or f"\x00{len(masks)-1}\x00"), t)
    kept = []
    n_total = n_kept = 0
    for p in re.split(r'\n\s*\n', masked):
        if not p.strip():
            continue
        s = p.lstrip()
        if asar_head.match(s):
            n_total += 1
            if hit(primary_name(asar_head.sub('', s, count=1))):
                n_kept += 1
                kept.append(p)
        else:                       # сноска мухаккика или заголовок/преамбула — оставляем
            kept.append(p)
    out = "\n\n".join(kept)
    out = re.sub(r'\x00(\d+)\x00', lambda m: masks[int(m.group(1))], out)
    return out, n_total, n_kept


def load_src():
    files = sorted(glob.glob(os.path.join(SRC, "[0-9]*.json")),
                   key=lambda f: int(re.search(r'(\d+)\.json', f).group(1)))
    return {int(re.search(r'(\d+)\.json', f).group(1)): json.load(open(f, encoding="utf-8")) for f in files}


def build(sid, data):
    spec = SCHOLARS[sid]
    hit = matcher(spec)
    mono = {}
    n_total = n_kept = n_ayat = 0
    for s in sorted(data):
        sd = {}
        for ay, t in data[s].items():
            out, tot, kept = filter_text(t, hit)
            n_total += tot
            n_kept += kept
            # оставляем аят, если в нём остались асары этого учёного
            # (только заголовки/сноски без единого асара — пропускаем)
            if kept > 0 and out.strip():
                sd[ay] = out.strip()
        if sd:
            mono[str(s)] = sd
            n_ayat += len(sd)
    dst = os.path.join(OUT, sid + ".json")
    os.makedirs(OUT, exist_ok=True)
    with open(dst, "w", encoding="utf-8") as f:
        f.write(json.dumps(mono, ensure_ascii=False, indent=2))
    mb = os.path.getsize(dst) / 1048576
    print(f"  ✓ {sid}: асаров {n_kept}/{n_total}, аятов {n_ayat}, {len(mono)} сур "
          f"→ {dst} ({mb:.1f} МБ)")


def stats(data):
    hits = {sid: matcher(spec) for sid, spec in SCHOLARS.items()}
    cnt = {sid: 0 for sid in SCHOLARS}
    total = 0
    for s in data:
        for ay, t in data[s].items():
            masked = foot_rx.sub(lambda m: "X", t)
            for p in re.split(r'\n\s*\n', masked):
                ps = p.lstrip()
                if not asar_head.match(ps):
                    continue
                total += 1
                nm = primary_name(asar_head.sub('', ps, count=1))
                for sid, hit in hits.items():
                    if hit(nm):
                        cnt[sid] += 1
    print(f"Всего асаров: {total}\n")
    print(f"{'id':12} {'учёный':32} {'асаров':>8}  доля")
    for sid, c in sorted(cnt.items(), key=lambda x: -x[1]):
        print(f"{sid:12} {SCHOLARS[sid]['name']:32} {c:8d}  {100*c/total:4.1f}%")


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    data = load_src()
    if args[0] == "--stats":
        stats(data)
        return
    for sid in args:
        if sid not in SCHOLARS:
            print(f"  ✗ нет в реестре: {sid} (есть: {', '.join(SCHOLARS)})")
            continue
        build(sid, data)


if __name__ == "__main__":
    main()
