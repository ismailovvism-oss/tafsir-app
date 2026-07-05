#!/usr/bin/env python3
"""Build QPC v4 Tajweed (KFGQPC 1441H colored mushaf) glyph data for the tafsir app.

QUL (qul.tarteel.ai) не отдаёт экспорт раскладки v4 без логина, зато превью
mushaf-layout/19 рендерит каждую страницу серверным HTML со всеми данными:
строки (data-line, классы line--center / line--surah-name / line--bismillah)
и слова (char-word / char-end, data-location="сура:аят:позиция", PUA-глиф).
Скрипт качает 604 превью (кэш сырья в data/_sources/qpc_v4t/, gitignored)
и собирает те же чанки, что build_qpc.py для v1:

  data/qpc/v4t/surah/<s>.json -> {ayah: {"w": [[glyph, page], ...], "e": [glyph, page]|None}}
  data/qpc/v4t/page/<p>.json  -> {"lines": {lineNo: [[glyph,page],...]},
                                  "starts": [{"surah","ayah","line"},...], "center": [...]}
  data/qpc/v4t/meta.json      -> {"pages", "surahStart", "surahIndex", "pageStart",
                                  "juzStart", "rubStart"}

Глифы — PUA-кодпоинты постраничных шрифтов v4-tajweed (цвета таджвида зашиты
в COLR-таблицу шрифта). juz/rub берутся из v1-меты (сура:аят не зависят от
раскладки), страница — пересчитывается по данным v4. Запуск: python3 build_qpc4t.py
Идемпотентен; повторный запуск не перекачивает уже скачанные превью.
"""
import json, os, re, sys, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

BASE = os.path.dirname(os.path.abspath(__file__))
URL = "https://qul.tarteel.ai/resources/mushaf-layout/19?page={p}"
RAW = os.path.join(BASE, "data", "_sources", "qpc_v4t", "pages")
OUT = os.path.join(BASE, "data", "qpc", "v4t")
V1_META = os.path.join(BASE, "data", "qpc", "v1", "meta.json")
ARABIC = os.path.join(BASE, "data", "tafsirs", "_arabic.json")
PAGES = 604

def fetch(p, tries=5):
    path = os.path.join(RAW, f"p{p}.html")
    if os.path.exists(path) and os.path.getsize(path) > 10000:
        return path
    for i in range(tries):
        try:
            req = urllib.request.Request(URL.format(p=p), headers={"User-Agent": "tafsir-app-build"})
            with urllib.request.urlopen(req, timeout=40) as r:
                html = r.read().decode("utf-8")
            # страница должна быть именно та и содержать слова
            if f'id="page-{p}"' not in html or "char-word" not in html:
                raise ValueError(f"page {p}: unexpected html")
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            time.sleep(0.2)
            return path
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(2.0 * (i + 1))

RE_LINE = re.compile(r'<div class="line-container" data-line="(\d+)">')
RE_CLS = re.compile(r'<div class="(line[^"]*)" id="line-\d+">')
RE_CHAR = re.compile(
    r'<span class="char\s+(char-\w+)\s*".*?data-location="(\d+):(\d+):(\d+)".*?<a[^>]*>\s*(\S+)\s*</a>',
    re.S)

def parse_page(p):
    """-> [(lineNo, classes, [(kind, s, a, pos, glyph), ...]), ...]"""
    with open(os.path.join(RAW, f"p{p}.html"), encoding="utf-8") as f:
        html = f.read()
    i0 = html.find(f'id="page-{p}"')
    i1 = html.find('class="page-navigation', i0)
    seg = html[i0:i1 if i1 > 0 else len(html)]
    parts = RE_LINE.split(seg)  # [pre, n1, body1, n2, body2, ...]
    lines = []
    for j in range(1, len(parts), 2):
        ln, body = int(parts[j]), parts[j + 1]
        m = RE_CLS.search(body)
        cls = m.group(1) if m else ""
        chars = [(k, int(s), int(a), int(pos), g)
                 for k, s, a, pos, g in RE_CHAR.findall(body)]
        lines.append((ln, cls, chars))
    return lines

