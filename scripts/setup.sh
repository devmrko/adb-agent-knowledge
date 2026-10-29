#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
./uvw sync --locked --python 3.12 --extra knowledge --extra mcp
./.venv/bin/python scripts/configure_knowledge.py
printf '%s\n' 'After editing .env: ./scripts/run_knowledge.sh --migrate'
