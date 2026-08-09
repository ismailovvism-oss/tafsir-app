#!/usr/bin/env python3
"""Разделить источник Ибн Аббаса на ДВА: его асары и «Тафсир 5 имамов».

Свод «аль-Мавсу'а фи-т-тафсир аль-ма'сур» даёт по каждому аяту два разных слоя:
  • АСАРЫ передатчиков — «NNNN- عن فلان …» (по-русски «NNNN — От такого-то …»);
  • РЕДАКЦИОННЫЕ СВОДКИ — «NNNN فلان …» (номер БЕЗ тире), где редакция излагает
    выбор и уточнения пяти имамов тафсира: Ибн Джарира ат-Табари, Ибн Атыйи,
    Ибн Таймийи, Ибн аль-Кайима и Ибн Касира.

`build_athar.py` при выделении раздела учёного оставлял ОБА слоя, поэтому в
`ibn_abbas` 46% текста — сводки, к самому Ибн Аббасу не относящиеся, и они же
пропадали на аятах, где его асаров нет. Этот скрипт разводит слои:

  ibn_abbas / ibn_abbas_ar  → только заголовки секций + асары Ибн Аббаса;
  imams5    / imams5_ar     → только заголовки секций + сводки пяти имамов.

Заголовок секции (`﴿цитата﴾ - тип` / `**цитата** — Тип`) остаётся в ТОМ источнике,
где у этой секции что-то есть; пустые заголовки не переносятся.
Абзац без номера — продолжение предыдущего (иснад-оценка, вторая часть сводки),
уходит вместе с ним. Сноски `[^N]` пересобираются и перенумеровываются заново.

Использование:
  python3 build_imams5.py --report          # что отделится, без записи
  python3 build_imams5.py --apply           # записать чанки+монолиты (с .bak)

Дальше как обычно: build_index.py imams5 && compute_fill.py && build_coverage.py
&& sync_config.py && validate_data.py, затем ./upload_r2.sh
"""
import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
R2 = os.path.join(ROOT, "r2-data", "tafsirs")
LOCAL = os.path.join(ROOT, "data", "tafsirs")

PAIRS = [("ibn_abbas", "imams5"), ("ibn_abbas_ar", "imams5_ar")]

RU_ASAR = re.compile(r"^\d{3,6}\s*—")
RU_EDIT = re.compile(r"^\d{3,6}(?!\s*—)\s")
RU_HEAD = re.compile(r"^\*\*.+?\*\*\s*—\s*\S", re.S)
AR_ASAR = re.compile(r"^[٠-٩]+\s*-")
AR_EDIT = re.compile(r"^[٠-٩]+(?!\s*-)\s")
AR_HEAD = re.compile(r"^﴿")
FOOT_DEF = re.compile(r"^\[\^(\d+)\]:\s*(.*)$", re.S)
FOOT_REF = re.compile(r"\[\^(\d+)\]")


def units(text, arabic):
    """Разобрать текст аята в секции: [{head, items:[(kind, text)]}].

    kind = "asar" | "edit". Абзац без номера примыкает к предыдущему элементу,
    а если такого нет — к заголовку секции (преамбула).
    """
    head_rx, asar_rx, edit_rx = (
        (AR_HEAD, AR_ASAR, AR_EDIT) if arabic else (RU_HEAD, RU_ASAR, RU_EDIT)
    )
    sections = [{"head": [], "items": []}]
    defs = {}
    for para in re.split(r"\n\s*\n", text):
        p = para.strip()
        if not p:
            continue
        m = FOOT_DEF.match(p)
        if m:
            defs[m.group(1)] = m.group(2)
            continue
        if head_rx.match(p):
            sections.append({"head": [p], "items": []})
        elif asar_rx.match(p):
            sections[-1]["items"].append(["asar", [p]])
        elif edit_rx.match(p):
            sections[-1]["items"].append(["edit", [p]])
        elif sections[-1]["items"]:
            sections[-1]["items"][-1][1].append(p)
        else:
            sections[-1]["head"].append(p)
    return sections, defs


