#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
exec ./.venv/bin/python scripts/run_configured_knowledge_mcp.py
