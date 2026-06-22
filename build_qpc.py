#!/usr/bin/env python3
"""Build QPC v1 (King Fahd Madani mushaf) glyph data for the tafsir app.

Pulls word-level data from the quran.com API (code_v1 glyph, page, line,
char type) for all 114 surahs and emits compact per-surah + per-page chunks:

  data/qpc/v1/surah/<s>.json  -> {ayah: {"w": [[glyph, page], ...], "e": [glyph, page]|None}}
  data/qpc/v1/page/<p>.json   -> {"lines": {lineNo: [[glyph, page], ...]},
                                   "starts": [{"surah":n,"ayah":1,"line":L}, ...]}
  data/qpc/v1/meta.json       -> {"pages": 604, "surahStart": {s: {"page":P,"line":L}}}

Glyphs are Private Use Area codepoints that only render with that page's
QPC v1 font (fonts/qpc-v1/p<page>.woff2). Run: python3 build_qpc.py
"""
import json, os, sys, time, urllib.request, urllib.error

API = "https://api.quran.com/api/v4/verses/by_chapter/{s}?words=true&per_page=300&word_fields=code_v1,page_number,line_number,char_type_name"
OUT = os.path.join(os.path.dirname(__file__), "data", "qpc", "v1")
SURAH_AYAH_COUNT = None  # filled from API responses

def fetch(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "tafsir-app-build"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except (urllib.error.URLError, TimeoutError) as e:
            if i == tries - 1:
                raise
            time.sleep(1.5 * (i + 1))

def main():
    os.makedirs(os.path.join(OUT, "surah"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "page"), exist_ok=True)

    pages = {}            # page -> {line -> [[glyph,page],...]}
    page_starts = {}      # page -> [{surah,ayah,line}]
    surah_start = {}      # surah -> {page,line}
    surah_index = []

    for s in range(1, 115):
        data = fetch(API.format(s=s))
        verses = data["verses"]
        ayah_chunk = {}
        for v in verses:
            surah, ayah = map(int, v["verse_key"].split(":"))
            words, end = [], None
            for w in v["words"]:
                glyph = w.get("code_v1")
                page = w.get("page_number")
                line = w.get("line_number")
                if glyph is None or page is None:
                    continue
                if w.get("char_type_name") == "end":
                    end = [glyph, page]
                else:
                    words.append([glyph, page])
                # accumulate page layout (words + end markers, in order)
                pg = pages.setdefault(page, {})
                pg.setdefault(line, []).append([glyph, page])
                if ayah == 1 and w["position"] == 1 and surah not in surah_start:
                    surah_start[surah] = {"page": page, "line": line}
                    page_starts.setdefault(page, []).append(
                        {"surah": surah, "ayah": 1, "line": line})
            ayah_chunk[str(ayah)] = {"w": words, "e": end}
        with open(os.path.join(OUT, "surah", f"{s}.json"), "w", encoding="utf-8") as f:
            json.dump(ayah_chunk, f, ensure_ascii=False, separators=(",", ":"))
        surah_index.append(s)
        print(f"surah {s:3d}: {len(verses)} ayat", flush=True)
        time.sleep(0.15)

    # write page chunks
    for p, lines in pages.items():
        ordered = {str(ln): lines[ln] for ln in sorted(lines)}
        out = {"lines": ordered, "starts": page_starts.get(p, [])}
        with open(os.path.join(OUT, "page", f"{p}.json"), "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    meta = {
        "pages": max(pages) if pages else 0,
        "surahStart": {str(k): v for k, v in surah_start.items()},
        "surahIndex": surah_index,
    }
    with open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, separators=(",", ":"))
    print(f"done: {len(pages)} pages, {len(surah_index)} surahs", flush=True)

if __name__ == "__main__":
    main()
