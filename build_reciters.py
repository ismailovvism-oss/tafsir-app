#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_reciters.py — собрать список чтецов everyayah в config.json → audio.reciters.

Источник (сырьё, gitignored): data/_sources/everyayah_recitations.js — канонический
список everyayah.com (скачивается вручную: curl https://everyayah.com/data/recitations.js).
Формат: {"ayahCount":[...], "1":{"subfolder","name","bitrate"}, ...} — по одной
записи на (чтец × битрейт).

Что делает:
  • дедуплицирует по чтецу, берёт ЛУЧШИЙ битрейт (128 предпочтительнее — дефолт
    everyayah и самый полный; далее 192/64/…);
  • присваивает стабильный человекочитаемый id и русское имя из RU-карты ниже;
  • флаг recommended → чтец виден в наборе «из коробки»; остальные скрыты по
    умолчанию (приложение сидит tl_recHidden не-рекомендованными при первом
    запуске; список скрытых — опт-аут, поэтому будущие новые чтецы видны сами);
  • пишет массив в data/config.json (audio.reciters), audio.default оставляет
    "shatri" (id закреплён, чтобы не сломать сохранённый выбор пользователя).

После: python3 sync_config.py  (зеркало config.js).
Идемпотентно.
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC  = os.path.join(ROOT, "data", "_sources", "everyayah_recitations.js")
CFG  = os.path.join(ROOT, "data", "config.json")

# Предпочтение битрейтов (первый доступный выигрывает). 128 — дефолт everyayah.
BITRATE_PREF = ["128kbps", "192kbps", "64kbps", "48kbps", "46kbps", "40kbps",
                "32kbps", "16kbps"]

def bnorm(b):  # "64Kbps" → "64kbps"
    return (b or "").lower()

# ── Карта: имя everyayah → (id, русское имя, арабское имя|"", рекомендован) ──
# id — стабильный ключ (сохраняется в tl_mediaReciter); менять нельзя после релиза.
# nameAr необязателен (для рекомендованных заполнен). recommended=True → в наборе
# по умолчанию. Не перечисленные чтецы попадают с авто-id и англ. именем, скрыты.
RU = {
  # ── Рекомендованные (Хафс, мурат­таль) — популярны у русскоязычных ──
  "Alafasy":                        ("alafasy",  "Мишари аль-Афаси",       "مشاري راشد العفاسي", True),
  "Abu Bakr Ash-Shaatree":          ("shatri",   "Абу Бакр аш-Шатри",      "أبو بكر الشاطري",     True),
  "Abdurrahmaan As-Sudais":         ("sudais",   "Абдуррахман ас-Судайс",  "عبد الرحمن السديس",  True),
  "Saood bin Ibraaheem Ash-Shuraym":("shuraim",  "Сауд аш-Шурайм",         "سعود الشريم",        True),
  "Maher Al Muaiqly":               ("muaiqly",  "Махир аль-Муайкли",      "ماهر المعيقلي",      True),
  "Husary":                         ("husary",   "Махмуд аль-Хусари",      "محمود خليل الحصري",  True),
  "Minshawy Murattal":              ("minshawi", "Мухаммад аль-Миншави",   "محمد صديق المنشاوي", True),
  "Abdul Basit Murattal":           ("basit",    "Абдуль-Басит (мурат­таль)","عبد الباسط عبد الصمد", True),
  "Muhammad Ayyoub":                ("ayyoub",   "Мухаммад Айюб",          "محمد أيوب",          True),
  "Hudhaify":                       ("hudhaify", "Али аль-Хузайфи",        "علي الحذيفي",        True),
  "Ali Jaber":                      ("alijaber", "Али Джабир",             "علي جابر",           True),
  "Nasser_Alqatami":                ("qatami",   "Насер аль-Катами",       "ناصر القطامي",       True),
  "Yasser_Ad-Dussary":              ("dussary",  "Ясир ад-Дусари",         "ياسر الدوسري",       True),
  "Abdullaah 3awwaad Al-Juhaynee":  ("juhani",   "Абдулла аль-Джухани",    "عبد الله الجهني",    True),
  "Fares Abbad":                    ("fares",    "Фарис Аббад",            "فارس عباد",          True),
  "Ahmed Ibn Ali Al Ajamy":         ("ajamy",    "Ахмад аль-Аджами",       "أحمد العجمي",        True),
  # ── Прочие (скрыты по умолчанию; можно включить в наборе) ──
  "Abdul Basit Mujawwad":           ("basit_muj","Абдуль-Басит (муджаввад)","عبد الباسط عبد الصمد", False),
  "Minshawy Mujawwad":              ("minshawi_muj","Мухаммад аль-Миншави (муджаввад)","محمد صديق المنشاوي", False),
  "Husary Mujawwad":                ("husary_muj","Махмуд аль-Хусари (муджаввад)","محمود خليل الحصري", False),
  "Husary (Muallim)":               ("husary_mua","Махмуд аль-Хусари (муаллим)","محمود خليل الحصري", False),
  "Abdullah Basfar":                ("basfar",   "Абдулла Басфар",         "عبد الله بصفر",      False),
  "Abdullah Matroud":               ("matroud",  "Абдулла Матруд",         "عبد الله المطرود",   False),
  "Hani Rifai":                     ("rifai",    "Хани ар-Рифаи",          "هاني الرفاعي",       False),
  "Mohammad al Tablaway":           ("tablaway", "Мухаммад ат-Таблави",    "محمد الطبلاوي",      False),
  "Muhammad Jibreel":               ("jibreel",  "Мухаммад Джибриль",      "محمد جبريل",         False),
  "Ibrahim Akhdar":                 ("akhdar",   "Ибрахим аль-Ахдар",      "إبراهيم الأخضر",     False),
  "Ghamadi":                        ("ghamadi",  "Саад аль-Гамиди",        "سعد الغامدي",        False),
  "Salah Al Budair":                ("budair",   "Салах аль-Будайр",       "صلاح البدير",        False),
  "Salaah AbdulRahman Bukhatir":    ("bukhatir", "Салах Бухатир",          "صلاح بو خاطر",       False),
  "Khalefa Al-Tunaiji":             ("tunaiji",  "Халифа ат-Тунайджи",     "",                   False),
  "Khalid Abdullah al-Qahtanee":    ("qahtani",  "Халид аль-Кахтани",      "خالد القحطاني",      False),
  "Ahmed Neana":                    ("neana",    "Ахмад Неана",            "",                   False),
  "Akram Al Alaqimy":               ("alaqimy",  "Акрам аль-Алякими",      "",                   False),
  "Ayman Sowaid":                   ("sowaid",   "Айман Сувайд",           "أيمن سويد",          False),
  "Aziz Alili":                     ("alili",    "Азиз Алили",             "",                   False),
  "Fares Abbad ":                   ("fares2",   "Фарис Аббад",            "",                   False),
  "Mahmoud Ali Al-Banna":           ("banna",    "Махмуд аль-Банна",       "محمود علي البنا",    False),
  "Mustafa Ismail":                 ("mustafa_ismail","Мустафа Исмаил",    "مصطفى إسماعيل",      False),
  "Muhsin Al Qasim":                ("qasim",    "Мухсин аль-Касим",       "محسن القاسم",        False),
  "Muhammad AbdulKareem":           ("abdulkareem","Мухаммад Абдулькарим", "",                   False),
  "Yaser Salamah":                  ("salamah",  "Ясир Салама",            "",                   False),
  "Yaser Salamah ":                 ("salamah2", "Ясир Салама",            "",                   False),
  "Menshawi":                       ("menshawi_lo","Аль-Миншави (низкий битрейт)","",            False),
  "AbdulSamad QuranExplorer.Com":   ("abdulsamad","Абдус-Самад",           "",                   False),
  "Ahmed ibn Ali al-Ajamy KetabAllah.Net":("ajamy_ka","Ахмад аль-Аджами (KetabAllah)","",       False),
  "Ahmed ibn Ali al-Ajamy QuranExplorer.Com":("ajamy_qe","Ахмад аль-Аджами (QuranExplorer)","", False),
  "Ali_Hajjaj_AlSuesy":             ("suesy",    "Али аль-Хаджадж ас-Суэси","",                  False),
  "Sahl_Yassin":                    ("sahl",     "Сахль Ясин",             "",                   False),
  "Balayev":                        ("balayev",  "Балаев",                 "",                   False),
  # ── qira'at / переводы / прочие языки (скрыты) ──
  "(Warsh) Abdul Basit":            ("warsh_basit","Абдуль-Басит (Варш)",  "عبد الباسط — ورش",   False),
  "(Warsh) Ibrahim Al-Dosary":      ("warsh_dosary","Ибрахим ад-Дусари (Варш)","",               False),
  "(Warsh) Yassin Al-Jazaery":      ("warsh_jazaery","Ясин аль-Джазаири (Варш)","",              False),
  "(English) Translated by Sahih International Recited by Ibrahim Walk":
                                    ("en_sahih", "English — Sahih International (Ibrahim Walk)","", False),
  "MultiLanguage/Basfar Walk":      ("basfar_walk","Basfar + English (Walk)","",                 False),
  "(Persian) Translated by Fooladvand Recited by Hedayatfar":
                                    ("fa_foolad","فارسی — Fooladvand (Hedayatfar)","",           False),
  "(Persian) Translated by Makarem Recited by Kabiri":
                                    ("fa_makarem","فارسی — Makarem (Kabiri)","",                 False),
  "Karim Mansoori (Iran)":          ("mansoori", "Карим Мансури",          "",                   False),
  "Parhizgar_64Kbps":               ("parhizgar","Пархизгар",              "",                   False),
  "(Urdu) Shamshad Ali Khan":       ("ur_shamshad","اردو — Shamshad Ali Khan","",                False),
  "Farhat Hashmi (Urdu word for word translation)":
                                    ("ur_farhat","اردو — Farhat Hashmi (пословно)","",           False),
  "Besim Korkut (Bosnian)":         ("bs_korkut","Bosanski — Besim Korkut","",                   False),
}

# Чтецы на ДРУГИХ языках (не арабский/английский) — не включаем вовсе.
# Арабский (в т.ч. кираат Варш) и английский (перевод Sahih Intl) оставляем.
DROP_IDS = {"fa_foolad", "fa_makarem", "mansoori", "parhizgar",
            "ur_shamshad", "ur_farhat", "bs_korkut"}

def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:32] or "reciter"

