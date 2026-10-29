#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
# Avoid dependency installation/network access and stdout noise during MCP startup.
exec ./.venv/bin/python -m knowledge_app.mcp_server
