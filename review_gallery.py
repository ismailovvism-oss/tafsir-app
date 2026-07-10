#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
review_gallery.py — HTML-галереи для ревью диафильм-наборов (любого агента).

Для каждого набора строит review-<label>.html: картинки сгруппированы по темам,
у каждой темы — имя (из фихриста `data/topics/names_ru.json`; для наших 25 тем —
ещё смысл и ⛔ «что запрещено» из filmstrip-manifest.json). Под картинкой — имя
файла и, если тема есть в манифесте, метафора конкретного варианта (v01→metaphors[0]).
Файлы `default-NN.png` собираются в раздел «Без темы (общий фон)».

Клик по картинке помечает её на удаление; кнопка выдаёт готовые `rm`-команды.

Запуск:
    python3 review_gallery.py                       # seedream, nano, grok, codex
    python3 review_gallery.py --sets seedream nano
Открывать через локальный сервер (иначе картинки не грузятся):
    python3 -m http.server 8000  →  http://localhost:8000/review-seedream.html
"""
import argparse
import html
import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(ROOT, "data", "media", "filmstrip-manifest.json")
NAMES = os.path.join(ROOT, "data", "topics", "names_ru.json")
TOPIC_RE = re.compile(r"^topic-(\d+)-(\d+)\.(png|jpg|jpeg|webp)$", re.I)
DEFAULT_RE = re.compile(r"^default-(\d+)\.(png|jpg|jpeg|webp)$", re.I)

# набор (label) → папка относительно корня репозитория
SETS = {
    "seedream": "data/media/filmstrip-fal/seedream",
    "nano":     "data/media/filmstrip-fal/nano-banana-pro",
    "grok":     "data/media/filmstrip-grok-build",
    "codex":    "data/media/filmstrip",
}

PAGE = """<!doctype html><html lang=ru><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Ревью · {label}</title>
<style>
 :root{{color-scheme:dark}}
 body{{margin:0;background:#111;color:#eee;font:15px/1.4 system-ui,sans-serif}}
 header{{position:sticky;top:0;z-index:10;background:#1b1b1bee;backdrop-filter:blur(6px);
   padding:10px 14px;border-bottom:1px solid #333;display:flex;gap:14px;align-items:center;flex-wrap:wrap}}
 header b{{font-size:17px}} .muted{{color:#999}}
 button{{background:#2a2a2a;color:#eee;border:1px solid #444;border-radius:8px;padding:7px 12px;cursor:pointer;font-size:14px}}
 button:hover{{background:#333}}
 .topic{{padding:16px 14px 4px}}
 .topic h2{{margin:0 0 2px;font-size:18px}}
 .topic .meta{{color:#bbb;font-size:13px;margin:0 0 2px}}
 .topic .avoid{{color:#e6a;font-size:12.5px;margin:0 0 8px}}
 .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px;padding:0 14px 8px}}
 figure{{margin:0;position:relative;border:2px solid transparent;border-radius:10px;overflow:hidden;background:#000;cursor:pointer}}
 figure img{{width:100%;display:block;aspect-ratio:16/9;object-fit:cover}}
 figcaption{{padding:6px 8px;font-size:12.5px;color:#cdd}}
 figcaption .mph{{color:#9cf}} figcaption .fn{{color:#888;font-size:11px}}
 figure.rej{{border-color:#e33}}
 figure.rej::after{{content:"✕ УДАЛИТЬ";position:absolute;inset:0;display:flex;align-items:center;
   justify-content:center;font-size:26px;font-weight:700;color:#fff;background:rgba(200,20,20,.45)}}
 #panel{{position:fixed;inset:auto 0 0 0;background:#1b1b1bf2;border-top:1px solid #444;padding:10px 14px;display:none}}
 #panel.show{{display:block}} textarea{{width:100%;height:110px;background:#000;color:#6f6;border:1px solid #444;border-radius:8px;font:12px monospace;padding:8px;box-sizing:border-box}}
</style></head><body>
<header>
 <b>Ревью: {label}</b>
 <span class=muted>{count} картинок · {ntopics} тем</span>
 <span class=muted>клик по картинке = пометить на удаление</span>
 <span style=flex:1></span>
 <span id=cnt class=muted>помечено: 0</span>
 <button onclick=showRm()>Показать команды удаления</button>
 <button onclick=clearAll()>Снять все пометки</button>
</header>
{body}
<div id=panel>
 <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
   <b>Скопируй и вставь в терминал (из корня репозитория):</b>
   <button onclick="document.getElementById('panel').classList.remove('show')">закрыть</button>
 </div>
 <textarea id=rm readonly onclick=this.select()></textarea>
</div>
<script>
const KEY="review-reject-{label}";
let rej=new Set(JSON.parse(localStorage.getItem(KEY)||"[]"));
function paint(){{document.querySelectorAll('figure').forEach(f=>f.classList.toggle('rej',rej.has(f.dataset.f)));
  document.getElementById('cnt').textContent="помечено: "+rej.size;}}
function toggle(f){{const k=f.dataset.f;if(rej.has(k))rej.delete(k);else rej.add(k);
  localStorage.setItem(KEY,JSON.stringify([...rej]));paint();}}
function showRm(){{const p=document.getElementById('panel'),t=document.getElementById('rm');
  t.value=[...rej].sort().map(f=>"rm '"+f+"'").join("\\n")||"# ничего не помечено";
  p.classList.add('show');t.select();}}
function clearAll(){{if(!confirm('Снять все пометки?'))return;rej.clear();localStorage.removeItem(KEY);paint();}}
document.querySelectorAll('figure').forEach(f=>f.addEventListener('click',()=>toggle(f)));
paint();
</script></body></html>"""


def esc(s):
    return html.escape(str(s or ""))


def load_lookups():
    with open(MANIFEST, encoding="utf-8") as f:
        man = {t["id"]: t for t in json.load(f)["topics"]}
    names = {}
    if os.path.exists(NAMES):
        with open(NAMES, encoding="utf-8") as f:
            names = json.load(f)
    return man, names


def build(label, reldir, manifest, names):
    d = os.path.join(ROOT, reldir)
    if not os.path.isdir(d):
        print(f"  пропуск {label}: нет папки {reldir}")
        return
    by_topic = {}
    defaults = []
    for f in sorted(os.listdir(d)):
        m = TOPIC_RE.match(f)
        if m:
            by_topic.setdefault(m.group(1), []).append((int(m.group(2)), f))
            continue
        if DEFAULT_RE.match(f):
            defaults.append(f)
    count = sum(len(v) for v in by_topic.values()) + len(defaults)

    def card(fname, label_html):
        rel = f"{reldir}/{fname}"
        return (f'<figure data-f="{esc(rel)}"><img loading=lazy src="/{esc(rel)}" alt="">'
                f'<figcaption>{label_html}<br><span class=fn>{esc(fname)}</span></figcaption></figure>')

    blocks = []
    for tid in sorted(by_topic, key=lambda x: int(x)):
        t = manifest.get(tid)
        name = (t or {}).get("name") or names.get(tid) or f"тема {tid}"
        meaning = (t or {}).get("meaning", "")
        avoid = (t or {}).get("avoid", "")
        metas = (t or {}).get("metaphors", [])
        cards = []
        for nn, fname in sorted(by_topic[tid]):
            mph = metas[nn - 1] if 1 <= nn <= len(metas) else ""
            lab = f'<span class=mph>v{nn:02d}{" · " + esc(mph) if mph else ""}</span>'
            cards.append(card(fname, lab))
        blocks.append(
            f'<div class=topic><h2>{esc(name)} <span class=muted>#{esc(tid)}</span></h2>'
            + (f'<p class=meta>{esc(meaning)}</p>' if meaning else "")
            + (f'<p class=avoid>⛔ {esc(avoid)}</p>' if avoid else "")
            + f'<div class=grid>{"".join(cards)}</div></div>'
        )
    if defaults:
        cards = [card(fn, '<span class=mph>default (общий фон)</span>') for fn in sorted(defaults)]
        blocks.append('<div class=topic><h2>Без темы <span class=muted>default</span></h2>'
                      f'<div class=grid>{"".join(cards)}</div></div>')

    ntopics = len(by_topic) + (1 if defaults else 0)
    page = PAGE.format(label=esc(label), count=count, ntopics=ntopics, body="\n".join(blocks))
    out = os.path.join(ROOT, f"review-{label}.html")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"  OK → review-{label}.html  ({count} картинок, {ntopics} тем)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", nargs="*", default=list(SETS.keys()),
                    help="какие наборы строить (по умолчанию все)")
    args = ap.parse_args()
    manifest, names = load_lookups()
    print("Сборка галерей ревью:")
    for s in args.sets:
        reldir = SETS.get(s)
        if not reldir:
            print(f"  неизвестный набор: {s} (есть: {', '.join(SETS)})")
            continue
        build(s, reldir, manifest, names)
    print("\nОткрывай через локальный сервер (python3 -m http.server 8000):")
    for s in args.sets:
        if s in SETS:
            print(f"  http://localhost:8000/review-{s}.html")


if __name__ == "__main__":
    main()