def main():
    if not os.path.exists(SRC):
        sys.exit("Нет сырья: %s\nСкачай: curl -s https://everyayah.com/data/recitations.js "
                 "-o data/_sources/everyayah_recitations.js" % SRC)
    raw = json.load(open(SRC, encoding="utf-8"))
    variants = [raw[k] for k in raw if k != "ayahCount"]

    # группировка по имени; выбор лучшего битрейта
    by_name = {}
    for v in variants:
        by_name.setdefault(v["name"], []).append(v)
    def best(vs):
        def rank(v):
            b = bnorm(v["bitrate"])
            return BITRATE_PREF.index(b) if b in BITRATE_PREF else len(BITRATE_PREF)
        return sorted(vs, key=rank)[0]

    reciters, seen_ids, unmapped = [], set(), []
    for name in by_name:
        v = best(by_name[name])
        m = RU.get(name)
        if m:
            rid, ru, ar, rec = m
        else:
            rid, ru, ar, rec = slug(name), name, "", False
            unmapped.append(name)
        if rid in DROP_IDS:            # другой язык — пропускаем
            continue
        if rid in seen_ids:            # защита от коллизий id
            rid = rid + "_" + slug(v["subfolder"])[:8]
        seen_ids.add(rid)
        r = {"id": rid, "name": ru, "cdn": "everyayah",
             "subdir": v["subfolder"], "type": "audio_cdn",
             "bitrate": bnorm(v["bitrate"])}
        if ar: r["nameAr"] = ar
        if rec: r["recommended"] = True
        reciters.append(r)

    # сортировка: рекомендованные первыми (в порядке RU-карты), затем прочие по имени
    order = {name: i for i, name in enumerate(RU)}
    reciters.sort(key=lambda r: (0 if r.get("recommended") else 1,
                                 order.get(_orig_name(r, by_name), 999),
                                 r["name"]))

    cfg = json.load(open(CFG, encoding="utf-8"))
    cfg.setdefault("audio", {})
    cfg["audio"]["default"] = "shatri"
    cfg["audio"]["reciters"] = reciters
    json.dump(cfg, open(CFG, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    rec_n = sum(1 for r in reciters if r.get("recommended"))
    print("Чтецов: %d (рекомендованных: %d, скрытых по умолчанию: %d)"
          % (len(reciters), rec_n, len(reciters) - rec_n))
    if unmapped:
        print("Без русского имени (%d): %s" % (len(unmapped), ", ".join(unmapped)))
    print("Дальше: python3 sync_config.py")

# восстановить оригинальное имя everyayah для сортировки (по subdir)
def _orig_name(r, by_name):
    for name, vs in by_name.items():
        if any(v["subfolder"] == r["subdir"] for v in vs):
            return name
    return r["name"]

if __name__ == "__main__":
    main()
