# Architecture and model execution

[English home](../../README.en.md) · [한국어 모델 문서](../guides/local-models.md)

This guide describes the application code, not a promise that every model is installed on a particular
server. A configured model name does not identify the machine where inference takes place.

## Execution boundaries

| Function | Process | Model or database work |
|---|---|---|
| Tool interface | MCP adapter | Makes authenticated Knowledge API calls; uses Kev routing where applicable |
| Query embedding | Knowledge API | Local Sentence Transformer or remote embeddings API |
| Source embedding | Ingestion worker | Chunking and document vectors using the same configured profile |
| Vector retrieval | Oracle ADB | Vector-distance SQL, scoped candidates, source and revision storage |
| Decision scoring | Separate Kev service | `/v1/systemone` scores for retrieval, capture and navigation |
| Agent-mode extraction | Codex/Claude | Reads exact source evidence and submits entity/relationship operations |
| Service-mode extraction | Optional graph worker | Calls `CompletionProvider`, currently with an OpenAI-compatible HTTP implementation |

The application combines vector candidates with literal substring keyword candidates. It does not currently
use Oracle Text/BM25. Application code combines candidates and applies ranking/visibility rules; not every
part of retrieval ranking runs inside the database.

### Local embeddings

```dotenv
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=dragonkue/snowflake-arctic-embed-l-v2.0-ko
EMBEDDING_DEVICE=cpu
```

Keep `EMBEDDING_REVISION` at the pinned commit supplied in `.env.example`. Local loading rejects an
unpinned revision. The model is loaded lazily by SentenceTransformers with `trust_remote_code=False`.

“Local” means **the machine running each API/worker process**. The MCP adapter itself does not run this
embedding model. If the API and worker run on a server and the agent runs on a laptop, embedding compute
is on the server. If API and worker run on different hosts, each local-provider process needs the model
and matching configuration. The processes have separate model instances and memory consumption.

Default launchers set `HF_HOME` to the checkout's `.cache/huggingface` unless already configured. Direct
Python execution follows the environment and Hugging Face defaults. A missing cached model is downloaded
when first needed. CPU is the default; `mps`/`cuda` require compatible hardware and PyTorch. CUDA local
loading uses bf16. No combined minimum memory requirement is guaranteed for all optional models.

The [embedding model card](https://huggingface.co/dragonkue/snowflake-arctic-embed-l-v2.0-ko) identifies a
Korean-tuned Snowflake Sentence Transformer supporting Korean/English, 1024 dimensions, cosine similarity,
and a query prompt. The application uses 384-token chunks with 48-token overlap by default, normalizes
vectors, and selects `prompt_name="query"` for searches. Model maximum context is not application chunk size.

### Remote embeddings

```dotenv
EMBEDDING_PROVIDER=openai
EMBEDDING_URL=https://models.example.com/v1
EMBEDDING_MODEL=your-1024-dimensional-model
EMBEDDING_REVISION=immutable-model-version
EMBEDDING_API_KEY=your_embedding_key
EMBEDDING_QUERY_PREFIX=
```

The endpoint and values are placeholders. API/worker send document chunks or queries to `/embeddings`;
the remote provider performs inference. No embedding weights are loaded by the local adapter. The provider
name denotes wire compatibility, not a requirement to buy an OpenAI service. Chat completions endpoints
cannot substitute for embeddings. HTTP is accepted only on loopback; remote deployments require HTTPS.
Environment proxies and redirects are disabled by the adapter.

Remote chunking is character-based: default 512 characters and 64 overlap. Configure the query prefix to
match the provider, without applying it twice. API/worker must agree on provider, model, immutable revision,
dimensions, and preprocessing. Changing an endpoint requires operational assurance that the actual model
and preprocessing remain the same; a declared revision string alone cannot prove that.

Current database vectors are fixed at 1024 dimensions. Local and remote profiles are not interchangeable
just because they name the same model. Profile mismatches are rejected; automatic re-embedding/profile
migration is not implemented. Plan migration or validate in a separate schema before changing profiles.

### Oracle's role

Oracle stores original content/revisions and vectors. The API sends an already-computed query vector;
Oracle evaluates vector distance against stored vectors. **This application does not load the above
embedding model into Oracle or invoke database-side embedding inference.** This is an implementation
boundary, not a claim that Oracle has no database-side AI capabilities.

## Kev remains in v2

The default local model is `jaredpalmer/kev-4b`. Its [model card](https://huggingface.co/jaredpalmer/kev-4b)
describes a Qwen3.5-4B-Base adapter and decision head, with English as its stated language. The application
uses typed scores rather than generated chat answers. Korean prompts do not establish validated Korean
accuracy. Thresholds are provisional operational choices, not guarantees.

```sh
./scripts/setup_kev.sh
./scripts/run_knowledge.sh --kev
```

Setup pins a Kev source commit and prepares a separate Python 3.13 environment. Model weights download
separately; this is not a fully pinned offline model bundle. `KEV_REPO_DIR` locates the checkout,
`KEV_RUN` selects local model loading, `KEV_URL` locates the server, and `KEV_MODEL=kev-latest` is an API alias.
For remote Kev, configure HTTPS `KEV_URL`, `KEV_ALLOW_REMOTE=true`, and any required `KEV_API_KEY`;
do not also start local Kev with `--kev`.

Lookup defaults to a 0.2 threshold; capture defaults to 0.7, with an agent-review interval. Explicit requests,
storage opt-outs, and sensitive content rules override scores. Failures return `agent_review` rather than
pretending that Kev is working. Only short relevant text should be sent, not secrets or entire conversations.
These decisions are invoked by tool/skill flow, not a universal mandatory hook on every user message.

## Generative relationship extraction

Default `GRAPH_EXTRACTION_MODE=agent` uses the calling Codex/Claude model. There is no separate generation
provider invocation in the service and the launcher does not start the graph extraction worker. Agent usage
still costs tokens; web-only ingestion needs an agent follow-up to get relationships extracted.

Optional `GRAPH_EXTRACTION_MODE=service` plus `GRAPH_AUTO_ENABLED=true` retains worker-based extraction.
The worker calls a separate model using `CompletionProvider`; the shipped implementation is OpenAI-compatible
HTTP. Ollama/vLLM/OpenRouter are connection choices, not models bundled into this repository. SDK and direct
in-process implementations are extension points; concrete OCI SDK/local loaders are not shipped.

The local example `adb-agent-knowledge-gemma4:e2b` is an Ollama model alias defined through
[Gemma4.Modelfile](../../config/Gemma4.Modelfile), not a model installed by naming it in `.env`.
The public example is not a declaration of what model a particular hosted service runs.

## Sources of truth and limits

Execution paths: [embedding.py](../../knowledge_app/embedding.py),
[service.py](../../knowledge_app/service.py), [repository.py](../../knowledge_app/repository.py),
[mcp_server.py](../../knowledge_app/mcp_server.py), [launcher.py](../../knowledge_app/launcher.py).
Configuration: [settings.py](../../knowledge_app/settings.py), [.env.example](../../.env.example).

This documentation was checked against source on 2026-10-30 and the linked model cards. That check does
not establish actual deployment state, end-to-end model quality, or fresh-ADB compatibility. Models and
runtimes retain their own licenses; consult [THIRD_PARTY.md](../../THIRD_PARTY.md).
