#!/usr/bin/env bash
set -euo pipefail
BOT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
if [[ ! -x "$BOT_DIR/.venv/bin/python" ]]; then
    echo 'Önce ./setup.sh çalıştırın.' >&2
    exit 1
fi
exec "$BOT_DIR/.venv/bin/python" -u "$BOT_DIR/main.py" "$@"
