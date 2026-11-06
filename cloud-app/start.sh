#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ -x .venv/bin/python ]]; then
  sticker_python=.venv/bin/python
else
  sticker_python=python3
fi
exec "$sticker_python" -m uvicorn app.main:app --host "${STICKER_HOST:-127.0.0.1}" --port "${STICKER_PORT:-8000}" --workers 1 --no-access-log
