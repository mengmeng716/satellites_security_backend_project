#!/usr/bin/env bash
set -euo pipefail

# Long-running pipeline E2E validation helper.
# Usage:
#   ./scripts/long_pipeline_e2e_check.sh <task_id> [--restart]
# Example:
#   ./scripts/long_pipeline_e2e_check.sh 20260605_103000_123_abcd1234 --restart

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <task_id> [--restart]"
  exit 1
fi

TASK_ID="$1"
DO_RESTART="${2:-}"
BASE_URL="${SATSEC_BASE_URL:-http://127.0.0.1:8000}"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

STATUS_URL="$BASE_URL/api/security/run-pipeline/status/$TASK_ID/"
STREAM_URL="$BASE_URL/api/security/run-pipeline/stream/$TASK_ID/"

compose_cmd() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    echo "docker compose"
    return 0
  fi
  if command -v docker-compose >/dev/null 2>&1; then
    echo "docker-compose"
    return 0
  fi
  return 1
}

print_header() {
  echo
  echo "============================================================"
  echo "$1"
  echo "============================================================"
}

check_status_once() {
  print_header "[1] Query task status"
  echo "GET $STATUS_URL"
  curl -fsS "$STATUS_URL" | sed -n '1,200p'
}

watch_sse_short() {
  print_header "[2] Read SSE for 20 seconds"
  echo "GET $STREAM_URL"
  timeout 20s curl -NsS "$STREAM_URL" || true
}

restart_services_if_requested() {
  if [[ "$DO_RESTART" != "--restart" ]]; then
    return 0
  fi

  print_header "[3] Restart backend/frontend/celery services"
  local cmd
  if ! cmd="$(compose_cmd)"; then
    echo "No docker compose command found. Skip restart step."
    return 0
  fi

  echo "Using compose command: $cmd"
  (
    cd "$PROJECT_DIR"
    $cmd up -d backend celery_worker frontend
    $cmd ps
  )
}

poll_status_loop() {
  print_header "[4] Poll status 12 times (5s interval)"
  for i in $(seq 1 12); do
    echo "[$i/12] $(date '+%F %T')"
    if ! curl -fsS "$STATUS_URL"; then
      echo "status request failed"
    fi
    echo
    sleep 5
  done
}

manual_network_test_hint() {
  print_header "[5] Manual network reconnect test"
  cat <<'EOF'
Please run this manual check in browser DevTools:
1. Open Network tab, set Offline for 20-30 seconds.
2. Restore Online.
3. Verify frontend reconnects SSE and task status continues to advance.
4. Verify result panels still open when pipeline reaches completed/failed.
EOF
}

check_status_once
watch_sse_short
restart_services_if_requested
poll_status_loop
manual_network_test_hint

print_header "DONE"
echo "Task: $TASK_ID"
echo "Status URL: $STATUS_URL"