def main():
    os.makedirs(RAW, exist_ok=True)
    os.makedirs(os.path.join(OUT, "surah"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "page"), exist_ok=True)

    print("fetching QUL layout previews (cached)...", flush=True)
    with ThreadPoolExecutor(max_workers=3) as ex:
        for n, _ in enumerate(ex.map(fetch, range(1, PAGES + 1)), 1):
            if n % 50 == 0:
                print(f"  {n}/{PAGES}", flush=True)

    surahs = {}       # s -> {ayah: {"w": [...], "e": ...}}
    pages_out = {}    # p -> {"lines": {...}, "starts": [...], "center": [...]}
    surah_start, page_first = {}, {}
    warn = []

    for p in range(1, PAGES + 1):
        lines = parse_page(p)
        pl, starts, center = {}, [], []
        line_cls = {ln: cls for ln, cls, _ in lines}
        for ln, cls, chars in lines:
            if "line--center" in cls and chars:
                center.append(ln)
            for kind, s, a, pos, g in chars:
                if p not in page_first:
                    page_first[p] = {"surah": s, "ayah": a}
                ay = surahs.setdefault(s, {}).setdefault(a, {"w": [], "e": None})
                if kind == "char-end":
                    if ay["e"] is not None:
                        warn.append(f"p{p} {s}:{a}: second end marker")
                    ay["e"] = [g, p]
                else:
                    ay["w"].append([g, p])
                    if a == 1 and pos == 1 and s not in surah_start:
                        surah_start[s] = {"page": p, "line": ln}
                        starts.append({"surah": s, "ayah": 1, "line": ln})
                        # проверка допущения рендера: заголовок строкой выше,
                        # басмала (кроме сур 1 и 9) — между ними
                        has_b = s not in (1, 9)
                        hl, bl = ln - (2 if has_b else 1), ln - 1
                        if hl >= 1 and "line--surah-name" not in line_cls.get(hl, ""):
                            warn.append(f"p{p} surah {s}: no header at line {hl}")
                        if has_b and bl >= 1 and "line--bismillah" not in line_cls.get(bl, ""):
                            warn.append(f"p{p} surah {s}: no bismillah at line {bl}")
                pl.setdefault(ln, []).append([g, p])
        pages_out[p] = {"lines": {str(ln): pl[ln] for ln in sorted(pl)},
                        "starts": starts, "center": center}

    # --- валидации ---------------------------------------------------------
    arabic = json.load(open(ARABIC, encoding="utf-8"))
    total = 0
    for s in range(1, 115):
        want = len(arabic[str(s)])
        got = len(surahs.get(s, {}))
        total += got
        if want != got:
            warn.append(f"surah {s}: {got} ayat, expected {want}")
        for a, ay in surahs.get(s, {}).items():
            if not ay["w"]:
                warn.append(f"{s}:{a}: no words")
            if ay["e"] is None:
                warn.append(f"{s}:{a}: no end marker")
    print(f"parsed: {total} ayat, {len(pages_out)} pages, {len(surah_start)} surah starts")

    v1 = json.load(open(V1_META, encoding="utf-8")) if os.path.exists(V1_META) else None
    if v1:
        diff = [p for p in map(str, range(1, PAGES + 1))
                if v1["pageStart"].get(p) != {k: v for k, v in page_first[int(p)].items()}]
        print(f"pageStart diff vs v1: {len(diff)} pages" + (f" -> {diff[:20]}" if diff else ""))

    # juz/rub: сура:аят из v1-меты (не зависят от раскладки), страница — по v4
    def page_of(s, a):
        e = surahs.get(int(s), {}).get(int(a))
        return e["w"][0][1] if e and e["w"] else (e["e"][1] if e and e["e"] else None)
    juz_start = {k: {"page": page_of(v["surah"], v["ayah"]), "surah": v["surah"], "ayah": v["ayah"]}
                 for k, v in (v1["juzStart"] if v1 else {}).items()}
    rub_start = {k: {"page": page_of(v["surah"], v["ayah"]), "surah": v["surah"], "ayah": v["ayah"]}
                 for k, v in (v1["rubStart"] if v1 else {}).items()}

    # --- запись -------------------------------------------------------------
    for s, ayat in surahs.items():
        chunk = {str(a): ayat[a] for a in sorted(ayat)}
        with open(os.path.join(OUT, "surah", f"{s}.json"), "w", encoding="utf-8") as f:
            json.dump(chunk, f, ensure_ascii=False, separators=(",", ":"))
    for p, out in pages_out.items():
        with open(os.path.join(OUT, "page", f"{p}.json"), "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    meta = {"pages": PAGES,
            "surahStart": {str(k): surah_start[k] for k in sorted(surah_start)},
            "surahIndex": sorted(surahs),
            "pageStart": {str(k): page_first[k] for k in sorted(page_first)},
            "juzStart": juz_start, "rubStart": rub_start}
    with open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, separators=(",", ":"))

    if warn:
        print(f"\nWARNINGS ({len(warn)}):")
        for w in warn[:40]:
            print(" ", w)
    print("done.", flush=True)

if __name__ == "__main__":
    main()
