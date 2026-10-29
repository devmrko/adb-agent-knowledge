# External components

The root MIT license covers this project's original code. It does not relicense external software,
models, data or services. No model weights, Wallet or database credentials are distributed here.

- Oracle Database / Autonomous Database: provision your own service and follow Oracle terms.
- Kev: separately installed from https://github.com/jaredpalmer/kev ; retain its license and the
  selected model/base model conditions. The repository pins a Kev source commit in setup_kev.sh.
- Embeddings: https://huggingface.co/dragonkue/snowflake-arctic-embed-l-v2.0-ko ; check the pinned
  model card and upstream model conditions before redistribution.
- Gemma: downloaded separately; Google Gemma terms apply, not this repository's MIT license.
- Ollama and Python dependencies retain their respective licenses; exact dependency versions are
  recorded in uv.lock. This is an inventory guide, not a completed dependency license audit.

Maintainer-only access helpers and deployment addresses are excluded from this distribution.
Supply your own endpoints and credentials using docs/guides/portable-setup.md.

Installed Python dependency declarations: [inventory](docs/reference/dependency-licenses.md).
