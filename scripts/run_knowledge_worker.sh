#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export HF_HOME="${HF_HOME:-$PWD/.cache/huggingface}"
exec ./.venv/bin/python -m knowledge_app.worker "$@"
