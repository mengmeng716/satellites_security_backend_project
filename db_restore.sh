#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <backup.sql>"
  exit 1
fi

SQL_FILE="$1"
if [[ ! -f "$SQL_FILE" ]]; then
  echo "[db_restore] Error: file not found: $SQL_FILE"
  exit 1
fi

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

DB_NAME="${DB_NAME:-satellite_security_db}"
DB_USER="${DB_USER:-root}"
DB_PASSWORD="${DB_PASSWORD:-${MYSQL_ROOT_PASSWORD:-123456}}"

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD=(docker-compose)
else
  echo "[db_restore] Error: neither 'docker compose' nor 'docker-compose' is available."
  exit 1
fi

echo "[db_restore] Using compose command: ${COMPOSE_CMD[*]}"
echo "[db_restore] Restoring '${SQL_FILE}' into database '${DB_NAME}' ..."

cat "$SQL_FILE" | "${COMPOSE_CMD[@]}" exec -T mysql sh -lc \
  "exec mysql -u\"$DB_USER\" -p\"$DB_PASSWORD\" \"$DB_NAME\""

echo "[db_restore] Done."
