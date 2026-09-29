#!/usr/bin/env bash
set -euo pipefail
BOT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
cd -- "$BOT_DIR"
if command -v uv >/dev/null 2>&1; then
    uv venv --python /usr/bin/python3 --system-site-packages --allow-existing .venv
    uv pip install --python .venv/bin/python -r requirements.txt
else
    /usr/bin/python3 -m venv --system-site-packages .venv
    .venv/bin/python -m pip install -r requirements.txt
fi
./run.sh --doctor
