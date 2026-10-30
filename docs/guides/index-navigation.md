# 요약, 인덱스와 근거를 따라 지식 찾기

지식은 요약 → 상세 → 원본으로 읽습니다. 요약과 상세는 Oracle에 함께 저장하고 원본 바이트 및 출처 위치를 보존합니다. 큰 파일의 외부 저장소 이전이나 Obsidian 연동은 아직 활성화하지 않았습니다.

## 설치와 업그레이드

기존 빠른 시작 설정을 완료한 뒤 다음을 실행합니다. RDF 기능을 켠 Oracle에서는 기존 network/shared graph 설치에 이어 VK_NAV 모델도 준비해야 합니다. 먼저 API·worker의 쓰기를 중지하고, 업데이트 후 모두 같은 코드 버전으로 시작합니다.

```sh
./uvw run alembic upgrade head
./uvw run python -m scripts.prepare_knowledge_rdf
# 성공 후 .env에 WORKFLOW_RDF_ENABLED=true 설정
./scripts/run_knowledge.sh
# 별도 터미널: 현재 API 사용자의 기존 활성 지식 파생 데이터 보완
./uvw run python -m scripts.backfill_navigation
```

스키마 vk0007은 summary_kind, vk_index, vk_index_entry, vk_index_change, vk_nav_snapshot을 추가합니다. backfill은 원문 버전을 만들거나 기존 작성 요약을 덮어쓰지 않습니다. RDF 비활성/SQLite에서는 relational_metadata로 명시하며 Oracle RDF 저장이라고 표시하지 않습니다.

## 화면과 API

`/knowledge` 왼쪽의 ‘인덱스로 찾기’에서 카탈로그와 구성원을 페이지 단위로 봅니다. 일반 카테고리·검색은 유지됩니다. 오른쪽은 요약 / 상세 / 참조 위치 / 연결된 지식입니다. 상세는 줄 번호·코드 서식·자동 줄바꿈을 유지하고, 요약과 본문을 수정하면 HUMAN 출처를 남깁니다. 화면은 선택한 노트의 상세도 함께 로드하지만 MCP 탐색은 요약부터 반환합니다.

- `POST /api/v1/knowledge/recall`: Kev가 직접 검색/인덱스/양쪽을 선택합니다.
- `POST /api/v1/knowledge/prepare-save`: 저장 가치와 중복·보완·인덱스 후보를 조회합니다. **저장하지 않습니다.**
- `/api/v1/indexes`: 카탈로그 GET, 생성 POST. `/{id}` GET/PUT, `/{id}/entries` GET/PUT, `/{id}/history` GET.
- `/api/v1/indexes/unfiled`: 어느 인덱스에도 속하지 않은 활성 지식.
- `/api/v1/knowledge/{id}/references?revision_id=...`: 원본 위치, 머신, 원문 버전, 현재 인덱스 역참조와 공통 관계 조회 seed.
- `/api/v1/knowledge/{id}/revisions/{revision}/summary` 및 `/original`: 요약/인증된 원본 다운로드.
- `POST /api/v1/knowledge/{id}/refresh-derived`: 현재 원문의 누락 요약과 출처 RDF 보완.

MCP에는 knowledge_recall, knowledge_prepare_save, knowledge_index_list/get/create/update/link/entries/history, knowledge_get_summary, knowledge_references가 대응합니다. 실행 예:

```json
{"text":"지난번 Oracle 접속을 어떻게 해결했지?","scopes":["global","project:my-project"],"mode":"auto","top_k":5}
```

모델 경로를 강제하지 않고 `mode=direct/index/both`, 명시적 index_ids, catalog_offset으로 직접 탐색할 수도 있습니다. 카탈로그 20개, 선택 인덱스 최대 3개, 각 8개 요약, 요약 본문 총 6000자까지 미리 봅니다. 카탈로그 설명/메타데이터는 이 요약 예산과 별도입니다. 반환된 페이지와 next_offset을 따라가야 전체 구성을 확인할 수 있습니다. 모델 실패/모호함에는 양쪽 경로, 빈 결과에는 다른 경로로 보완합니다. 비어 있지 않아도 관련 없는 결과일 수 있으므로 에이전트가 실제 내용을 판단해야 합니다.

## 버전과 RDF

하나의 지식이 프로젝트·주제·업무 인덱스 여러 개에 연결됩니다. 인덱스는 stable knowledge_id를 참조하여 본문 보완 시 최신 요약을 표시합니다. 메타데이터와 구성원 배치 변경은 버전·변경 이력을 남깁니다. 인덱스 전체의 과거 시점 재구성 및 구성원 삭제 API는 아직 제공하지 않습니다.

