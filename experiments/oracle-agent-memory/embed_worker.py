"""JSON-lines bridge to the application's existing, pinned local Korean embedder."""

import argparse
import json
import os
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--hf-home", required=True)
args = parser.parse_args()
os.environ["HF_HOME"] = str(Path(args.hf_home).expanduser().resolve())
os.environ["HF_HUB_OFFLINE"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from knowledge_app.embedding import SentenceEmbedder  # noqa: E402
from knowledge_app.settings import Settings  # noqa: E402

embedder = SentenceEmbedder(
    Settings(
        _env_file=None,
        embedding_provider="local",
        embedding_device="cpu",
        embedding_revision="55ec6e9358a56d56af759bc8372e970caf8c305f",
    )
)
for line in sys.stdin:
    request = json.loads(line)
    vectors = embedder.encode(request["texts"], query=request["is_query"])
    print(json.dumps(vectors), flush=True)
