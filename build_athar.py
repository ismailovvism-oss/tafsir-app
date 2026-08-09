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
    # `out` — id ФАЙЛА, если он отличается от ключа реестра. У Ибн Аббаса ключ
    # исторический (`ibn_abbas`), но так называется РУССКИЙ перевод; арабская
    # выборка обязана писаться в ibn_abbas_ar, иначе сборка затрёт русский монолит.
    "ibn_abbas": {"name": "Тафсир Ибн Аббаса", "nameAr": "تفسير ابن عباس", "out": "ibn_abbas_ar",
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
    # ── Второй эшелон (перепись свода: у каждого ≥250 асаров) ──────────────
    "yahya_sallam": {"name": "Тафсир Яхьи ибн Салляма", "nameAr": "تفسير يحيى بن سلام",
                     "match": ["يحيى بن سلام"], "exclude": []},
    "ibn_zayd":  {"name": "Тафсир Абд ар-Рахмана ибн Зайда ибн Аслама", "nameAr": "تفسير عبد الرحمن بن زيد بن أسلم",
                  "match": ["عبد الرحمن بن زيد"], "exclude": []},
    "ibn_jurayj":{"name": "Тафсир Ибн Джурайджа", "nameAr": "تفسير ابن جريج",
                  "match": ["عبد الملك ابن جريج", "عبد الملك بن جريج", "ابن جريج"], "exclude": []},
    "abu_hurayra":{"name": "Тафсир Абу Хурайры", "nameAr": "تفسير أبي هريرة",
                  "match": ["أبي هريرة", "أبو هريرة"], "exclude": []},
    "kalbi":     {"name": "Тафсир аль-Кальби", "nameAr": "تفسير الكلبي",
                  "match": ["محمد بن السائب الكلبي", "الكلبي"], "exclude": []},
    "rabi_anas": {"name": "Тафсир ар-Раби ибн Анаса", "nameAr": "تفسير الربيع بن أنس",
                  "match": ["الربيع بن أنس"], "exclude": []},
    "ibn_ishaq": {"name": "Тафсир Ибн Исхака", "nameAr": "تفسير ابن إسحاق",
                  "match": ["محمد بن إسحاق", "ابن إسحاق"], "exclude": []},
    "muqatil_hayyan":{"name": "Тафсир Мукатиля ибн Хайяна", "nameAr": "تفسير مقاتل بن حيان",
                  "match": ["مقاتل بن حيان"], "exclude": []},
    "ali":       {"name": "Тафсир Али ибн Аби Талиба", "nameAr": "تفسير علي بن أبي طالب",
                  "match": ["علي بن أبي طالب"], "exclude": []},   # НЕ «علي بن أبي طلحة» — это путь передачи
    "ibn_umar":  {"name": "Тафсир Ибн Умара", "nameAr": "تفسير ابن عمر",
                  "match": ["عبد الله بن عمر", "ابن عمر"], "exclude": ["عبد الله بن عمرو"]},
    "aisha":     {"name": "Тафсир Аиши", "nameAr": "تفسير عائشة",
                  "match": ["عائشة"], "exclude": []},
    "shabi":     {"name": "Тафсир аш-Шаби", "nameAr": "تفسير الشعبي",
                  "match": ["عامر الشعبي", "الشعبي"], "exclude": []},
    "qurazi":    {"name": "Тафсир Мухаммада ибн Кааба аль-Куразый", "nameAr": "تفسير محمد بن كعب القرظي",
                  "match": ["محمد بن كعب القرظي", "محمد بن كعب"], "exclude": []},
    "nakhai":    {"name": "Тафсир Ибрахима ан-Нахаи", "nameAr": "تفسير إبراهيم النخعي",
                  "match": ["إبراهيم النخعي"], "exclude": []},
    "anas":      {"name": "Тафсир Анаса ибн Малика", "nameAr": "تفسير أنس بن مالك",
                  "match": ["أنس بن مالك", "أنس"], "exclude": []},
    "zayd_aslam":{"name": "Тафсир Зайда ибн Аслама", "nameAr": "تفسير زيد بن أسلم",
                  "match": ["زيد بن أسلم"], "exclude": []},
    "wahb":      {"name": "Тафсир Вахба ибн Мунаббиха", "nameAr": "تفسير وهب بن منبه",
                  "match": ["وهب بن منبه"], "exclude": []},
    "ata_khurasani":{"name": "Тафсир Аты аль-Хурасани", "nameAr": "تفسير عطاء الخراساني",
                  "match": ["عطاء الخراساني"], "exclude": []},
    "thawri":    {"name": "Тафсир Суфьяна ас-Саури", "nameAr": "تفسير سفيان الثوري",
                  "match": ["سفيان الثوري"], "exclude": []},   # «سفيان» без нисбы — неоднозначно, идёт в прочие
    "zuhri":     {"name": "Тафсир аз-Зухри", "nameAr": "تفسير الزهري",
                  "match": ["محمد ابن شهاب الزهري", "ابن شهاب الزهري", "الزهري"], "exclude": []},
    "jabir":     {"name": "Тафсир Джабира ибн Абдуллаха", "nameAr": "تفسير جابر بن عبد الله",
                  "match": ["جابر بن عبد الله"], "exclude": []},
    "abu_aliya": {"name": "Тафсир Абу-ль-Алии", "nameAr": "تفسير أبي العالية",
                  "match": ["أبي العالية", "أبو العالية"], "exclude": []},
    "abu_malik": {"name": "Тафсир Абу Малика аль-Гифари", "nameAr": "تفسير أبي مالك الغفاري",
                  "match": ["أبي مالك غزوان", "أبي مالك الغفاري"], "exclude": []},
    "ibn_musayyab":{"name": "Тафсир Саида ибн аль-Мусаййаба", "nameAr": "تفسير سعيد بن المسيب",
                  "match": ["سعيد بن المسيب"], "exclude": []},
    "abu_saeed": {"name": "Тафсир Абу Саида аль-Худри", "nameAr": "تفسير أبي سعيد الخدري",
                  "match": ["أبي سعيد الخدري"], "exclude": []},
    "umar":      {"name": "Тафсир Умара ибн аль-Хаттаба", "nameAr": "تفسير عمر بن الخطاب",
                  "match": ["عمر بن الخطاب"], "exclude": []},
    # ── Хвост: всё, что не подошло ни одной персоне ────────────────────────
    # Резать дальше нерационально — за порогом ~250 асаров идут сотни имён по
    # десятку записей. Они собраны одним слоем, чтобы объединение слоёв давало
    # ВЕСЬ свод: ни один асар не выпадает.
    "athar_misc":{"name": "Асары прочих передатчиков", "nameAr": "آثار سائر الرواة",
                  "match": [], "exclude": [], "others": True},
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


def others_matcher():
    """Хвост: асар, не подошедший НИ ОДНОЙ персоне реестра.

    Нужен, чтобы объединение слоёв давало свод целиком: за порогом отдельных
    персон остаются сотни имён по десятку записей, резать их поимённо
    нерационально, но и терять нельзя.
    """
    hits = [matcher(sp) for sid, sp in SCHOLARS.items() if not sp.get("others")]
    return lambda name: not any(h(name) for h in hits)


head_rx = re.compile(r'^﴿')                          # заголовок секции аята


def filter_text(t, hit, keep_notes=False):
    """Оставить асары ЭТОГО учёного (+ заголовки их секций).

    Разбор идёт ЭЛЕМЕНТАМИ, а не абзацами: абзац без номера — продолжение
    предыдущего асара или сводки (оценка иснада, вторая часть разбора) и уходит
    вместе с ним; заголовок секции остаётся, только если в секции что-то
    сохранилось, иначе в тексте повисали бы пустые заголовки.

    `keep_notes=False` (по умолчанию): редакционные сводки НЕ включаются — с
    2026-08-09 они вынесены в отдельный слой «Тафсир 5 имамов» (imams5_ar), и
    дублировать их в каждом передатчике значило бы показывать один и тот же
    разбор столько раз, сколько слоёв включено.
    """
    masks = []
    masked = foot_rx.sub(lambda m: (masks.append(m.group(0)) or f"\x00{len(masks)-1}\x00"), t)
    secs = [{"head": [], "items": []}]
    n_total = n_kept = 0
    for p in re.split(r'\n\s*\n', masked):
        s = p.strip()
        if not s:
            continue
        if head_rx.match(s):
            secs.append({"head": [p], "items": []})
        elif asar_head.match(s):
            n_total += 1
            keep = hit(primary_name(asar_head.sub('', s.lstrip(), count=1)))
            n_kept += 1 if keep else 0
            secs[-1]["items"].append(["asar" if keep else "skip", [p]])
        elif note_head.match(s):
            secs[-1]["items"].append(["note", [p]])
        elif secs[-1]["items"]:
            secs[-1]["items"][-1][1].append(p)
        else:
            secs[-1]["head"].append(p)
    want = ("asar", "note") if keep_notes else ("asar",)
    kept = []
    for sec in secs:
        items = [it for it in sec["items"] if it[0] in want]
        if not items and sec["items"]:
            continue                       # секция без нашего материала — и заголовок не нужен
        kept.extend(sec["head"])
        for _, paras in items:
            kept.extend(paras)
    out = "\n\n".join(kept)
    out = re.sub(r'\x00(\d+)\x00', lambda m: masks[int(m.group(1))], out)
    return out, n_total, n_kept


def load_src():
    files = sorted(glob.glob(os.path.join(SRC, "[0-9]*.json")),
                   key=lambda f: int(re.search(r'(\d+)\.json', f).group(1)))
    return {int(re.search(r'(\d+)\.json', f).group(1)): json.load(open(f, encoding="utf-8")) for f in files}


def build(sid, data):
    spec = SCHOLARS[sid]
    hit = others_matcher() if spec.get("others") else matcher(spec)
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
    dst = os.path.join(OUT, spec.get("out", sid) + ".json")
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
