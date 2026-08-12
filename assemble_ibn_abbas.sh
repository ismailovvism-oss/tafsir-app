#!/usr/bin/env bash
# Пост-конвейер партии перевода Ибн Аббаса — одной командой.
# Запускать ИЗ КОРНЯ проекта, ПОСЛЕ того как переведены все блоки партии
# (файлы sSURA_ru/<блок>.md в папке SCRATCH).
#
# Использование:
#   ./assemble_ibn_abbas.sh SCRATCH SURA [SURA ...]
# Примеры:
#   ./assemble_ibn_abbas.sh /tmp/ibn-abbas-s11.XXXX 11
#   ATHAR_DST=imams5 ./assemble_ibn_abbas.sh /tmp/imams5 6 7 8      # костяк
#
# Тот же конвейер обслуживает любой слой корпуса: куда класть русский —
# переменная ATHAR_DST (по умолчанию ibn_abbas), её же читают assemble_s3.py и
# sync_ibn_abbas.py. Шаги 1-3 идут по каждой суре, 4-8 — один раз в конце.
# Любой сбой останавливает конвейер (set -e). Публикация на R2/коммит/push —
# ОТДЕЛЬНО и только по прямой просьбе.

set -euo pipefail

SCRATCH="${1:?нужен путь SCRATCH}"
shift
[ "$#" -gt 0 ] || { echo "нужен номер суры (можно несколько)" >&2; exit 1; }
SURAS=("$@")
DST="${ATHAR_DST:-ibn_abbas}"
export ATHAR_DST="$DST"
D=data/_sources/ibn_abbas_ru

for SURA in "${SURAS[@]}"; do
  echo "== 1/8 сура $SURA: механическая сверка структуры (арабский <-> русский) =="
  python3 "$D/check_translation_block.py" "$SCRATCH" "$SURA"

  echo "== 2/8 сура $SURA: сборка партии =="
  python3 "$D/assemble_s3.py" "$SCRATCH" "$SURA"

  echo "== 3/8 сура $SURA: монолит + чанк =="
  python3 sync_ibn_abbas.py monolith "$SCRATCH" "$SURA"
done

SURA="${SURAS[-1]}"

echo "== 4/8 поисковый индекс ($DST) =="
python3 build_index.py "$DST"

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
