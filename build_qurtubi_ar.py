#!/usr/bin/env python3
"""
Сборка источника `qurtubi_ar` — «Тафсир аль-Куртуби» (الجامع لأحكام القرآن)
Абу Абдуллаха аль-Куртуби (ум. 671 х.), арабский оригинал.

Данные берутся по-аятно из открытого агрегатора spa5k/tafsir_api (зеркало
quran.com), edition slug `ar-tafseer-al-qurtubi`. Полный охват Корана; текст
чистый (арабский, с огласовками).

ВАЖНО — источник ТЯЖЁЛЫЙ. По решению проекта его данные живут НЕ в репозитории,
а на Cloudflare R2 (как mawsua_masur): в config у источника поле `dataBase`
указывает на публичный R2-URL, а монолит/чанки/индекс в репо НЕ коммитятся
(см. .gitignore). Этот скрипт лишь воссоздаёт их локально — для заливки на R2.

Использование:
  python3 build_qurtubi_ar.py             # скачать + собрать монолит
  python3 split.py qurtubi_ar             # → чанки по сурам
  python3 build_index.py qurtubi_ar       # → индекс поиска
  python3 compute_fill.py && python3 build_coverage.py && python3 sync_config.py
  # затем зеркало в r2-data/ и ./upload_r2.sh
"""

import json, os, time
from concurrent.futures import ThreadPoolExecutor
from urllib.request import urlopen, Request

ROOT = os.path.dirname(os.path.abspath(__file__))
SLUG = "ar-tafseer-al-qurtubi"
BASE = "https://raw.githubusercontent.com/spa5k/tafsir_api/main/tafsir/" + SLUG
OUT = os.path.join(ROOT, "data", "tafsirs", "qurtubi_ar.json")

# Канонические числа аятов по сурам берём из текста Корана (источник истины).
ARABIC = os.path.join(ROOT, "data", "tafsirs", "_arabic.json")


def ayah_counts():
    with open(ARABIC, encoding="utf-8") as f:
        a = json.load(f)
    return {int(s): len(v) for s, v in a.items()}


def fetch_one(s, ay, retries=4):
    url = f"{BASE}/{s}/{ay}.json"
    for attempt in range(retries):
        try:
            with urlopen(Request(url, headers={"User-Agent": "tafsir-app-build"}), timeout=30) as r:
                if r.status == 200:
                    return s, ay, (json.loads(r.read().decode("utf-8")).get("text") or "").strip()
                return s, ay, None  # 404 и т.п. — аята нет
        except Exception:
            if attempt == retries - 1:
                return s, ay, ""  # пометим как сбой (перекачаем отдельно)
            time.sleep(2 ** attempt)
    return s, ay, ""


def main():
    counts = ayah_counts()
    refs = [(s, ay) for s in range(1, 115) for ay in range(1, counts[s] + 1)]
    print(f"Скачиваю {len(refs)} аятов из spa5k/tafsir_api ({SLUG})…")

    results = {}
    with ThreadPoolExecutor(max_workers=20) as ex:
        for i, (s, ay, text) in enumerate(ex.map(lambda r: fetch_one(*r), refs), 1):
            results[(s, ay)] = text
            if i % 500 == 0:
                print(f"  …{i}/{len(refs)}")

    # перекачать «сбойные» (text == "" но файл реально есть) поштучно
    retry = [(s, ay) for (s, ay), t in results.items() if t == ""]
    for s, ay in retry:
        _, _, t = fetch_one(s, ay, retries=6)
        results[(s, ay)] = t

    mono = {}
    for s in range(1, 115):
        sd = {str(ay): results[(s, ay)] for ay in range(1, counts[s] + 1)
              if results.get((s, ay))}
        if sd:
            mono[str(s)] = sd

    total = sum(len(v) for v in mono.values())
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(json.dumps(mono, ensure_ascii=False, indent=2))
    print(f"Готово: {len(mono)} сур, {total} аятов → {OUT} "
          f"({os.path.getsize(OUT) // 1048576} МБ)")
    print("Дальше: split.py → build_index.py → compute_fill/build_coverage/sync_config, "
          "затем зеркало в r2-data/ и залить на R2.")


if __name__ == "__main__":
    main()
