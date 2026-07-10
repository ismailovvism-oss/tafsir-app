#!/usr/bin/env python3
"""Собрать карту визуального набора (pack) из папки с PNG.

Правила (мульти-агент):
  • Каждый агент пишет картинки ТОЛЬКО в свою папку.
  • Карта набора — data/media/visual/<pack>.json (не общий visual.json).
  • Имя файла обязано содержать id темы: topic-<id>-<nn>.png
    → карту можно пересобрать без ручной правки и без конфликтов.

Примеры:
  python3 build_visual_pack.py \\
      --pack grok-build \\
      --dir data/media/filmstrip-grok-build \\
      --agent grok-build

  python3 build_visual_pack.py --pack filmstrip --dir data/media/filmstrip --agent codex
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TOPIC_RE = re.compile(r"^topic-(\d+)-(\d+)\.(png|jpg|jpeg|webp)$", re.I)
DEFAULT_RE = re.compile(r"^default-(\d+)\.(png|jpg|jpeg|webp)$", re.I)
# опционально: pin-2-255-01.png → pins["2:255"]
PIN_RE = re.compile(r"^pin-(\d+)-(\d+)-(\d+)\.(png|jpg|jpeg|webp)$", re.I)


def build(pack: str, media_dir: Path, agent: str, out: Path, rel_prefix: str | None) -> dict:
    if not media_dir.is_dir():
        raise SystemExit(f"нет папки: {media_dir}")

    # пути в карте — относительно data/media/ (resolveUrl visual_media → media/{file})
    prefix = rel_prefix if rel_prefix is not None else media_dir.as_posix().removeprefix("data/media/").removeprefix("data/media")
    prefix = prefix.strip("/")
    if not prefix:
        prefix = media_dir.name

    topics: dict[str, list[str]] = {}
    defaults: list[str] = []
    pins: dict[str, str] = {}
    unknown: list[str] = []

    for p in sorted(media_dir.iterdir()):
        if not p.is_file() or p.name.startswith("."):
            continue
        name = p.name
        m = TOPIC_RE.match(name)
        if m:
            tid, _nn = m.group(1), m.group(2)
            topics.setdefault(tid, []).append(f"{prefix}/{name}")
            continue
        m = DEFAULT_RE.match(name)
        if m:
            defaults.append(f"{prefix}/{name}")
            continue
        m = PIN_RE.match(name)
        if m:
            s, a, _nn = m.group(1), m.group(2), m.group(3)
            key = f"{s}:{a}"
            # первый файл на аят; остальные в topics не кладём (pin = одна картинка)
            if key not in pins:
                pins[key] = f"{prefix}/{name}"
            continue
        if name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            unknown.append(name)

    # стабильный порядок
    for tid in topics:
        topics[tid] = sorted(topics[tid])
    topics = dict(sorted(topics.items(), key=lambda kv: int(kv[0])))
    defaults = sorted(defaults)

    doc = (
        f"Карта набора «{pack}» (агент {agent}). "
        f"Собрана скриптом build_visual_pack.py из {prefix}/. "
        f"Имена: topic-<id>-<nn>.png, default-<nn>.png, pin-<sura>-<ayah>-<nn>.png. "
        f"НЕ править data/media/visual.json этим набором — только этот файл."
    )
    data = {
        "_doc": doc,
        "_pack": pack,
        "_agent": agent,
        "_mediaDir": prefix,
        "_builtBy": "build_visual_pack.py",
        "render_type": "image",
        "topics": topics,
        "default": defaults,
        "pins": pins,
    }
    if unknown:
        data["_unknownFiles"] = unknown

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def main() -> None:
    ap = argparse.ArgumentParser(description="Собрать data/media/visual/<pack>.json из папки PNG")
    ap.add_argument("--pack", required=True, help="id набора → visual/<pack>.json")
    ap.add_argument("--dir", required=True, type=Path, help="папка с PNG (своя у агента)")
    ap.add_argument("--agent", default="", help="метка агента (grok-build, codex, …)")
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="куда писать (по умолчанию data/media/visual/<pack>.json)",
    )
    ap.add_argument(
        "--rel-prefix",
        default=None,
        help="префикс путей в карте (по умолчанию путь dir относительно data/media/)",
    )
    args = ap.parse_args()
    agent = args.agent or args.pack
    out = args.out or Path("data/media/visual") / f"{args.pack}.json"
    data = build(args.pack, args.dir, agent, out, args.rel_prefix)
    n_topics = len(data["topics"])
    n_imgs = sum(len(v) for v in data["topics"].values())
    print(
        f"OK → {out}  topics={n_topics} topic_imgs={n_imgs} "
        f"default={len(data['default'])} pins={len(data['pins'])}"
        + (f" unknown={len(data.get('_unknownFiles', []))}" if data.get("_unknownFiles") else "")
    )


if __name__ == "__main__":
    main()
