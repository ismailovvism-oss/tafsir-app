#!/usr/bin/env python3
"""
«تأويلات الطبري وترجيحاته» (tabari_tarjih_ar) — арабский оригинал того же текста,
что переведён в tabari_tarjih_ru: речь самого ат-Табари, извлечённая из полного
«Джами' аль-баяна».

Пять источников по ат-Табари, чтобы не путать имена:
  tabari_ar          — ПОЛНЫЙ тафсир по-арабски                    (готов)
  tabari_tarjih_ar   — извлечённая речь имама по-арабски           (этот скрипт)
  tabari_ru          — перевод ПОЛНОГО тафсира             (ИМЯ ЗАРЕЗЕРВИРОВАНО)
  tabari_tarjih_ru   — перевод извлечённой речи имама              (в работе)
  + собственный перевод Корана, выводимый из tabari_tarjih_ru      (впереди)

ЧТО ЭТО НЕ ТАКОЕ: это НЕ изданный «Мухтасар тафсир ат-Табари» (ас-Сабуни и др.),
а машинная выжимка из полного текста — перифраза аята («يقول تعالى ذكره»), итог
(«فتأويل الكلام إذًا») и тарджих («وأولى الأقوال…»). Так и сказано в паспорте ℹ:
выдавать выжимку за признанное сокращение нельзя.

Асар, на который имам передал слово («وتأويل ذلك كالذي قاله ابن عباس، الذي:-»),
идёт следом за его словами с иснадом как есть — без него мысль обрывается.

Вход:  data/_sources/tabari_ru/skeleton/<sura>.json  (build_tabari_skeleton.py)
Выход: data/tafsirs/tabari_tarjih_ar.json = {"<sura>": {"<ayah>": "md"}}

Использование:
  python3 build_tabari_tarjih_ar.py --sample 1:6 5:38
  python3 build_tabari_tarjih_ar.py
Дальше: split.py tabari_tarjih_ar && build_index.py tabari_tarjih_ar
        && compute_fill.py && build_coverage.py && sync_config.py
        затем зеркало в r2-data/ и ./upload_r2.sh
"""
import os, sys, json, glob

ROOT = os.path.dirname(os.path.abspath(__file__))
SKEL = os.path.join(ROOT, "data", "_sources", "tabari_ru", "skeleton")
OUT = os.path.join(ROOT, "data", "tafsirs", "tabari_tarjih_ar.json")


def render(rec):
    """Запись скелета аята → markdown в том же порядке блоков, что и в русском."""
    parts = []
    for f in rec.get("frags", []):
        body = []
        for x in f.get("para", []):
            body.append(x)
        for x in f.get("final", []):
            body.append(f"**فتأويل الكلام:** {x}")
        for x in f.get("tarjih", []):
            body.append(f"**والصواب عند الطبري:** {x}")
        for x in f.get("athar", []):
            body.append(f"> {x}")
        if not body:
            continue                      # фрагмент без слов имама не показываем
        q = (f.get("q") or "").strip()
        if q:
            parts.append(f"**﴿{q}﴾**")
        parts += body
    return "\n\n".join(parts).strip()


def build():
    out = {}
    for path in sorted(glob.glob(os.path.join(SKEL, "*.json")),
                       key=lambda p: int(os.path.basename(p)[:-5])):
        su = os.path.basename(path)[:-5]
        chunk = {}
        for ay, rec in json.load(open(path, encoding="utf-8")).items():
            md = render(rec)
            if md:
                chunk[ay] = md
        if chunk:
            out[su] = chunk
    return out


def main():
    a = sys.argv[1:]
    if a and a[0] == "--sample":
        for ref in a[1:]:
            su, ay = ref.split(":")
            rec = json.load(open(os.path.join(SKEL, f"{su}.json"), encoding="utf-8"))[ay]
            print(f"\n===== {ref} =====\n{render(rec)}")
        return
    out = build()
    if not out:
        print("нет скелета — сначала python3 build_tabari_skeleton.py --build")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    ayat = sum(len(v) for v in out.values())
    print(f"  ✓ монолит: {len(out)} сур, {ayat} аятов, "
          f"{os.path.getsize(OUT) / 1e6:.1f} МБ → {OUT}")
    print("Дальше: split.py tabari_tarjih_ar && build_index.py tabari_tarjih_ar "
          "&& compute_fill.py && build_coverage.py && sync_config.py, затем R2")


if __name__ == "__main__":
    main()