구조 연결은 VK_NAV에 member_of, revision_of, in_scope, has_source, on_machine, has_original, written_on 등으로 저장합니다. 연결의 실제 존재를 manifest와 대조합니다. 경로 문자열은 출처 메타데이터에서 읽으며, RDF의 source 노드는 안정적인 식별자를 사용합니다. 경로가 등록되어도 접근 가능성을 보장하지 않습니다.

업무 의존·순서 같은 사실 관계는 기존 VK_SHARED와 정확한 evidence revision을 사용합니다. 구조 연결은 업무 관계를 증명하지 않습니다. 시점 필터는 공통 관계에 적용하며 현재 인덱스 멤버십을 과거 멤버십으로 해석하지 않습니다. 모든 API는 사용자 소유권을 검사합니다. global도 개인 소유 범위입니다.

## 작업을 잊었을 때

기존 EPISODE 유형에 무엇을 했는지 / 이유 / 수행 방법 / 관찰한 결과 / 근거 위치와 버전을 기록합니다. 단순 시도와 검증된 성공을 구분합니다. 같은 사건의 확인된 보완은 기존 원문과 이력을 읽고 수정하며, 다른 사건은 분리합니다. 원문·자료를 통째로 자동 보관하지 않습니다. 당시 근거는 정확한 revision을 참조하므로 이후 본문 수정과 혼동하지 않습니다.

요약을 제공하면 HUMAN/AGENT/API 출처를 기록합니다. 미제공 시 EXTRACTIVE 요약은 일부 문장을 추출한 미리보기입니다. 전체 의미를 충실하게 생성한 요약이라고 보장하지 않으며, 요약 자체를 사실 근거로 인용하지 않습니다. 원문 청크 검색은 계속 사용합니다.

## 현재 접근의 장점과 남은 과제

이 구조는 경량 참조에서 필요한 상세를 읽는 [just-in-time retrieval](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)과 방향이 같습니다. 다만 사람이 관리하는 인덱스는 [RAPTOR](https://arxiv.org/abs/2401.18059)의 자동 다층 요약 트리와 같지 않습니다. RDF 연결만으로 [GraphRAG](https://microsoft.github.io/graphrag/)의 커뮤니티 요약·전역 질문 처리를 구현한 것도 아닙니다.

1. 실제 사용자 질의로 직접 검색/인덱스/양쪽 경로의 정답 포함률, 누락, 불필요 검색, 지연을 비교해야 합니다. 현재 Kev 임계값은 잠정값입니다. [평가 가이드](search-evaluation.md)의 초기 합성 세트만으로 품질 향상을 주장할 수 없습니다.
2. 미분류 항목과 최신 revision 연결은 제공하지만 인덱스 범위/설명 노후화, 잘못된 분류, 고아 원본의 자동 감시는 남아 있습니다.
3. 키워드는 LIKE 기반이며 한국어 전문 검색/BM25, 문서 맥락을 붙인 청크 임베딩은 아직 없습니다. [Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval)의 발표 수치를 이 서비스의 개선율로 적용할 수 없습니다.
4. 리랭커는 구현되어 있으나 소규모 평가에서 임계값에 따른 정답 누락이 있어 기본 비활성입니다. [실측과 재평가 절차](search-reranking.md)를 따라야 합니다.
5. 관계 시점은 지원하지만 여러 단계의 자동 탐색은 제한된 프리뷰와 에이전트 판단입니다. 완전한 자동 추론/전역 그래프 요약 엔진은 아닙니다.


## 검증 기록 (2026-10-16)

정적 검사(Ruff, mypy), 전체 130개 테스트, 브라우저의 요약/본문 편집·HUMAN 표시·페이지·모바일 검증을 통과했습니다. 실제 Oracle에서 인덱스/이력/접근 경계/VK_NAV 저장 및 격리한 worker의 파생 요약·RDF 생성을 확인했습니다. 실제 MCP에서 Kev가 both 경로를 선택했고 해당 전체 요청은 약 8.6초였습니다. 단일 표본이므로 대표 지연이나 개선율은 아닙니다.

기존 활성 지식 65건의 파생 데이터를 보완했습니다. 배포 후 새 revision 한 건에서 READY지만 구조 RDF가 없는 상태가 관찰되어 refresh-derived로 복구했습니다. 원인은 확정하지 않았습니다. 여러 머신에서 같은 DB의 작업을 처리한다면 모든 worker를 같은 버전으로 업데이트해야 합니다. 기존 worker도 READY를 기록할 수 있으므로 작업 상태만으로 새 파생 데이터 존재를 보장하지 않습니다. references의 rdf.status/storage로 별도 확인합니다.
