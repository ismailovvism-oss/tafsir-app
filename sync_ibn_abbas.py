#!/usr/bin/env python3
"""Synchronize the Russian Ibn Abbas chunk, monoliths and R2 search index.

The script keeps recoverable pre-sync copies under the explicitly supplied
scratch directory and uses atomic replacement for every destination.

Usage:
  python3 sync_ibn_abbas.py monolith SCRATCH SURA
  python3 sync_ibn_abbas.py index SCRATCH
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile


ROOT = Path(__file__).resolve().parent
SOURCE_ID = "ibn_abbas"


def backup_once(source: Path, backup: Path) -> None:
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        shutil.copy2(source, backup)


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(value, output, ensure_ascii=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    try:
        with source.open("rb") as src, os.fdopen(fd, "wb") as output:
            shutil.copyfileobj(src, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def sync_monolith(scratch: Path, sura: str) -> None:
    chunk_path = ROOT / "r2-data" / "tafsirs" / SOURCE_ID / f"{sura}.json"
    with chunk_path.open(encoding="utf-8") as source:
        chunk = json.load(source)

    targets = (
        ROOT / "data" / "tafsirs" / f"{SOURCE_ID}.json",
        ROOT / "r2-data" / "tafsirs" / f"{SOURCE_ID}.json",
    )
    for target in targets:
        with target.open(encoding="utf-8") as source:
            monolith = json.load(source)
        backup_name = f"{target.parent.parent.name}-{target.name}.before-sync"
        backup_once(target, scratch / "backups" / backup_name)
        monolith[sura] = chunk
        atomic_json(target, monolith)
        with target.open(encoding="utf-8") as source:
            written = json.load(source)
        if written.get(sura) != chunk:
            raise RuntimeError(f"monolith verification failed: {target}")
        print(f"synced {sura}: {len(chunk)} entries -> {target.relative_to(ROOT)}")


def sync_index(scratch: Path) -> None:
    source = ROOT / "data" / "index" / f"{SOURCE_ID}.json"
    destination = ROOT / "r2-data" / "index" / f"{SOURCE_ID}.json"
    with source.open(encoding="utf-8") as stream:
        json.load(stream)
    backup_once(destination, scratch / "backups" / "r2-index-ibn_abbas.json.before-sync")
    atomic_copy(source, destination)
    if source.read_bytes() != destination.read_bytes():
        raise RuntimeError("R2 index verification failed")
    print(f"synced index -> {destination.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    monolith = subparsers.add_parser("monolith")
    monolith.add_argument("scratch", type=Path)
    monolith.add_argument("sura")

    index = subparsers.add_parser("index")
    index.add_argument("scratch", type=Path)

    args = parser.parse_args()
    if args.command == "monolith":
        sync_monolith(args.scratch, str(int(args.sura)))
    else:
        sync_index(args.scratch)


if __name__ == "__main__":
    main()
