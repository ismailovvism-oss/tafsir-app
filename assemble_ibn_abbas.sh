#!/usr/bin/env bash
# Пост-конвейер партии перевода Ибн Аббаса — одной командой.
# Запускать ИЗ КОРНЯ проекта, ПОСЛЕ того как переведены все блоки партии
# (файлы sSURA_ru/<блок>.md в папке SCRATCH).
#
# Использование:
#   ./assemble_ibn_abbas.sh SCRATCH SURA
# Пример:
#   ./assemble_ibn_abbas.sh /tmp/ibn-abbas-s11.XXXX 11
#
# Делает по порядку: механическая сверка -> сборка -> монолит+чанк ->
# поисковый индекс -> fill -> coverage -> config -> проектная валидация.
# Любой сбой останавливает конвейер (set -e). Публикация на R2/коммит/push —
# ОТДЕЛЬНО и только по прямой просьбе.

set -euo pipefail

SCRATCH="${1:?нужен путь SCRATCH}"
SURA="${2:?нужен номер суры}"
D=data/_sources/ibn_abbas_ru

echo "== 1/8 механическая сверка структуры (арабский <-> русский) =="
python3 "$D/check_translation_block.py" "$SCRATCH" "$SURA"

echo "== 2/8 сборка партии =="
python3 "$D/assemble_s3.py" "$SCRATCH" "$SURA"

echo "== 3/8 монолит + чанк суры =="
python3 sync_ibn_abbas.py monolith "$SCRATCH" "$SURA"

echo "== 4/8 поисковый индекс =="
python3 build_index.py ibn_abbas

echo "== 5/8 синхронизация индекса =="
python3 sync_ibn_abbas.py index "$SCRATCH"

echo "== 6/8 пересчёт fill =="
python3 compute_fill.py

echo "== 7/8 индекс покрытия =="
python3 build_coverage.py

echo "== 8/8 config + проектная валидация =="
python3 sync_config.py
python3 validate_data.py

echo ""
echo "ГОТОВО. Проверить в приложении:"
echo "  python3 -m http.server 8000"
echo "  http://localhost:8000/?r2local=1#${SURA}"
