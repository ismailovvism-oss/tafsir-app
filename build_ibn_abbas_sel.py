#!/usr/bin/env python3
"""
Парсер книги «Тафсир Ибн Аббаса к избранным сурам» (сост. Кенан Абу Абдуррахман,
Уфа · Читай-Умма, 2023) из .md-экспорта в формат приложения {сура:{аят:markdown}}.

Это ОТДЕЛЬНЫЙ источник `ibn_abbas_sel` — не путать с `ibn_abbas` (свод асаров
Ибн Аббаса из «аль-Мавсуа»). Здесь — курированная компиляция преданий Ибн Аббаса
И мекканской школы (Муджахид, Икрима, Ата, Саид ибн Джубайр, Хасан) + хадисы +
пояснения составителя, по ~13 избранным сурам, на русском с арабскими цитатами.

Структура .md:
  • суры    — заголовок «# Сура N «…»» (у Фатихи — без #, ловим по наличию аятов);
  • аяты    — жирный заголовок «**N. «перевод»**» (перед ним обычно строка ﴿…﴾);
  • сноски  — инлайн ((n))(#_ftn n) → [^n]; определения единым блоком в конце файла
              ((n))(#_ftnref n) …  → карта, дописывается под аят по факту использования;
  • контент — до раздела «БИБЛИОГРАФИЯ» (back-matter отсекается).

Запуск:  python3 build_ibn_abbas_sel.py
Далее :  python3 split.py ibn_abbas_sel && python3 build_index.py ibn_abbas_sel
         зеркало в r2-data/ и ./upload_r2.sh; затем compute_fill/build_coverage/sync_config.
"""
import re, json, os

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = "/home/qaadiy/obsid/qaadiy/Ислам/Коран/Тафсир/Ибн Аббас/Тафсир Ибн Аббаса к избранным сурам.md"
OUT = os.path.join(ROOT, "data", "tafsirs", "ibn_abbas_sel.json")
ARABIC = os.path.join(ROOT, "data", "tafsirs", "_arabic.json")


def main():
    raw = open(SRC, encoding="utf-8").read()
    aycount = {int(s): len(v) for s, v in json.load(open(ARABIC, encoding="utf-8")).items()}

    # карта сносок из блока определений в конце файла
    fnmap = {m.group(1): re.sub(r"\s+", " ", m.group(2)).strip()
             for m in re.finditer(r"\(\((\d+)\)\)\(#_ftnref\d+\)\s*(.*?)(?=\n\(\(\d+\)\)\(#_ftnref|\Z)", raw, re.S)}

    # контент для нарезки — до back-matter «БИБЛИОГРАФИЯ» (или до блока сносок)
    end = len(raw)
    mb = re.search(r"(?m)^\s*БИБЛИОГРАФИЯ\b", raw)
    if mb:
        end = mb.start()
    else:
        mf = re.search(r"\(\(\d+\)\)\(#_ftnref\d+\)", raw)
        if mf:
            end = mf.start()
    body_all = raw[:end]

    def clean(t):
        t = re.sub(r"!\(\)\([^)]*\)", "", t)                       # картинки/файлы
        t = re.sub(r"\(\((\d+)\)\)\(#_ftn\d+\)", r"[^\1]", t)      # инлайн-сноска → [^n]
        t = re.sub(r"(?m)^#{0,2}\s*\*\*\* \* \*\*\*\s*$", "", t)   # декоративные разделители
        t = re.sub(r"[ \t]+", " ", t)
        return t.strip()

    # заголовки сур (с # и без — у Фатихи без); блоки без аятов = оглавление, отсеиваем
    cands = [(m.start(), int(m.group(1))) for m in re.finditer(r"(?m)^#?\s*Сура (\d+)\b.*«", body_all)]
    cands.append((len(body_all), None))

    mono = {}
    for i in range(len(cands) - 1):
        start, snum = cands[i]
        block = body_all[start:cands[i + 1][0]]
        if not re.search(r"(?m)^\*\*\d{1,3}[.*]", block):
            continue  # оглавление / не сура

        ayah, buckets = 0, {0: []}
        for ln in block.split("\n"):
            hm = re.match(r"^\*\*(\d{1,3})[.*]", ln.strip())
            if hm:
                ayah = int(hm.group(1))
                buckets.setdefault(ayah, [])
            buckets[ayah].append(ln)

        sd = {}
        for ay, ls in buckets.items():
            b = re.sub(r"\n{3,}", "\n\n", clean("\n".join(ls))).strip()
            if not b:
                continue
            used = sorted(set(re.findall(r"\[\^(\d+)\]", b)), key=int)
            if used:
                b += "\n\n" + "\n".join(f"[^{n}]: {fnmap.get(n, '?')}" for n in used)
            sd[str(ay)] = b

        # если аята 1 нет, а вся суть суры лежит в «0» (напр., ан-Нас 1–5 единым
        # блоком) — переносим на аят 1, чтобы привязалось к тексту, а не к преамбуле
        if "1" not in sd and "0" in sd and len(sd["0"]) > 1500:
            sd["1"] = sd.pop("0")

        # отбросить ключи-аяты сверх длины суры (артефакты)
        n = aycount.get(snum, 999)
        sd = {a: t for a, t in sd.items() if a == "0" or int(a) <= n}
        if sd:
            mono[str(snum)] = sd

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(mono, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    tot = sum(len(v) for sd in mono.values() for v in sd.values())
    print(f"Готово: {len(mono)} сур, "
          f"{sum(1 for sd in mono.values() for a in sd if a != '0')} аятов, "
          f"{tot} символов → {OUT}")
    for s in sorted(mono, key=int):
        print(f"  сура {s:>3}: ключей {len(mono[s])}")
    print("Дальше: split.py → build_index.py → зеркало r2-data → upload → config.")


if __name__ == "__main__":
    main()
