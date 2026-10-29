#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export HF_HOME="${HF_HOME:-$PWD/.cache/huggingface}"
exec ./.venv/bin/python -c 'import uvicorn; from knowledge_app.settings import Settings; s=Settings(); uvicorn.run("knowledge_app.app:create_app", factory=True, host=s.api_host, port=s.api_port)'
