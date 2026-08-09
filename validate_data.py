#!/usr/bin/env python3
"""
Smoke-проверка целостности данных перед публикацией. Только чтение, ничего не
пишет. Возвращает код 1, если найдены ошибки (удобно для чеклиста/CI).

Проверяет:
  - config.json валиден; config.js — точное зеркало config.json;
  - каждый источник: монолит .json, чанки по сурам совпадают с index.json и с
    соответствующими разделами монолита, поисковый индекс на месте (для
    текстовых), поле fill совпадает с реальностью;
  - скан-источник (kind:image): каталог imgdir существует;
  - QPC: meta.pages страниц-чанков и шрифтов, 114 сур;
  - word-by-word: words/ и morph/ имеют одинаковый набор сур.

Запуск:  python3 validate_data.py
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
R2DATA = os.path.join(ROOT, "r2-data")  # локальное зеркало данных, живущих на R2
TOTAL = 6236  # аятов в Коране (стандартная нумерация)

errors = []
warnings = []


def err(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


def files_equal(first, second):
    """Byte-for-byte comparison without loading large R2 monoliths into memory."""
    if os.path.getsize(first) != os.path.getsize(second):
        return False
    with open(first, "rb") as left, open(second, "rb") as right:
        while True:
            a = left.read(1024 * 1024)
            b = right.read(1024 * 1024)
            if a != b:
                return False
            if not a:
                return True


def mono_path(tid):
    """Монолит источника: сначала data/, иначе зеркало r2-data/ (источники с dataBase)."""
    for base in (os.path.join(DATA, "tafsirs"), os.path.join(R2DATA, "tafsirs")):
        p = os.path.join(base, tid + ".json")
        if os.path.isfile(p):
            return p
    return None


def count_real(tid):
    """Реальные (не-«※») аяты монолита — та же логика, что в compute_fill.py."""
    path = mono_path(tid)
    if path is None:
        return None
    data = json.load(open(path, encoding="utf-8"))
    n = 0
    for sk, s in data.items():
        if sk == "0":            # «сура 0» = мукаддима книги, не аят Корана
            continue
        for ak, txt in s.items():
            if ak == "0":        # ключ "0" внутри суры = вступление к суре, не аят
                continue
            t = (txt or "").strip()
            if t and not t.startswith("※"):
                n += 1
    return n


def check_configs():
    cfg_json = os.path.join(DATA, "config.json")
    cfg_js = os.path.join(DATA, "config.js")
    try:
        cfg = json.load(open(cfg_json, encoding="utf-8"))
    except Exception as e:
        err(f"config.json не парсится: {e}")
        return None
    try:
        txt = open(cfg_js, encoding="utf-8").read()
        m = re.match(r"\s*window\.TL_CONFIG=(.*?);\s*$", txt, re.S)
        obj = json.loads(m.group(1))
    except Exception as e:
        err(f"config.js не парсится: {e}")
        return cfg
    if cfg != obj:
        err("config.js не совпадает с config.json — запусти sync_config.py")
    return cfg


def check_containers(cfg):
    """Контейнеры (config.containers) — узлы-группы каталога, а не источники.

    Сами не читаются и в tafsirs не лежат, поэтому проверяем только целостность
    связей: у ребёнка parent обязан существовать (источник ИЛИ контейнер),
    id контейнера не должен совпадать с id источника, а `about: true` — иметь
    файл паспорта, иначе кнопка ℹ откроет пустоту.
    """
    conts = {c["id"]: c for c in cfg.get("containers", [])}
    ids = {t["id"] for t in cfg["tafsirs"]}
    for cid, c in conts.items():
        if cid in ids:
            err(f"[{cid}] id контейнера совпадает с id источника")
        if c.get("about") and not os.path.exists(os.path.join(DATA, "about", f"{cid}.md")):
            err(f"[{cid}] about: true, но нет data/about/{cid}.md")
        if not any(t.get("parent") == cid for t in cfg["tafsirs"]):
            warn(f"[{cid}] контейнер без единого источника внутри")
    for t in cfg["tafsirs"]:
        p = t.get("parent")
        if p and p not in ids and p not in conts:
            err(f"[{t['id']}] parent «{p}» не найден ни среди источников, ни среди контейнеров")


def check_source(t):
    tid = t["id"]
    kind = t.get("kind", "")

    if kind == "image":
        imgdir = t.get("imgdir")
        if not imgdir:
            err(f"[{tid}] kind:image без поля imgdir")
        elif not os.path.isdir(os.path.join(DATA, imgdir)):
            err(f"[{tid}] каталог сканов не найден: data/{imgdir}")
        return

    # Источник с dataBase обслуживается с R2, поэтому его зеркало проверяем
    # первым. Иначе старый локальный каталог может скрыть свежие R2-чанки.
    on_r2 = bool(t.get("dataBase"))
    bases = [R2DATA, DATA] if on_r2 else [DATA]

    def find(*rel):
        for b in bases:
            p = os.path.join(b, *rel)
            if os.path.exists(p):
                return p
        return None

    # монолит
    mono = find("tafsirs", tid + ".json")
    if mono is None:
        if on_r2:
            warn(f"[{tid}] данные на R2, локального зеркала r2-data нет — проверка пропущена")
        else:
            err(f"[{tid}] нет монолита data/tafsirs/{tid}.json")
        return
    local_mono = os.path.join(DATA, "tafsirs", tid + ".json")
    r2_mono = os.path.join(R2DATA, "tafsirs", tid + ".json")
    if on_r2 and os.path.isfile(local_mono) and os.path.isfile(r2_mono):
        if not files_equal(local_mono, r2_mono):
            err(f"[{tid}] локальный и R2-монолиты различаются")

    try:
        monolith = json.load(open(mono, encoding="utf-8"))
    except Exception as e:
        err(f"[{tid}] монолит не парсится: {e}")
        return

    # чанки по сурам
    chunk_dir = find("tafsirs", tid)
    idx_path = chunk_dir and os.path.join(chunk_dir, "index.json")
    if chunk_dir is None:
        err(f"[{tid}] нет каталога чанков tafsirs/{tid}/ (ни в data/, ни в r2-data/)")
    elif not os.path.isfile(idx_path):
        err(f"[{tid}] нет index.json в каталоге чанков")
    else:
        surahs = json.load(open(idx_path, encoding="utf-8"))
        missing = [s for s in surahs
                   if not os.path.isfile(os.path.join(chunk_dir, f"{s}.json"))]
        if missing:
            err(f"[{tid}] index.json ссылается на отсутствующие чанки: {missing[:10]}")
        mismatched = []
        for sura in surahs:
            chunk_path = os.path.join(chunk_dir, f"{sura}.json")
            if not os.path.isfile(chunk_path):
                continue
            try:
                chunk = json.load(open(chunk_path, encoding="utf-8"))
            except Exception as e:
                err(f"[{tid}] чанк {sura}.json не парсится: {e}")
                continue
            if chunk != monolith.get(str(sura)):
                mismatched.append(str(sura))
        if mismatched:
            err(f"[{tid}] чанки не совпадают с монолитом: {mismatched[:10]}")
        indexed = {str(sura) for sura in surahs}
        unindexed = [
            sura for sura, value in monolith.items()
            if sura != "0" and value and sura not in indexed
        ]
        if unindexed:
            err(f"[{tid}] непустые суры отсутствуют в index.json: {unindexed[:10]}")

    # поисковый индекс
    if find("index", tid + ".json") is None:
        err(f"[{tid}] нет поискового индекса index/{tid}.json (ни в data/, ни в r2-data/)")

    # fill
    n = count_real(tid)
    if n is not None:
        expect = round(min(1.0, n / TOTAL), 4)
        if abs(t.get("fill", -1) - expect) > 1e-4:
            err(f"[{tid}] fill={t.get('fill')} не совпадает с фактом {expect} "
                f"({n} реальных аятов) — запусти compute_fill.py")


def check_qpc():
    base = os.path.join(DATA, "qpc", "v1")
    meta_path = os.path.join(base, "meta.json")
    if not os.path.isfile(meta_path):
        err("QPC: нет data/qpc/v1/meta.json")
        return
    meta = json.load(open(meta_path, encoding="utf-8"))
    pages = meta.get("pages", 0)
    si = meta.get("surahIndex", [])
    if len(si) != 114:
        err(f"QPC: surahIndex = {len(si)} (ожидалось 114)")
    page_chunks = len([f for f in os.listdir(os.path.join(base, "page")) if f.endswith(".json")])
    surah_chunks = len([f for f in os.listdir(os.path.join(base, "surah")) if f.endswith(".json")])
    fonts = os.path.join(ROOT, "fonts", "qpc-v1")
    n_fonts = len([f for f in os.listdir(fonts) if f.endswith(".woff2")]) if os.path.isdir(fonts) else 0
    if page_chunks != pages:
        err(f"QPC: страниц-чанков {page_chunks}, в meta.pages {pages}")
    if surah_chunks != 114:
        err(f"QPC: сура-чанков {surah_chunks} (ожидалось 114)")
    if n_fonts != pages:
        err(f"QPC: шрифтов {n_fonts}, страниц {pages}")


def check_wbw():
    base = os.path.join(DATA, "wbw")
    wd = os.path.join(base, "words")
    md = os.path.join(base, "morph")
    if not (os.path.isdir(wd) and os.path.isdir(md)):
        err("wbw: нет каталогов words/ и/или morph/")
        return
    words = {f for f in os.listdir(wd) if f.endswith(".json")}
    morph = {f for f in os.listdir(md) if f.endswith(".json")}
    if words != morph:
        only_w = sorted(words - morph)
        only_m = sorted(morph - words)
        err(f"wbw: words/ и morph/ расходятся (только в words: {only_w[:5]}, только в morph: {only_m[:5]})")
    if len(words) != 114:
        warn(f"wbw: {len(words)} сур со словами (ожидалось 114)")


def check_coverage(cfg):
    """coverage.json: набор источников и счётчики «n» совпадают с фактом; есть зеркало."""
    cov_path = os.path.join(DATA, "coverage.json")
    if not os.path.isfile(cov_path):
        err("нет data/coverage.json — запусти build_coverage.py")
        return
    cov = json.load(open(cov_path, encoding="utf-8"))
    txt_ids = {t["id"]: t for t in cfg["tafsirs"]
               if t.get("kind") in ("tafsir", "translation")}
    expected = {tid for tid, t in txt_ids.items() if (count_real(tid) or 0) > 0}
    got = set(cov.get("sources", {}))
    # R2-источник без локального зеркала: запись в coverage легитимна, хоть данных и нет
    unverifiable = {tid for tid in got - expected
                    if tid in txt_ids and txt_ids[tid].get("dataBase")
                    and count_real(tid) is None}
    for tid in sorted(unverifiable):
        warn(f"[{tid}] в coverage, но данных нет ни в data/, ни в r2-data/ — n не сверить")
    if expected != got - unverifiable:
        err(f"coverage.json расходится с источниками (нет: {sorted(expected-got)[:5]}, "
            f"лишние: {sorted(got-unverifiable-expected)[:5]}) — запусти build_coverage.py")
    for tid, src in cov.get("sources", {}).items():
        n = count_real(tid)
        if n is not None and src.get("n") != n:
            err(f"[{tid}] coverage n={src.get('n')} ≠ факт {n} — запусти build_coverage.py")
    if not os.path.isfile(os.path.join(DATA, "coverage.js")):
        err("нет data/coverage.js (offline-зеркало) — запусти build_coverage.py")


def main():
    cfg = check_configs()
    if cfg:
        for t in cfg["tafsirs"]:
            check_source(t)
        check_containers(cfg)
        check_coverage(cfg)
        print(f"Источников проверено: {len(cfg['tafsirs'])}"
              + (f", контейнеров: {len(cfg['containers'])}" if cfg.get("containers") else ""))
    check_qpc()
    check_wbw()

    for w in warnings:
        print("  ⚠ " + w)
    if errors:
        print(f"\n✗ Ошибок: {len(errors)}")
        for e in errors:
            print("  ✗ " + e)
        sys.exit(1)
    print("\n✓ Все проверки пройдены.")


if __name__ == "__main__":
    main()
