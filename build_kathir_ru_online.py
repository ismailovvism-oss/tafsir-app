#!/usr/bin/env python3
"""
Пере-сборка русского Ибн Касира (kathir_ru) из онлайн-источника quran-online.ru.

Это ТОТ ЖЕ перевод (Мухтасар Ибн Касира, пер. Айрат Вахитов), что уже был у нас
из fb2, но ПОЛНЫЙ (все 114 сур) и чище (арабские цитаты целы, по-аятно).
Разрешение переводчика получено (Ismail).

Источник: https://quran-online.ru/<sura>:<ayah>  — server-rendered HTML.
Блок Ибн Касира: <dl class="dl-horizontal"><dt>Ибн Касир</dt><dd class="ayat">…</dd></dl>
  • <p>                       → абзацы
  • span.ayat-text--addition  → добавления переводчика (инлайн, уже в скобках)
  • span.original-text/inline → арабские цитаты ﴾ … ﴿ (инлайн)
  • <a>                       → перекрёстные ссылки (берём текст, href отбрасываем)

Кеш сырого HTML: data/_sources/kathir_ru_online/<sura>/<ayah>.html (gitignored,
резюмируемо — повторный запуск не перекачивает уже скачанное).

Использование:
  python3 build_kathir_ru_online.py --sample 36:1 2:255 55:1   # печать md, без записи
  python3 build_kathir_ru_online.py --fetch                    # только докачать кеш
  python3 build_kathir_ru_online.py --parse                    # из кеша → монолит
  python3 build_kathir_ru_online.py                            # fetch + parse + монолит
После: python3 split.py kathir_ru && python3 build_index.py kathir_ru \
       && python3 compute_fill.py && python3 build_coverage.py
"""
import json, os, re, sys, time, random, shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import requests
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.abspath(__file__))
ARABIC_DIR = os.path.join(ROOT, "data", "tafsirs", "_arabic")
CACHE = os.path.join(ROOT, "data", "_sources", "kathir_ru_online")
MONOLITH = os.path.join(ROOT, "data", "tafsirs", "kathir_ru.json")
BASE = "https://quran-online.ru/{s}:{a}"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
WORKERS = 5
TIMEOUT = 25

_tls = threading.local()
def session():
    s = getattr(_tls, "s", None)
    if s is None:
        s = requests.Session()
        s.headers["User-Agent"] = UA
        _tls.s = s
    return s

# ---------- suras / ayah counts ----------
def ayah_counts():
    counts = {}
    for su in range(1, 115):
        p = os.path.join(ARABIC_DIR, f"{su}.json")
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        counts[su] = max(int(k) for k in d)
    return counts

# ---------- fetch (cache-backed, resumable) ----------
def cache_path(su, ay):
    return os.path.join(CACHE, str(su), f"{ay}.html")

def fetch_one(su, ay):
    cp = cache_path(su, ay)
    if os.path.isfile(cp) and os.path.getsize(cp) > 500:
        return "cached"
    url = BASE.format(s=su, a=ay)
    for attempt in range(4):
        try:
            r = session().get(url, timeout=TIMEOUT)
            if r.status_code == 200 and len(r.text) > 500:
                os.makedirs(os.path.dirname(cp), exist_ok=True)
                with open(cp, "w", encoding="utf-8") as f:
                    f.write(r.text)
                time.sleep(0.15 + random.random() * 0.2)
                return "ok"
            time.sleep(1.0 + attempt)
        except requests.RequestException:
            time.sleep(1.5 + attempt * 1.5)
    return "fail"

def fetch_all(counts):
    jobs = [(su, ay) for su in range(1, 115) for ay in range(1, counts[su] + 1)]
    total = len(jobs)
    done = {"ok": 0, "cached": 0, "fail": 0}
    fails = []
    print(f"Качаю {total} страниц ({WORKERS} потоков)…")
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(fetch_one, su, ay): (su, ay) for su, ay in jobs}
        n = 0
        for fut in as_completed(futs):
            su, ay = futs[fut]
            res = fut.result()
            done[res] = done.get(res, 0) + 1
            if res == "fail":
                fails.append((su, ay))
            n += 1
            if n % 250 == 0 or n == total:
                print(f"  {n}/{total}  ok={done['ok']} cached={done['cached']} fail={done['fail']}")
    if fails:
        print(f"  ⚠ не скачано: {len(fails)} — {fails[:20]}{'…' if len(fails)>20 else ''}")
    return fails

