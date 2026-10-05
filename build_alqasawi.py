#!/usr/bin/env python3
"""
Авторские слои тафсира аль-Касави — импорт из проекта книги в данные библиотеки.

На каждый аят у автора пять слоёв (план — ~/projects/texts/tafsir-na-palcah/СЛОИ.md).
Этот скрипт забирает три из них — те, что уже готовы как данные:

  слой 2  перевод                    слои/перевод/<NNN>.json        → alqasawi        (kind translation)
  слой 3  развёрнутый перевод-тафсир слои/перевод-тафсир/<NNN>.json → alqasawi_sharh  (kind translation)
  слой 4  визуальный тафсир — слайды слои/визуальный/<NNN>/<AAA>/   → alqasawi_slides (kind tafsir, render "slides")

Источник истины — папка проекта книги (там их правит автор). Сюда текст
копируется в data/translation/<id>/<сура>.json (наш собственный текст, история
правок — в git, как у tabari_bayan_ru), из него собирается монолит
data/tafsirs/<id>.json.

Слайды: кадры аята — data/slides/alqasawi_slides/<сура>.json =
  {"<аят>": [{"t":"img","src":URL,"alt":…,"cap":…} | {"t":"svg","svg":…,"cap":…}
            | {"t":"text","html":…,"cap":…}]}
(класс `slides` в SOURCES index.html). Картина первого кадра — та же, что у аята
в визуальной полосе: pin-<с>-<а>-01.png на R2. А в монолит alqasawi_slides идут
ПОДПИСИ кадров текстом — по ним работают поиск, покрытие и «есть у аята»; сам
источник рисуется листаемыми слайдами (`render:"slides"` в config.json).

Арабский в схемах сверяется с _arabic.json дословно (как в собрать.py проекта).

Использование:
  python3 build_alqasawi.py
Дальше: python3 split.py alqasawi alqasawi_sharh alqasawi_slides
        && python3 build_index.py alqasawi alqasawi_sharh alqasawi_slides
        && python3 compute_fill.py && python3 build_coverage.py && python3 sync_config.py
"""
import json, os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LAYERS = Path.home() / "projects/texts/tafsir-na-palcah/слои"
R2_PINS = "https://pub-d99a56b61d914461b5864f421a013097.r2.dev/media/filmstrip/"
ARAB = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]"
                  r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿ ]*")


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def text_layer(sub, tid):
    """{"аят": "текст"} по сурам → data/translation/<tid>/<с>.json + монолит."""
    whole = {}
    for f in sorted((LAYERS / sub).glob("[0-9][0-9][0-9].json")):
        s = str(int(f.stem))
        d = {a: t.strip() for a, t in json.loads(f.read_text(encoding="utf-8")).items() if t.strip()}
        save(ROOT / "data/translation" / tid / f"{s}.json", d)
        whole[s] = d
    (ROOT / "data/tafsirs" / f"{tid}.json").write_text(
        json.dumps(whole, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"  ✓ {tid}: сур {len(whole)}, аятов {sum(len(v) for v in whole.values())}")


def slides_layer(tid="alqasawi_slides"):
    arabic = json.loads((ROOT / "data/tafsirs/_arabic.json").read_text(encoding="utf-8"))
    every = "\n".join(t for su in arabic.values() for t in su.values())
    bad = 0
    caps_all = {}
    for sdir in sorted(p for p in (LAYERS / "визуальный").iterdir() if p.is_dir() and p.name.isdigit()):
        s = str(int(sdir.name))
        frames_s, caps_s = {}, {}
        for adir in sorted(p for p in sdir.iterdir() if (p / "кадры.json").exists()):
            a = str(int(adir.name))
            d = json.loads((adir / "кадры.json").read_text(encoding="utf-8"))
            frames = []
            for k in d["кадры"]:
                cap = k.get("подпись", "")
                if k["тип"] == "картина":
                    frames.append({"t": "img", "src": R2_PINS + k["файл"], "alt": k.get("alt", ""), "cap": cap})
                elif k["тип"] == "схема":
                    svg = (adir / k["файл"]).read_text(encoding="utf-8")
                    svg = "\n".join(l.strip() for l in svg.strip().splitlines())
                    frames.append({"t": "svg", "svg": svg, "cap": cap})
                else:
                    svg = k["текст"]
                    frames.append({"t": "text", "html": k["текст"], "cap": cap})
                if k["тип"] != "картина":
                    for m in ARAB.finditer(svg):
                        if m.group().strip() not in every:
                            print(f"  ! арабский не из эталона: {s}:{a}: {m.group().strip()}")
                            bad += 1
            frames_s[a] = frames
            caps_s[a] = "\n\n".join(f"**Кадр {n}.** {f['cap']}" for n, f in enumerate(frames, 1) if f["cap"])
        if frames_s:
            save(ROOT / "data/slides" / tid / f"{s}.json", frames_s)
            save(ROOT / "data/translation" / tid / f"{s}.json", caps_s)
            caps_all[s] = caps_s
    (ROOT / "data/tafsirs" / f"{tid}.json").write_text(
        json.dumps(caps_all, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    n = sum(len(v) for v in caps_all.values())
    print(f"  ✓ {tid}: сур {len(caps_all)}, аятов {n}" + (f", ! арабских ошибок {bad}" if bad else ", арабский сверен"))
    return bad


def main():
    if not LAYERS.is_dir():
        sys.exit(f"нет папки слоёв: {LAYERS}")
    text_layer("перевод", "alqasawi")
    text_layer("перевод-тафсир", "alqasawi_sharh")
    bad = slides_layer()
    print("Дальше: python3 split.py alqasawi alqasawi_sharh alqasawi_slides && "
          "python3 build_index.py alqasawi alqasawi_sharh alqasawi_slides && "
          "python3 compute_fill.py && python3 build_coverage.py && python3 sync_config.py")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
