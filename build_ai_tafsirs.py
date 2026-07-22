#!/usr/bin/env python3
"""
Импорт ИИ-тафсиров для детей и подростков из Obsidian-вольта в данные приложения.

Источник (авторский формат, Obsidian Publish):
  ~/obsid/qaadiy/Ислам/Коран/Тафсир/ИИ/{детям,подросткам}/<сура>/<a-b>.md

Преобразование в подмножество Markdown приложения:
  - арабские цитаты аятов выбрасываются (лента и так показывает арабский);
  - <span style=...>(пояснение)</span> -> обычный текст (перевод остаётся жирным,
    пояснения — обычным шрифтом: два слоя сохраняются контрастом);
  - callout-мостики (> [!tip]- 🌉 …, > [!note]- 🔗 …) -> обычные цитаты;
  - введение порции -> к первому аяту порции (### + цитата);
  - финальные блоки (✨/💚/🎯/➡️, 💎/🕋/🚀/🔗) -> к последнему аяту порции (###).

Выход: data/tafsirs/<id>.json (монолит), data/tafsirs/<id>/<сура>.json (чанки),
data/tafsirs/<id>/index.json. Скрипт идемпотентен.
После него: compute_fill.py, build_coverage.py, build_index.py <ids>, sync_config.py.
"""
import json
import os
import re
import sys

VAULT = os.path.expanduser("~/obsid/qaadiy/Ислам/Коран/Тафсир/ИИ")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "tafsirs")

SOURCES = {
    "detyam": "детям",
    "podrostkam": "подросткам",
}

AR_RE = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")
SPAN_RE = re.compile(r"<span\b[^>]*>(.*?)</span>", re.S)  # и style=, и class="sharh"
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)  # контрольные блоки «ПРОВЕРИТЬ» и пр.
AYAH_RE = re.compile(r"^\*\*(\d+)\.\*\*\s*(.*)$")
CALLOUT_RE = re.compile(r"^>\s*\[!\w+\]-?\s*(.*)$")


def convert_inline(text):
    """HTML-спаны -> обычный текст; прочее оставляем как есть.

    Снимаем итеративно: SPAN_RE нежадный и на вложенных <span> без цикла
    оставил бы литеральные теги. Цикл распрямляет любую глубину изнутри наружу.
    """
    for _ in range(10):
        new = SPAN_RE.sub(lambda m: m.group(1).strip(), text)
        if new == text:
            break
        text = new
    return text


def is_arabic_quote(line):
    s = line.lstrip("> ").strip()
    return bool(s) and bool(AR_RE.match(s[0])) and "[!" not in line


