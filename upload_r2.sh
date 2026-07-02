#!/usr/bin/env bash
# Заливка тяжёлых данных (сканы webp, монолиты/чанки/индексы тяжёлых источников)
# на Cloudflare R2. Зеркало лежит в ./r2-data/ и 1-в-1 ложится в КОРЕНЬ бакета:
#   r2-data/img/<id>/pNNN.webp   -> <bucket>/img/<id>/pNNN.webp   (класс mushaf_scans)
#   r2-data/tafsirs/<id>.json    -> <bucket>/tafsirs/<id>.json    (монолит)
#   r2-data/tafsirs/<id>/<s>.json-> <bucket>/tafsirs/<id>/<s>.json(чанки)
#   r2-data/index/<id>.json      -> <bucket>/index/<id>.json      (индекс поиска)
#
# Инкрементально: rclone сверяет размер+mtime и грузит ТОЛЬКО изменённое.
#
# Использование:
#   ./upload_r2.sh              # copy: залить новое/изменённое (НИЧЕГО не удаляет)
#   ./upload_r2.sh --dry-run    # показать, что бы залилось, без заливки
#   ./upload_r2.sh --prune      # sync: как copy, НО удаляет на R2 лишнее (чистка)
#   ./upload_r2.sh tafsirs      # ограничить одним подкаталогом (tafsirs|index|img)
# Флаги можно комбинировать: ./upload_r2.sh --dry-run --prune index
set -euo pipefail

RCLONE="${RCLONE:-$HOME/.local/bin/rclone}"
REMOTE="${R2_REMOTE:-r2}"                 # имя remote в rclone.conf
BUCKET="${R2_BUCKET:-tafsir-data}"        # имя бакета R2  (перебивается env R2_BUCKET)
SRC="$(cd "$(dirname "$0")" && pwd)/r2-data"

MODE="copy"; DRY=(); ONLY=""
for a in "$@"; do
  case "$a" in
    --prune)   MODE="sync" ;;
    --dry-run) DRY=(--dry-run) ;;
    img|index|tafsirs) ONLY="$a" ;;
    *) echo "неизвестный аргумент: $a" >&2; exit 2 ;;
  esac
done

SUBSRC="$SRC"; SUBDST=""
if [[ -n "$ONLY" ]]; then SUBSRC="$SRC/$ONLY"; SUBDST="/$ONLY"; fi

echo ">> rclone $MODE  ${SUBSRC#"$SRC"/}  ->  $REMOTE:$BUCKET$SUBDST  ${DRY[*]:-}"
"$RCLONE" "$MODE" "$SUBSRC" "$REMOTE:$BUCKET$SUBDST" \
  "${DRY[@]}" \
  --checksum \
  --transfers 16 --checkers 32 \
  --s3-no-check-bucket \
  --progress --stats-one-line
echo ">> готово."