def render(sections, defs, keep):
    """Собрать текст только из элементов вида keep; заголовки — если непусты."""
    out = []
    for sec in sections:
        items = [it for it in sec["items"] if it[0] == keep]
        if not items and not (sec["head"] and not sec["items"]):
            continue
        if not items and sec["head"] and sec["items"]:
            continue
        out.extend(sec["head"])
        for _, paras in items:
            out.extend(paras)
    body = "\n\n".join(out).strip()
    if not body:
        return ""
    used = []
    for n in FOOT_REF.findall(body):
        if n in defs and n not in used:
            used.append(n)
    if used:
        renum = {old: str(i + 1) for i, old in enumerate(used)}
        body = FOOT_REF.sub(lambda m: f"[^{renum.get(m.group(1), m.group(1))}]", body)
        body += "\n\n" + "\n".join(f"[^{renum[o]}]: {defs[o]}" for o in used)
    return body


def process(src_id, new_id, apply_changes):
    chunk_dir = os.path.join(R2, src_id)
    suras = sorted(json.load(open(os.path.join(chunk_dir, "index.json"))), key=int)
    kept_mono, new_mono = {}, {}
    stat = dict(asar=0, edit=0, lost=0, ayat_src=0, ayat_new=0)
    for s in suras:
        chunk = json.load(open(os.path.join(chunk_dir, f"{s}.json")))
        kept, new = {}, {}
        for ayah, text in chunk.items():
            arabic = src_id.endswith("_ar")
            sections, defs = units(text, arabic)
            n_asar = sum(1 for sec in sections for it in sec["items"] if it[0] == "asar")
            n_edit = sum(1 for sec in sections for it in sec["items"] if it[0] == "edit")
            stat["asar"] += n_asar
            stat["edit"] += n_edit
            a_text = render(sections, defs, "asar")
            e_text = render(sections, defs, "edit")
            if n_asar and not a_text:
                stat["lost"] += 1
            if a_text:
                kept[ayah] = a_text
            if e_text and n_edit:
                new[ayah] = e_text
        stat["ayat_src"] += len(kept)
        stat["ayat_new"] += len(new)
        kept_mono[s], new_mono[s] = kept, new
        if apply_changes:
            write_chunk(chunk_dir, s, kept, backup=True)
            write_chunk(os.path.join(R2, new_id), s, new, backup=False)
    if apply_changes:
        for path in (os.path.join(R2, f"{src_id}.json"), os.path.join(LOCAL, f"{src_id}.json")):
            shutil.copy(path, path + ".imams5.bak")
            json.dump(kept_mono, open(path, "w"), ensure_ascii=False)
        for path in (os.path.join(R2, f"{new_id}.json"), os.path.join(LOCAL, f"{new_id}.json")):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            json.dump({s: v for s, v in new_mono.items() if v}, open(path, "w"), ensure_ascii=False)
        json.dump([s for s in suras if new_mono[s]],
                  open(os.path.join(R2, new_id, "index.json"), "w"), ensure_ascii=False)
    print(f"{src_id}: асаров {stat['asar']}, сводок {stat['edit']}; "
          f"остаётся аятов {stat['ayat_src']}, у {new_id} аятов {stat['ayat_new']}"
          + (f"; ПОТЕРЯНО аятов {stat['lost']}" if stat["lost"] else ""))
    return stat


def write_chunk(directory, sura, data, backup):
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{sura}.json")
    if backup and os.path.exists(path) and not os.path.exists(path + ".imams5.bak"):
        shutil.copy(path, path + ".imams5.bak")
    if data:
        json.dump(data, open(path, "w"), ensure_ascii=False)
    elif os.path.exists(path) and not backup:
        os.remove(path)


def main():
    apply_changes = "--apply" in sys.argv
    if not apply_changes and "--report" not in sys.argv:
        print(__doc__)
        return
    for src_id, new_id in PAIRS:
        process(src_id, new_id, apply_changes)
    print("готово" + ("" if apply_changes else " (отчёт; ничего не записано)"))


if __name__ == "__main__":
    main()