def parse_portion(path):
    """Разбирает один файл порции -> (intro, {аят: текст}, outro)."""
    raw = open(path, encoding="utf-8").read()
    raw = COMMENT_RE.sub("", raw)  # HTML-комментарии (контрольный блок) — вон
    # нормализация слитного заголовка аята «**8. текст**» -> «**8.** **текст**»
    # (некоторые агенты пишут номер внутри того же жирного, что и перевод)
    raw = re.sub(r"(?m)^\*\*(\d+)\. (?!\*)", r"**\1.** **", raw)
    lines = raw.splitlines()
    # YAML-фронтматтер ревизии (--- … ---) в начале файла
    if lines and lines[0].strip() == "---":
        for j in range(1, len(lines)):
            if lines[j].strip() == "---":
                lines = lines[j + 1:]
                break

    intro_lines = []     # цитата введения
    ayahs = {}           # n -> [строки]
    outro_lines = []     # финальные секции (## ...)
    cur = None           # текущий аят
    state = "head"       # head -> intro -> body -> outro

    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()

        if state in ("head", "intro") and re.match(r"^##\s+[^#]", s):
            # первый ## — введение; второй ## — начало тела
            state = "intro" if state == "head" else "body"
            i += 1
            continue
        if state == "body" and re.match(r"^##\s+[^#]", s):
            state = "outro"
            outro_lines.append("### " + s.lstrip("# ").strip())
            i += 1
            continue

        if state == "head":
            i += 1
            continue

        if state == "intro":
            if s.startswith(">"):
                intro_lines.append(convert_inline(s.lstrip("> ").strip()))
            i += 1
            continue

        if state == "outro":
            if re.match(r"^##\s+[^#]", s):
                outro_lines.append("### " + s.lstrip("# ").strip())
            else:
                outro_lines.append(convert_inline(line.rstrip()))
            i += 1
            continue

        # --- body ---
        if not s or s == "---":
            if cur is not None and ayahs[cur] and ayahs[cur][-1] != "":
                ayahs[cur].append("")
            i += 1
            continue

        if is_arabic_quote(line) or "{{ayah:" in s:
            i += 1
            continue

        m = AYAH_RE.match(s)
        if m:
            cur = int(m.group(1))
            ayahs[cur] = [convert_inline(m.group(2)).strip()]
            i += 1
            continue

        cm = CALLOUT_RE.match(s)
        if cm:
            title = cm.group(1).strip()
            block = ["> **%s**" % title if title else ">"]
            i += 1
            while i < len(lines) and lines[i].strip().startswith(">"):
                inner = lines[i].strip().lstrip("> ").strip()
                if not is_arabic_quote(lines[i]):
                    block.append("> " + convert_inline(inner))
                i += 1
            if cur is not None:
                ayahs[cur] += [""] + block
            continue

        # прочий текст тела — к текущему аяту
        if cur is not None:
            ayahs[cur].append(convert_inline(s))
        i += 1

    intro = "\n".join("> " + l if l else ">" for l in intro_lines).strip()
    outro = re.sub(r"\n{3,}", "\n\n", "\n".join(outro_lines)).strip()
    return intro, {n: re.sub(r"\n{3,}", "\n\n", "\n".join(v)).strip() for n, v in ayahs.items()}, outro


def build_source(sid, folder):
    src_dir = os.path.join(VAULT, folder)
    mono = {}
    for sura in sorted((d for d in os.listdir(src_dir) if d.isdigit()), key=int):
        sura_dir = os.path.join(src_dir, sura)
        portions = sorted(
            (f for f in os.listdir(sura_dir) if re.match(r"^\d+-\d+\.md$", f)),
            key=lambda f: int(f.split("-")[0]),
        )
        stexts = {}
        for k, fname in enumerate(portions):
            intro, ayahs, outro = parse_portion(os.path.join(sura_dir, fname))
            if not ayahs:
                print(f"  ! {sid} {sura}/{fname}: не найдено аятов, пропуск")
                continue
            first, last = min(ayahs), max(ayahs)
            if intro:
                title = "### 🌟 О чём этот отрывок?" if sid == "detyam" else "### 🌅 Контекст отрывка"
                ayahs[first] = title + "\n" + intro + "\n\n" + ayahs[first]
            if outro:
                ayahs[last] = ayahs[last] + "\n\n" + outro
            for n, t in ayahs.items():
                if str(n) in stexts:
                    print(f"  ! {sid} {sura}: аят {n} дублируется ({fname})")
                stexts[str(n)] = t
        if stexts:
            mono[sura] = stexts

    # запись: монолит + чанки + index.json
    out_dir = os.path.join(OUT, sid)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(OUT, sid + ".json"), "w", encoding="utf-8") as f:
        json.dump(mono, f, ensure_ascii=False, indent=0)
    for old in os.listdir(out_dir):
        if old.endswith(".json"):
            os.remove(os.path.join(out_dir, old))
    for sura, stexts in mono.items():
        with open(os.path.join(out_dir, sura + ".json"), "w", encoding="utf-8") as f:
            json.dump(stexts, f, ensure_ascii=False, indent=0)
    with open(os.path.join(out_dir, "index.json"), "w", encoding="utf-8") as f:
        json.dump(sorted((int(s) for s in mono), key=int), f)
    n_ayahs = sum(len(v) for v in mono.values())
    print(f"{sid}: {len(mono)} сур, {n_ayahs} аятов")
    return mono


def main():
    for sid, folder in SOURCES.items():
        build_source(sid, folder)
    print("Дальше: compute_fill.py && build_coverage.py && "
          "build_index.py detyam podrostkam && sync_config.py")


if __name__ == "__main__":
    main()