# ---------- HTML → markdown ----------
def find_kathir_dd(html):
    soup = BeautifulSoup(html, "lxml")
    for dl in soup.select("dl.dl-horizontal"):
        dt = dl.find("dt")
        if dt and "Ибн Касир" in dt.get_text():
            return dl.find("dd", class_="ayat")
    return None

_ws = re.compile(r"[ \t\r\n ]+")
def _norm(t):
    return _ws.sub(" ", t).strip()

# Редакторские примечания переводчика в источнике — литеральные [[ … ]] (внутри
# абзаца, без переносов). У нас в kathir_ru принят стиль сносок [^N] + [^N]: …,
# поэтому переводим их в нумерованные (по-аятно) сноски в конце текста аята.
_note_re = re.compile(r"\[\[(.+?)\]\]")
def convert_notes(md):
    defs = []
    def repl(m):
        defs.append(m.group(1).strip())
        return "[^%d]" % len(defs)
    body = _note_re.sub(repl, md)
    if defs:
        body += "\n\n" + "\n".join("[^%d]: %s" % (i + 1, d) for i, d in enumerate(defs))
    return body

def dd_to_md(dd):
    if dd is None:
        return ""
    # Абзацы: прямые <p>. Если их нет — весь текст dd одним куском.
    ps = dd.find_all("p")
    if ps:
        paras = [_norm(p.get_text()) for p in ps]
    else:
        paras = [_norm(dd.get_text())]
    paras = [p for p in paras if p]
    return convert_notes("\n\n".join(paras))

def parse_all(counts):
    out = {}
    empty = []
    missing_cache = []
    for su in range(1, 115):
        chunk = {}
        for ay in range(1, counts[su] + 1):
            cp = cache_path(su, ay)
            if not (os.path.isfile(cp) and os.path.getsize(cp) > 500):
                missing_cache.append((su, ay)); continue
            with open(cp, encoding="utf-8") as f:
                html = f.read()
            md = dd_to_md(find_kathir_dd(html))
            if md:
                chunk[str(ay)] = md
            else:
                empty.append((su, ay))
        if chunk:
            out[str(su)] = chunk
    return out, empty, missing_cache

def write_monolith(out):
    if os.path.isfile(MONOLITH):
        shutil.copy2(MONOLITH, MONOLITH + ".bak")
        print(f"  бэкап старого монолита → {MONOLITH}.bak")
    with open(MONOLITH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    suras = len(out)
    ayat = sum(len(v) for v in out.values())
    size = os.path.getsize(MONOLITH) / 1e6
    print(f"  ✓ монолит: {suras} сур, {ayat} аятов, {size:.1f} МБ → {MONOLITH}")

# ---------- sample (для проверки качества) ----------
def sample(refs):
    for ref in refs:
        su, ay = ref.split(":")
        r = session().get(BASE.format(s=su, a=ay), timeout=TIMEOUT)
        md = dd_to_md(find_kathir_dd(r.text))
        print(f"\n===== {su}:{ay} ({len(md)} симв.) =====")
        print(md[:1200] + ("…" if len(md) > 1200 else ""))

# ---------- main ----------
def main():
    args = sys.argv[1:]
    if args and args[0] == "--sample":
        sample(args[1:]); return
    counts = ayah_counts()
    do_fetch = (not args) or "--fetch" in args
    do_parse = (not args) or "--parse" in args
    if do_fetch:
        fetch_all(counts)
    if do_parse:
        print("Парсю кеш → монолит…")
        out, empty, missing = parse_all(counts)
        write_monolith(out)
        if empty:
            print(f"  ℹ без текста Ибн Касира: {len(empty)} аятов — {empty[:20]}{'…' if len(empty)>20 else ''}")
        if missing:
            print(f"  ⚠ нет в кеше: {len(missing)} аятов — сначала --fetch")
        print("\nДальше:  python3 split.py kathir_ru && python3 build_index.py kathir_ru "
              "&& python3 compute_fill.py && python3 build_coverage.py")

if __name__ == "__main__":
    main()
