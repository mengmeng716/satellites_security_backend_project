#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

DB_NAME="${DB_NAME:-satellite_security_db}"
DB_USER="${DB_USER:-root}"
DB_PASSWORD="${DB_PASSWORD:-${MYSQL_ROOT_PASSWORD:-123456}}"
OUT_FILE="${1:-satsec_${DB_NAME}_$(date +%Y%m%d_%H%M%S).sql}"

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD=(docker-compose)
else
  COMPOSE_CMD=()
fi

echo "[db_backup] Backing up database '${DB_NAME}' to '${OUT_FILE}' ..."

if [[ ${#COMPOSE_CMD[@]} -gt 0 ]]; then
  echo "[db_backup] Using compose command: ${COMPOSE_CMD[*]}"
  "${COMPOSE_CMD[@]}" exec -T mysql sh -lc \
    "exec mysqldump -u\"$DB_USER\" -p\"$DB_PASSWORD\" --databases \"$DB_NAME\" --single-transaction --quick --set-gtid-purged=OFF" \
    > "$OUT_FILE"
else
  echo "[db_backup] Compose not found, fallback to container name: satsec-mysql"
  docker exec -i satsec-mysql sh -lc \
    "exec mysqldump -u\"$DB_USER\" -p\"$DB_PASSWORD\" --databases \"$DB_NAME\" --single-transaction --quick --set-gtid-purged=OFF" \
    > "$OUT_FILE"
fi

echo "[db_backup] Done: $OUT_FILE"
