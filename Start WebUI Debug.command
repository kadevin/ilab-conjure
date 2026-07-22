#!/bin/zsh
set -e
set -o pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

PORT="8787"
URL="http://127.0.0.1:${PORT}/"
HEALTH_URL="${URL}api/health"
WAIT_ATTEMPTS=60
VENV_DIR="${PROJECT_DIR}/.venv"
PYTHON_BIN="${VENV_DIR}/bin/python"
export CODEX_IMAGE_DEBUG_SSE=1

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 was not found. Install Python 3 first."
  read -r "?Press Enter to close..."
  exit 1
fi

if [ ! -x "$PYTHON_BIN" ]; then
  echo "Creating local virtual environment..."
  python3 -m venv "$VENV_DIR"
fi

if ! "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import fastapi
import uvicorn
import multipart
import httpx
PY
then
  echo "Installing WebUI dependencies..."
  "$PYTHON_BIN" -m pip install -r requirements-webui.txt
fi

webui_is_ready() {
  "$PYTHON_BIN" - "$HEALTH_URL" <<'PY' >/dev/null 2>&1
import sys
from urllib.request import urlopen

with urlopen(sys.argv[1], timeout=0.5) as response:
    if response.status != 200:
        raise SystemExit(1)
PY
}

wait_for_webui() {
  local attempt=0
  while [ "$attempt" -lt "$WAIT_ATTEMPTS" ]; do
    if webui_is_ready; then
      return 0
    fi
    attempt=$((attempt + 1))
    sleep 0.5
  done
  return 1
}

echo "Starting iLab CONJURE at ${URL} with SSE debug logging enabled"
echo "Debug logs will be written to output/webui/<task_id>/debug-sse.jsonl"
mkdir -p output
AUTH_SETTINGS_PATH="${PROJECT_DIR}/output/webui-auth-settings.json"
"$PYTHON_BIN" -m codex_image.webui.startup_auth --settings-path "$AUTH_SETTINGS_PATH" >/dev/null
LOG_FILE="${PROJECT_DIR}/output/webui-server.log"
echo "Writing server log to ${LOG_FILE}"
if webui_is_ready; then
  echo "WebUI is already running at ${URL}"
  open "$URL" >/dev/null 2>&1 || true
  exit 0
fi

"$PYTHON_BIN" -m uvicorn codex_image.webui.app:app --host 127.0.0.1 --port 8787 --no-access-log 2>&1 | tee -a "$LOG_FILE" &
SERVER_PID="$!"

if wait_for_webui; then
  open "$URL" >/dev/null 2>&1 || true
else
  echo "WebUI did not become ready within 30 seconds. Check ${LOG_FILE}."
fi

wait "$SERVER_PID"
