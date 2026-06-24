#!/usr/bin/env python3
"""
Считает «наполненность» каждого источника = доля реальных аятов от полного
Корана (6236) и записывает поле "fill" (0..1) в data/config.json и data/config.js.

Реальным считается аят с непустым текстом, не являющийся заглушкой
(не начинается с «※» — маркер отсутствующего аята).

Запуск:  python3 compute_fill.py
"""
import json, os, re

ROOT = os.path.dirname(os.path.abspath(__file__))
TAF = os.path.join(ROOT, "data", "tafsirs")
TOTAL = 6236  # аятов в Коране (стандартная нумерация)


def count_real(tid):
    path = os.path.join(TAF, tid + ".json")
    if not os.path.isfile(path):
        return 0
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
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


def main():
    cfg_json = os.path.join(ROOT, "data", "config.json")
    cfg = json.load(open(cfg_json, encoding="utf-8"))
    fills = {}
    for t in cfg["tafsirs"]:
        if t.get("kind") == "image":      # скан-источники: fill задаётся вручную
            fills[t["id"]] = t.get("fill", 0)
            continue
        f = round(min(1.0, count_real(t["id"]) / TOTAL), 4)
        t["fill"] = f
        fills[t["id"]] = f
    json.dump(cfg, open(cfg_json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    # config.js (offline mirror)
    cfg_js = os.path.join(ROOT, "data", "config.js")
    txt = open(cfg_js, encoding="utf-8").read()
    m = re.match(r"\s*window\.TL_CONFIG=(.*?);\s*$", txt, re.S)
    obj = json.loads(m.group(1))
    for t in obj["tafsirs"]:
        t["fill"] = fills.get(t["id"], 0)
    open(cfg_js, "w", encoding="utf-8").write(
        "window.TL_CONFIG=" + json.dumps(obj, ensure_ascii=False) + ";\n")

    for tid, f in sorted(fills.items(), key=lambda x: x[1]):
        print(f"  {tid:16} {f*100:6.1f}%")
    print(f"Готово: {len(fills)} источников.")


if __name__ == "__main__":
    main()
