#!/usr/bin/env bash
# Run Streamlit with the project venv so parsers (fitz, pdfplumber, …) resolve correctly.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "No .venv found. Create it and install deps first:"
  echo "  python3 -m venv .venv"
  echo "  .venv/bin/python -m pip install -r requirements.txt"
  exit 1
fi
exec "$ROOT/.venv/bin/python" -m streamlit run "$ROOT/app.py" "$@"
