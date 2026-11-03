# v3 production conversion validation / 운영 전환 검증

Date: 2026-11-03 · implementation: `e1a0e91` · version: 0.3.0 preview · schema: vk0016.

운영 API와 임베딩 워커를 함께 v3로 전환했습니다. 기존 준비된 원문 **462개 버전**을
Agent Memory로 이관하고 모든 본문이 기존 원문과 정확히 일치함을 확인했습니다.
이 수치는 전환 대상 버전 수이며 이후 신규 저장을 포함한 현재 총량이 아닙니다.

| 검증 / Check | 관찰 결과 / Observed result |
|---|---|
| 기존 데이터 / Existing sources | 462 versions transferred; all exact source comparisons passed |
| 새 저장 / New MCP save | READY without a manual transfer command; SDK record and V3_INGEST event present |
| 수정 / MCP revision | Same knowledge ID, new revision and SDK record IDs; both bodies readable |
| 이력 / History | Previous revision and events retained; revised version becomes current |
| 전후 API / Before–after API | Sample source hash, two graph relationships and revision history preserved; search returned five results |
| 현재 원문 / Current sources | Zero current READY sources missing an ACTIVE transfer at the deployment check |
| Oracle objects | No invalid VK audit triggers; native RDF and SQL Property Graph objects VALID |
| 공개 웹 / HTTPS web | API-key login, SDK source/IDs, selected-item SQL, separate memory tab, mobile width and logout passed; zero page errors |
| 자동 검사 / Automated checks | 338 Python tests, four JS SQL-help tests, ruff, format, mypy and Foundation wheel validation passed |

Production MCP write/revision checks ran through the normal API and worker. The conversion preserves
existing knowledge/revision/owner/graph IDs. Each immutable source version has a separate SDK record ID;
`vk_source_transfer.sdk_record_id` stores the mapping. Clients continue to use knowledge and revision IDs.
The web source/version panel and content response expose the mapped SDK store and record IDs.

Existing relational version/history, audit, attachment and graph data remain part of the design.
Retained source/vector copies support rollback and relational compatibility; they were not deleted.
Agent experience memories remain in their separate store. These are small functional checks, not a
large-corpus relevance/latency benchmark or a process-kill recovery test. User-principle editor saving was
not retested by the knowledge web check and retains its separately documented validation limits.

[구성·ID·복구 / Architecture, IDs and rollback](../guides/v3-primary-store.md) ·
[English guide](../guides/v3-primary-store.en.md) ·
[Isolated Oracle validation](v3-primary-validation.json)
