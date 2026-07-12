#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

VENV_DIR="${VENV_DIR:-.venv}"
PYTHON_BIN="${PYTHON_BIN:-}"

find_python() {
  if [[ -n "${PYTHON_BIN}" ]]; then
    echo "${PYTHON_BIN}"
    return
  fi

  if command -v python3.14 >/dev/null 2>&1; then
    echo "python3.14"
    return
  fi

  if command -v python3 >/dev/null 2>&1; then
    python3 - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 14) else 1)
PY
    echo "python3"
    return
  fi

  echo "Python 3.14 was not found. Install Python 3.14 or set PYTHON_BIN." >&2
  exit 1
}

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  PYTHON_CREATE="$(find_python)"
  echo "Creating virtual environment with ${PYTHON_CREATE}..."
  "${PYTHON_CREATE}" -m venv "${VENV_DIR}"
fi

PYTHON="${VENV_DIR}/bin/python"

if [[ "${ACA_SKIP_INSTALL:-0}" != "1" ]]; then
  echo "Installing Python dependencies..."
  "${PYTHON}" -m pip install -r requirements.txt
fi

if [[ ! -f ".env" ]]; then
  echo "Creating .env from .env.template..."
  cp .env.template .env
fi

set -a
# shellcheck disable=SC1091
. ./.env
set +a

build_frontend() {
  if [[ "${ACA_SKIP_FRONTEND_BUILD:-0}" == "1" ]]; then
    echo "Skipping frontend build because ACA_SKIP_FRONTEND_BUILD=1."
    return
  fi

  if ! command -v npm >/dev/null 2>&1; then
    echo "npm was not found. Install Node.js/npm or set ACA_SKIP_FRONTEND_BUILD=1 if server/static is already built." >&2
    exit 1
  fi

  pushd web >/dev/null
  if [[ "${ACA_SKIP_INSTALL:-0}" != "1" ]]; then
    echo "Installing frontend dependencies..."
    if [[ -f package-lock.json ]]; then
      npm ci
    else
      npm install
    fi
  fi

  echo "Building React frontend..."
  npm run build
  popd >/dev/null
}

build_frontend

ACA_HOST="${ACA_HOST:-127.0.0.1}"
ACA_PORT="${ACA_PORT:-9502}"

if [[ "${GOOGLE_API_KEY:-}" == "YOUR_GOOGLE_API_KEY" || -z "${GOOGLE_API_KEY:-}" ]]; then
  echo "Warning: GOOGLE_API_KEY is not configured. The UI can start, but chat requests may fail." >&2
fi

echo "Starting Open Creative Agent at http://${ACA_HOST}:${ACA_PORT}"
exec "${PYTHON}" -m uvicorn server.main:app --host "${ACA_HOST}" --port "${ACA_PORT}"
