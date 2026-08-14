#!/usr/bin/env python3
"""
Арабский оригинал «Джами' аль-баян» ат-Табари (tabari_ar).

Источник: tafsir_api (spa5k), издание ar-tafsir-al-tabari, по-аятно на jsdelivr CDN:
  https://cdn.jsdelivr.net/gh/spa5k/tafsir_api@main/tafsir/ar-tafsir-al-tabari/<sura>/<ayah>.json
  → {"text": "...", "ayah": n, "surah": s}. Формат тот же, что у аль-Багави
  (см. build_baghawi_ar.py): чистый текст, абзацы \n\n, ﴿…﴾ — цитаты аятов,
  [[…]] — примечания редактора (Махмуда Шакира) → сноски [^N].

Объём: ~36 МБ (вдвое больше аль-Куртуби) — монолит идёт на R2 (dataBase),
в репозиторий НЕ коммитится.

Кеш: data/_sources/tabari_ar/<sura>/<ayah>.json (gitignored, резюмируемо).
Выход: data/tafsirs/tabari_ar.json = {"<sura>": {"<ayah>": "md"}}.

Использование:
  python3 build_tabari_ar.py --sample 5:38 2:2
  python3 build_tabari_ar.py                  # fetch + parse + монолит
Дальше: split.py tabari_ar && build_index.py tabari_ar && compute_fill.py && build_coverage.py
"""
import os, re, sys, json, time, random
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading, requests

ROOT = os.path.dirname(os.path.abspath(__file__))
ARABIC_DIR = os.path.join(ROOT, "data", "tafsirs", "_arabic")
CACHE = os.path.join(ROOT, "data", "_sources", "tabari_ar")
OUT = os.path.join(ROOT, "data", "tafsirs", "tabari_ar.json")
BASE = "https://cdn.jsdelivr.net/gh/spa5k/tafsir_api@main/tafsir/ar-tafsir-al-tabari/{s}/{a}.json"
UA = "Mozilla/5.0 (tafsir-library data build)"
WORKERS = 6
TIMEOUT = 25

_tls = threading.local()
def session():
    s = getattr(_tls, "s", None)
    if s is None:
        s = requests.Session(); s.headers["User-Agent"] = UA; _tls.s = s
    return s

def ayah_counts():
    c = {}
    for su in range(1, 115):
        with open(os.path.join(ARABIC_DIR, f"{su}.json"), encoding="utf-8") as f:
            c[su] = max(int(k) for k in json.load(f))
    return c

def cache_path(su, ay):
    return os.path.join(CACHE, str(su), f"{ay}.json")

def fetch_one(su, ay):
    cp = cache_path(su, ay)
    if os.path.isfile(cp) and os.path.getsize(cp) > 2:
        return "cached"
    url = BASE.format(s=su, a=ay)
    for attempt in range(4):
        try:
            r = session().get(url, timeout=TIMEOUT)
            if r.status_code == 200:
                os.makedirs(os.path.dirname(cp), exist_ok=True)
                with open(cp, "w", encoding="utf-8") as f:
                    f.write(r.text)
                time.sleep(0.05 + random.random() * 0.1)
                return "ok"
            if r.status_code == 404:            # нет аята — пустой маркер
                os.makedirs(os.path.dirname(cp), exist_ok=True)
                open(cp, "w").write("{}")
                return "ok"
            time.sleep(1.0 + attempt)
        except requests.RequestException:
            time.sleep(1.5 + attempt * 1.5)
    return "fail"

def fetch_all(counts):
    jobs = [(su, ay) for su in range(1, 115) for ay in range(1, counts[su] + 1)]
    done = {"ok": 0, "cached": 0, "fail": 0}; fails = []
    print(f"Качаю {len(jobs)} аятов ({WORKERS} потоков)…")
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(fetch_one, su, ay): (su, ay) for su, ay in jobs}
        n = 0
        for fut in as_completed(futs):
            res = fut.result(); done[res] = done.get(res, 0) + 1
            if res == "fail": fails.append(futs[fut])
            n += 1
            if n % 500 == 0 or n == len(jobs):
                print(f"  {n}/{len(jobs)}  ok={done['ok']} cached={done['cached']} fail={done['fail']}")
    if fails:
        print(f"  ⚠ не скачано: {len(fails)} — {fails[:15]}")
    return fails

# ---------- конвертация текста → markdown ----------
_note_re = re.compile(r"\[\[(.+?)\]\]", re.S)
def convert(text):
    if not text:
        return ""
    text = text.replace("\r", "").strip()
    # редакторские [[…]] → сноски [^N] (по-аятно)
    defs = []
    def repl(m):
        defs.append(re.sub(r"\s+", " ", m.group(1).strip()))
        return "[^%d]" % len(defs)
    body = _note_re.sub(repl, text)
    # убрать строки-разделители (только * _ - пробелы) и нормализовать пустые строки
    body = re.sub(r"(?m)^[\s*_\-–—]+$", "", body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    if defs:
        body += "\n\n" + "\n".join("[^%d]: %s" % (i + 1, d) for i, d in enumerate(defs))
    return body

def read_cached(su, ay):
    cp = cache_path(su, ay)
    if not (os.path.isfile(cp) and os.path.getsize(cp) > 2):
        return None
    try:
        d = json.load(open(cp, encoding="utf-8"))
    except Exception:
        return None
    return (d.get("text") or "").strip() or None

def parse_all(counts):
    out = {}; empty = 0; miss = 0
    for su in range(1, 115):
        chunk = {}
        for ay in range(1, counts[su] + 1):
            cp = cache_path(su, ay)
            if not (os.path.isfile(cp) and os.path.getsize(cp) > 2):
                miss += 1; continue
            txt = read_cached(su, ay)
            if not txt:
                empty += 1; continue
            md = convert(txt)
            if md:
                chunk[str(ay)] = md
        if chunk:
            out[str(su)] = chunk
    return out, empty, miss

def write_monolith(out):
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    ayat = sum(len(v) for v in out.values())
    print(f"  ✓ монолит: {len(out)} сур, {ayat} аятов, {os.path.getsize(OUT)/1e6:.1f} МБ → {OUT}")

def sample(refs):
    for ref in refs:
        su, ay = ref.split(":")
        r = session().get(BASE.format(s=su, a=ay), timeout=TIMEOUT).json()
        md = convert(r.get("text", ""))
        print(f"\n===== {su}:{ay} ({len(md)} симв.) =====\n{md[:900]}")

def main():
    a = sys.argv[1:]
    if a and a[0] == "--sample":
        sample(a[1:]); return
    counts = ayah_counts()
    if not a or "--fetch" in a:
        fetch_all(counts)
    if not a or "--parse" in a:
        print("Парсю кеш → монолит…")
        out, empty, miss = parse_all(counts)
        write_monolith(out)
        if empty: print(f"  ℹ пустых аятов: {empty}")
        if miss: print(f"  ⚠ нет в кеше: {miss} — сначала --fetch")
        print("\nДальше: python3 split.py tabari_ar && python3 build_index.py tabari_ar "
              "&& python3 compute_fill.py && python3 build_coverage.py")

if __name__ == "__main__":
    main()
