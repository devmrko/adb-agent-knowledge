# 요약 계층, 여러 인덱스와 Kev 탐색 경로

2026-10-16 사용자 구현 승인. 요약→상세→원본을 구분하고 Oracle에 요약/상세를 저장한다. 큰 원본의 외부 저장과 Obsidian 편집 연동은 이번에 외부 서비스 설정 없이 활성화하지 않는다. 기존 원본 바이트와 출처 참조를 보존한다.

요약은 source revision에 귀속한다. 생성/수정 API와 MCP가 summary를 받으며 HUMAN/AGENT/API 작성 출처를 기록한다. 미제공시 worker가 제한된 문장을 추출한 EXTRACTIVE 요약을 저장한다. 추출 요약은 생성형 요약이나 전체 내용의 완전한 대체로 주장하지 않는다. 기존 revision은 읽을 때 같은 추출 방식으로 미리보기를 제공하고 명시적 backfill로 파생 요약만 채울 수 있다. 새 본문에 옛 요약을 상속하지 않는다. 요약은 원문 근거로 사용하지 않는다. 기존 원문 청크 검색은 유지하며 요약만 검색하는 좁은 관문을 만들지 않는다.

인덱스는 owner/scope/key로 식별하는 별도 문서이다. title, summary(수록 범위 설명), body(편집 가능한 안내), version을 갖는다. 인덱스 수정에는 expected_version, 이력을 남긴다. 구성원은 knowledge_id 참조와 section/position/note이며 본문을 복사하지 않는다. 동일 지식을 여러 인덱스에 연결할 수 있다. 구성원 페이지는 활성 revision의 요약을 동적으로 읽고 폐기·미색인 항목을 제외한다. 모든 조회/연결에서 owner와 scope를 검증한다. global 인덱스는 소유자의 여러 프로젝트를 연결할 수 있고 범위 필터는 구성원에도 적용한다. 자동 삭제/정리 API는 제공하지 않는다.

카탈로그와 구성원은 명시적 페이지 탐색을 제공하며 벡터 top-k에 의존하지 않는다. 검색어는 카탈로그에서 선택적 제목/설명 필터다. Kev는 제한된 카탈로그 설명과 요청만 보고 direct/index/both/skip/agent_review, graph 필요성을 판단한다. 인덱스 적합도도 동일 호출에서 평가한다. 페이지가 잘렸음을 반환하고 명시적 index_ids로 직접 읽을 수 있다. 모델 장애/애매한 판단은 양쪽 경로로 보완하며 scores는 확률 보증이 아니다. 첫 경로의 빈 결과는 다른 경로로 보완한다. 저장 계획은 가치 판단→직접 검색으로 중복 후보 확인→인덱스 후보/기존 보완 필요성 판단이다. Kev는 기존 내용을 자동으로 덮어쓰거나 개체 동일성을 결정하지 않는다. 에이전트가 정확한 원문과 이력을 확인해 save/revise, READY 후 verified membership을 연결한다. 인덱스 새 생성은 명시적 설명/키로 에이전트가 수행한다. 기존 membership은 본문 갱신 후 자동으로 최신 요약을 가리킨다.

API: /knowledge/recall, /knowledge/prepare-save, /indexes GET/POST, /indexes/{id} GET/PUT, /indexes/{id}/entries GET/PUT, /indexes/{id}/history GET, /knowledge/{id}/revisions/{revision}/summary GET. MCP 동일 기능과 저장 summary 인자. 웹은 요약→코드 상세와 인덱스 카탈로그/구성원 페이지 제공. 웹은 노트 선택 시 상세도 함께 읽으며 수정 기능을 보존한다. MCP 탐색은 요약부터 반환한다.

검증: 요약-본문 버전 일치, HUMAN 요약 및 extractive 표시, 중복 재요청 호환, 다중 인덱스/페이지/최신 revision/폐기 제외, owner/scope 경계, 충돌/이력, Kev 경로·장애·입력 비밀 차단, 빈 결과 보완, 원문 근거 유지, 실제 Oracle/MCP/UI. 모델 품질 개선 여부는 별도 실제 질의 평가가 필요하다.


후속 확정: 원본 위치와 연결 인덱스/프로젝트 양쪽을 references로 노출한다. VK_NAV 구조 RDF는 member_of/revision_of/in_scope/has_source 및 머신·원본 연결을 보관한다. manifest와 원시 native RDF를 대조하여 저장 여부를 확인한다. 업무 사실의 VK_SHARED 증거와 분리한다. 과거 근거는 exact revision, 인덱스는 현재 구성원이다. EPISODE에 무엇/이유/방법/관찰 결과/근거를 기록하되 시도와 검증 성공을 구분한다. 최신 원문의 파생 데이터 backfill은 원문 이력을 변경하지 않는다.

상세 사용법·현재 방식과 최신 접근의 비교·미완성 범위는 [인덱스 탐색 가이드](../../guides/index-navigation.md)에 기록한다.
