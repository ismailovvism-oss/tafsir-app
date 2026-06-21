#!/usr/bin/env python3
"""
Универсальный конвертер переводов/тафсиров в JSON.

Поддерживаемые форматы:
  - TXT (Tanzil): сура|аят|текст
  - XML (Tanzil): <sura index="N"><aya index="N" text="..."/>
  - SQL (Tanzil): INSERT INTO ... VALUES (сура, аят, 'текст')
  - Custom TXT:   ### сура:аят + текст (наш формат)

Использование:
  python3 convert_all.py input_file output.json
  python3 convert_all.py ru_kuliev.txt kuliev.json
  python3 convert_all.py ru_kuliev.xml kuliev.json
  python3 convert_all.py ru_kuliev.sql kuliev.json
"""

import json, sys, re, os

def detect_format(text):
    if text.strip().startswith("<?xml"):
        return "xml"
    if "INSERT INTO" in text[:5000]:
        return "sql"
    if "### " in text[:500]:
        return "custom"
    if "|" in text[:200]:
        return "tanzil_txt"
    return "unknown"

def parse_tanzil_txt(text):
    """Формат: сура|аят|текст"""
    data = {}
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|", 2)
        if len(parts) < 3:
            continue
        surah, ayah, content = parts[0].strip(), parts[1].strip(), parts[2].strip()
        if not surah.isdigit():
            continue
        if surah not in data:
            data[surah] = {}
        data[surah][ayah] = content
    return data

def parse_xml(text):
    """Формат Tanzil XML: <sura index="N"><aya index="N" text="..."/>"""
    data = {}
    current_surah = None

    for line in text.split("\n"):
        line = line.strip()

        # Ищем <sura index="N">
        m = re.search(r'<sura\s+index="(\d+)"', line)
        if m:
            current_surah = m.group(1)
            if current_surah not in data:
                data[current_surah] = {}

        # Ищем <aya index="N" text="..."/>
        m = re.search(r'<aya\s+index="(\d+)"\s+text="([^"]*)"', line)
        if m and current_surah:
            ayah = m.group(1)
            content = m.group(2)
            # Декодируем HTML entities
            content = content.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
            data[current_surah][ayah] = content

    return data

def parse_sql(text):
    """Формат Tanzil SQL: INSERT INTO ... VALUES (index, сура, аят, 'текст') или (сура, аят, 'текст')"""
    data = {}

    # Формат с 4 колонками: (index, sura, aya, 'text')
    for match in re.finditer(r'\(\d+,\s*(\d+),\s*(\d+),\s*\'((?:[^\'\\]|\\.|\'\')*)\'\)', text):
        surah = match.group(1)
        ayah = match.group(2)
        content = match.group(3).replace("\\'", "'").replace("''", "'").replace("\\n", "\n")
        if surah not in data:
            data[surah] = {}
        data[surah][ayah] = content

    # Если не нашли — пробуем 3 колонки: (sura, aya, 'text')
    if not data:
        for match in re.finditer(r'\((\d+),\s*(\d+),\s*\'((?:[^\'\\]|\\.|\'\')*)\'\)', text):
            surah = match.group(1)
            ayah = match.group(2)
            content = match.group(3).replace("\\'", "'").replace("''", "'").replace("\\n", "\n")
            if surah not in data:
                data[surah] = {}
            data[surah][ayah] = content

    return data

def parse_custom(text):
    """Наш формат: ### сура:аят + текст"""
    data = {}
    parts = re.split(r'^###\s+(\d+):(\d+)\s*$', text, flags=re.MULTILINE)
    i = 1
    while i < len(parts) - 2:
        surah, ayah, content = parts[i].strip(), parts[i+1].strip(), parts[i+2].strip()
        if surah not in data:
            data[surah] = {}
        data[surah][ayah] = content
        i += 3
    return data

def convert(input_path, output_path):
    with open(input_path, 'r', encoding='utf-8') as f:
        text = f.read()

    fmt = detect_format(text)
    print(f"Формат: {fmt}")

    if fmt == "tanzil_txt":
        data = parse_tanzil_txt(text)
    elif fmt == "xml":
        data = parse_xml(text)
    elif fmt == "sql":
        data = parse_sql(text)
    elif fmt == "custom":
        data = parse_custom(text)
    else:
        print("Не удалось определить формат файла!")
        sys.exit(1)

    # Подсчёт
    total_ayat = sum(len(v) for v in data.values())
    total_surahs = len(data)

    # Сохраняем JSON
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    size_kb = os.path.getsize(output_path) / 1024

    # Генерируем JS-файл для оффлайн-режима
    js_path = output_path.rsplit('.', 1)[0] + '.js'
    tafsir_id = os.path.basename(js_path).rsplit('.', 1)[0]
    js_content = json.dumps(data, ensure_ascii=False)
    with open(js_path, 'w', encoding='utf-8') as f:
        f.write(f'window.TL_DATA=window.TL_DATA||{{}};window.TL_DATA["{tafsir_id}"]={js_content};\n')

    js_kb = os.path.getsize(js_path) / 1024

    # Разрезаем на чанки по сурам (ленивая загрузка в приложении)
    out_dir = os.path.join(os.path.dirname(output_path), tafsir_id)
    os.makedirs(out_dir, exist_ok=True)
    surahs = sorted((int(s) for s in data.keys()))
    for s in surahs:
        with open(os.path.join(out_dir, f"{s}.json"), 'w', encoding='utf-8') as f:
            json.dump(data[str(s)], f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(out_dir, "index.json"), 'w', encoding='utf-8') as f:
        json.dump(surahs, f, separators=(",", ":"))

    print(f"Готово!")
    print(f"  Сур: {total_surahs}")
    print(f"  Аятов: {total_ayat}")
    print(f"  JSON:   {output_path} ({size_kb:.1f} КБ)")
    print(f"  JS:     {js_path} ({js_kb:.1f} КБ) — для оффлайн-режима")
    print(f"  Чанки:  {out_dir}/ ({total_surahs} файлов по сурам) — для ленивой загрузки")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])
