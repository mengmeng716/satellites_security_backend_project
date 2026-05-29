#!/usr/bin/env bash
set -euo pipefail

DB_HOST="${DB_HOST:-mysql}"
DB_PORT="${DB_PORT:-3306}"

echo "[entrypoint] Waiting for MySQL at ${DB_HOST}:${DB_PORT} ..."
python - <<'PY'
import os
import socket
import time

host = os.getenv("DB_HOST", "mysql")
port = int(os.getenv("DB_PORT", "3306"))
max_wait_sec = int(os.getenv("DB_WAIT_TIMEOUT", "120"))
start = time.time()

while True:
    try:
        with socket.create_connection((host, port), timeout=3):
            print(f"[entrypoint] MySQL is reachable at {host}:{port}")
            break
    except OSError:
        if time.time() - start > max_wait_sec:
            raise SystemExit(f"[entrypoint] Timeout waiting for MySQL at {host}:{port}")
        time.sleep(2)
PY

echo "[entrypoint] Running migrations..."
python manage.py migrate --noinput

echo "[entrypoint] Collecting static files..."
python manage.py collectstatic --noinput

# 如果 docker-compose 传递了自定义的 command（比如启 Celery），则执行传递的 command
if [ $# -gt 0 ]; then
    echo "[entrypoint] Executing custom command: $*"
    exec "$@"
fi

# 否则默认启动 Gunicorn
echo "[entrypoint] Starting gunicorn..."
exec gunicorn satellites_security_backend.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-2}" \
  --threads "${GUNICORN_THREADS:-4}" \
  --timeout "${GUNICORN_TIMEOUT:-300}"
