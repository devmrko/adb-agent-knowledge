# Oracle AI Agent Memory 실험 / SDK evaluation

공식 `oracleagentmemory==26.8.0`을 기존 서비스와 분리해 검증한다.
운영 MCP의 백엔드를 전환하지 않으며, 기존 `vk_*` 테이블을 SDK가 관리하게 하지 않는다.
SDK dependency lock and virtual environment are independent of the application.

## 실행

저장소 루트에서 앱의 로컬 임베딩 의존성과 모델 캐시를 먼저 준비한다.
이 실험은 기존 한국어 모델을 CPU 별도 프로세스에서 실행하며 모델을 다시 다운로드하지 않는다.
DB 설정 파일에는 USER_NAME, USER_PASSWORD, ORACLE_DSN, WALLET_DIR,
WALLET_PASSWORD가 필요하다. 운영 계정이나 ADMIN을 사용하지 않는다.

```bash
./uvw sync --project experiments/oracle-agent-memory --locked
experiments/oracle-agent-memory/.venv/bin/python \
  experiments/oracle-agent-memory/evaluate.py \
  --env-file /path/to/test.env \
  --expected-user OAM_TEST_DEMO \
  --store-id OAMEVAL_DEMO \
  --embedding-python "$PWD/.venv/bin/python" \
  --hf-home /path/to/cached/huggingface \
  --report .run/oam-evaluation/report.json
```

Use Python 3.12 for this locked experiment. The SDK supports additional versions,
but only macOS Apple Silicon / Python 3.12 was exercised here.
The isolated account needs managed-schema privileges, including CREATE TABLE,
CREATE PROCEDURE, CREATE TRIGGER and CREATE PROPERTY GRAPH. CREATE JOB is needed
for the optional automatic expiry purge job; expiry/purge is not tested here.
The SDK initializes its own prefixed objects using CREATE_IF_NECESSARY, never RECREATE.
Each invocation uses distinct synthetic user/memory IDs and leaves them for inspection.
A failed run may have stored rows already. It does not erase prior tests or resume writes.

## 실제 검증 결과 (2026-11-02)

- SDK import on macOS arm64 / Python 3.12: PASS.
- Separate existing test account, Oracle 23.26.4.1.0: PASS.
- SDK created 8 tables, 5 indexes, 1 SQL Property Graph and 1 trigger under its prefix.
- Local `dragonkue/snowflake-arctic-embed-l-v2.0-ko`, revision
  `55ec6e9358a56d56af759bc8372e970caf8c305f`, 1024 dimensions: PASS.
- Automatic extraction disabled; no generation LLM or OCI GenAI calls.
- Five synthetic Korean facts plus another user's isolation sentinel stored.
- Explicit `supersedes`: old server A becomes INVALID, current server B remains VALID.
- Current-only direct retrieval excludes A; graph expansion still exposes A as historical context.
- Explicit `contradicts`: both incompatible approval claims remain VALID (not resolved truth).
- Three queries found the intended facts in top two. Search including embedding and remote DB
  took 1.123 / 0.397 / 0.405 seconds in this small warm-model run, not a benchmark.
- Other user's sentinel was absent from direct and linked results.
- Existing vk_* object inventory was unchanged. This does not claim a byte-for-byte data audit.

First attempt stored data successfully but the experiment serializer treated
`linked_results` as a flat result list. Actual SDK contract is `(RecordRelation, SearchResult)`
pairs. The adapter was corrected and the run repeated; old test rows were retained.

## 한계와 적용 판단 / limitations

- Top-k also returned unrelated second results: SDK adoption alone does not solve relevance filtering.
- Graph linking was explicit. Automatic LLM extraction quality, Korean conflict resolution,
  large-corpus recall, concurrency, migrations and failure recovery have not been evaluated.
- User scoping here is functional API filtering, not proof of authentication or DDS/VPD isolation.
- `include_invalid_results=False` controls direct matches; linked historical context can still
  contain INVALID records. Preserve status and relation direction when presenting it to agents.
- The sample JSON report summarizes one-hop children; the SDK itself returns a recursive graph tree.
- Existing application query prompting is preserved through `is_query`; production embedding
  adapters need bounded inputs, provider timeouts, batching and process lifecycle management.
- Keep business RDF entities, exact evidence revisions, valid/known time, human clarification
  and audit history in the existing service until explicit mappings and migration tests exist.
- This is not yet a selectable production MCP backend, nor a new web data source.

Recommendation: retain MCP/Kev/UI and evaluate an optional SDK-backed memory adapter.
Keep one canonical writer per record kind; do not silently dual-write both stores.

SDK license metadata: Apache-2.0 OR UPL-1.0. The embedding model and dependencies retain
independent license terms; the application remains MIT.

References:
- https://docs.oracle.com/en/database/oracle/agent-memory/26.8/guide/get-started.html
- https://docs.oracle.com/en/database/oracle/agent-memory/26.8/guide/int-graph-memory.html
- https://docs.oracle.com/en/database/oracle/agent-memory/26.8/guide/api/search.html
