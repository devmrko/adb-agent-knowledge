# 검증 결과 — 2026-10-15

## 이식성·스킬 배포 검증
- 78개 테스트: 기존 .env 보존/신규 토큰 생성, 스킬 복사 및 덮어쓰기 방지,
  별도 SQLite DB에서 migration→API/worker 시작→Ctrl-C 종료까지 확인.
- ruff/mypy, 공통 SKILL.md 형식 검증, sdist/wheel 빌드와 기존 소비 앱 6개 조합 통과.
- 개인 Wallet 경로/DSN 기본값 제거. 기존 개발 머신의 값은 무시되는 .env에만 유지.
- 새 머신의 Oracle 접속과 Kev 설치는 각 머신의 자격증명·네트워크·하드웨어에 의존한다.
  이번에는 별도 머신에 접속해 실행하지 않았으며 기존 Oracle 검증 이력은 아래와 같다.

## 메모리 확장 검증 (vk0002)
- 코드 검사/포맷 검사, mypy 27개 파일, 자동 테스트 59개 통과.
- 기존 데이터가 있는 SQLite vk0001→vk0002 마이그레이션: 원문/활성 revision/FK 보존 확인.
- 실제 Autonomous DB vk0002 적용 및 API/worker 재시작 완료.
- 실제 stdio MCP 11개 도구: 범위/종류 저장·검색, 중복 요청, 수정 색인, 과거 원문,
  컨텍스트 카드, 폐기/복원/이력 통과. 검증 항목은 최종 RETIRED 처리.
- 재시작 API health=UP, 기존 ACTIVE 지식 4건 유지.
- 제공된 65,394,671바이트 PPTX를 로컬 추출: 슬라이드 41개, 노트 섹션 11개, 23,539문자.
  이 파일은 DB에 등록하지 않았다. 큰 미디어를 읽지 않고 슬라이드/노트 XML만 추출한다.
- 사용자 간 격리, 오래된 수정 요청 거절, 늦게 완료한 revision의 되돌림 방지,
  폐기 중 worker 완료 시 비활성 상태 유지, 무관 결과 제외를 자동 테스트로 검증.
- 관련성 기준 0.28은 잠정값. 한국어 대규모 검색 품질/동시 부하 성능을 보장하는 수치가 아니다.
- 생성형 요약·자동 기억 추출/병합·OCR·Graph는 미구현. 아래는 최초 버전 검증 이력이다.


## 실제 환경
- Apple Silicon arm64, 프로젝트 전용 Python 3.12.15.
- Autonomous AI Database 23.26.4.1.0: Wallet 연결, SELECT 및 VECTOR_DISTANCE 성공.
- vk_alembic_version=vk0001. VK_ITEM / VK_REVISION / VK_JOB / VK_CHUNK 생성 완료.
- 모델 dragonkue/snowflake-arctic-embed-l-v2.0-ko.
- 고정 revision: 55ec6e9358a56d56af759bc8372e970caf8c305f.
- CPU 실제 추론: 1024차원. 모델 캐시 .cache/huggingface.

## 자동 검증
- ruff check / format check 통과.
- mypy: 26개 소스 파일 통과.
- pytest: 43개 통과(기존 Foundation 회귀 포함).
- wheel/sdist 빌드 통과.
- 설치된 wheel의 소비 앱 6개 조합(SQLite/Oracle 설정 × session/token/mixed) 검증 통과.
  해당 wheel 검증은 SQLite 런타임이며, 아래 별도 검증이 실제 Oracle 결과다.

## 실제 HTTP → Oracle → 모델 통합
- 텍스트 등록 202 → DB QUEUED → 독립 worker → CPU 임베딩 → READY.
- 한국어 질문의 표현을 바꿔 Oracle cosine/키워드 결합 검색 후 원문 조회 성공.
- PDF 파일 업로드 → 텍스트/페이지 추출 → 임베딩 → 검색/원문 조회 성공.
- example.com HTTPS URL → 검증 IP에 TLS 연결 → HTML 텍스트 추출 → READY/원문 조회 성공.
- Swagger HTTPBearer 보안 스키마 확인.
- 개발 검증 데이터 3건을 developer 소유로 남김:
  - d6f5358b-9e64-4fbc-987a-cb901cc3b9ae: 한국어 텍스트
  - 5f44030a-5b59-4acb-8c6f-c414bc07a201: PDF
  - d4f61afd-cd24-4260-ade4-59fde704c042: URL

## 검증 구분과 남은 범위
- 사용자 간 격리/실패 재시도/프로필 격리/복합 FK는 자동 테스트로 검증.
- A10 CUDA, MPS, 운영 JWT 공급자, 대규모 처리량은 아직 실측하지 않음.
- 요약 생성/자동 키워드/문서 대표 임베딩/수정·삭제 API는 미구현.
- 검색은 정확 cosine + 단순 포함 검색 RRF이며 ANN/Oracle Text/BM25가 아님.
- 현재 schema는 1024차원 전용. 모델 구성은 .env와 설계서, profile 해시로 추적하며
  별도 EMBEDDING_PROFILE 이력 테이블은 후속 확장 대상.
- 카테고리는 문자열, 사용자 태그는 JSON 문자열. 계층형 카테고리 테이블은 후속 확장.
- 프로세스 중단 작업은 worker 중지 후 수동 복구 CLI 사용.
- 비밀값/Wallet/모델 캐시는 git 제외 확인. 원격 저장소 push는 수행하지 않음.


## 검색 평가 기준선 (2026-10-15)

실행 중인 한국어 임베딩 + 원격 Oracle + 키워드 혼합 검색 API를 읽기 전용 측정했다.
활성 문서 6개 중 원문 확인한 4개를 정답으로 삼은 합성 양성 질문 20개,
무응답 질문 8개와 다른 프로젝트 scope 질문 2개로 구성했다. 사용자 실제 질의 로그는 아니다.
30개 × 3회, 워밍업 1회 별도. 유사도 기준 0.28. 임베딩 프로필
`65e672b3edc9f0aeb92dc75b59e56439e4c8193ea71aa47ede6da2b921253d36`.

- Recall@5/20: 1.0, MRR@5: 0.900, nDCG@5: 0.9262 (양성 20개 기준)
- 무응답 정확도: 1.0 (음성 10개 기준)
- HTTP 검색 왕복 지연 p50: 398.7ms, p95: 454.2ms, 첫 워밍업: 625.7ms
- 폐기/이전 revision 제외: 이번 데이터 세트에서 미측정
- `.run/search-eval/cases.jsonl` 및 `baseline-20261015.json`은 로컬 전용이며 Git 제외

문서가 6개뿐이라 Recall@5/20에 큰 한계가 있다. 이 값으로 리랭커 필요성/효과나
실제 질의 품질을 일반화하지 않는다. dev/test는 정답 문서별로 분리했으며 아직 튜닝하지 않았다.
지표 단위 테스트는 중복 결과, 다른 revision, 순위 계산, 무응답 분모, 오류 실패,
낡은 라벨 거부와 워밍업/반복 처리를 확인한다. 검색 기능 자체는 변경하지 않았다.


## 선택적 리랭커 실험 (2026-10-15)

별도 8011번 API에서 같은 원격 Oracle corpus/임베딩 profile/30질의를 사용했다.
모델 dragonkue/bge-reranker-v2-m3-ko, revision `2aca5884ecac490192af9ebd86836d9073d826cd`,
MPS, batch 4, max_length 512, RRF 최대 20문서 × 3청크. 실제 corpus는 6문서라 최대 후보는 작다.
비교 후 실험 API는 종료했고 기존 8000 API와 DB/기존 기억은 변경하지 않았다.

| 방식 | Recall@5 (양성20) | MRR@5 | 무응답 정확도 (음성10) | p50 / p95 |
|---|---:|---:|---:|---:|
| 기존 RRF + cosine 0.28 | 1.00 | 0.900 | 1.00 | 399 / 454ms |
| 리랭커 cutoff 0.5 | 0.55 | 0.550 | 1.00 | 543 / 765ms |
| 리랭커 cutoff 0 (순위만) | 1.00 | 0.925 | 0.20 | 542 / 678ms |
| dev 선택 cutoff 0.0001 | 0.75 | 0.750 | 1.00 | 오프라인 계산 |

리랭커는 각 질문 1회, 기준선은 3회이며 지연은 통계적 우열 검증이 아니다. 첫 워밍업은
각각 약 14.2초/9.9초로 모델 로딩 비용이 포함된다. cutoff 0은 후보를 버리지 않아
무응답 질문에 오탐이 발생한다. 리랭커 순위만 보면 평균 개선이 작게 나타나지만,
단일 점수 cutoff는 기억 질의의 정답을 과도하게 제외한다.

미리 정한 cutoff grid에서 dev Recall@5와 무응답 정확도 평균을 최대화하면 0.0001이 선택됐다.
이때 **dev 정답은 5/10, test 정답은 10/10**, 음성은 각각 4/4, 6/6이다.
따라서 test의 좋은 결과만으로 전체 향상이라 주장할 수 없다. corpus/질문 유형에 매우 민감하다.
이 실험에서 기본 활성화는 타당하지 않아 `RERANKER_ENABLED=false`를 유지했다.
0.5는 실험용 초기 설정일 뿐이고 0.0001 역시 추천값이 아니다.

실험 결과 파일은 `.run/search-eval/reranker-mps-20261015.json`,
`reranker-ungated-20261015.json`, `cutoff-selection.json`이며 Git에서 제외한다.
실제 사용자 질의/혼동 문서/장문 corpus 추가 및 순위 재정렬과 제외 정책을 분리한 후속 평가가 필요하다.

검증: 전체 94 tests, Ruff 및 mypy 통과. 테스트에서 리랭커에 전달되기 전 소유자/scope/
폐기/이전 revision 제외, cosine 아래 정답 복구, top_k 후처리, 오류 점수 거부를 확인했다.


## 검색 웹 화면 (2026-10-15)

`/knowledge`에 검색/목록/원문 화면을 제공하고 기존 8000 API를 재시작해 반영했다.
실제 Chrome + 원격 Oracle에서 토큰 연결, 목록, 의미 검색, 정확한 revision 원문,
연결 해제 시 결과 삭제, 잘못된 토큰 차단, 로컬/세션 스토리지 미사용을 검증했다.
1280px 데스크톱과 390px 모바일 레이아웃, JS 오류 없음 확인. 전체 95 tests 및 정적 검사 통과.
공개 화면만으로 지식은 조회할 수 없으며 기존 Bearer 인증/사용자 격리를 유지한다.
공통 SKILL.md, AGENTS.md, MCP 설명에 같은 대상/scope의 검증된 보충을 전체 본문 revise로
반영하도록 보강했다. 글로벌 설정/이미 설치한 스킬 사본은 수정하지 않았다.


## 서비스 중심 폴더 정리 (2026-10-15)

루트 프로젝트를 vector-knowledge로 명명하고 Foundation을 packages/python-foundation workspace
의존 패키지로 분리했다. 예제 앱/예제 migration/기반 테스트/문서/검증 스크립트도 그 아래로 이동했다.
루트 migrations + alembic.ini는 지식 서비스만 관리하며 DB revision/테이블은 변경하지 않았다.
이전 portable 단계의 Foundation sdist에 지식 앱을 함께 넣던 구성은 더 이상 사용하지 않는다.
Foundation wheel/sdist는 기반 패키지 전용이고 서비스는 Git checkout + setup으로 배포한다.

- 서비스+Foundation 전체 95 tests, Ruff, mypy 통과
- Foundation 별도 실행 CRUD/CSRF 계약과 설치 wheel 소비 6조합 통과
- 빈 임시 체크아웃에서 uv sync --locked, 설정/스킬 설치, migration, API+worker 기동/종료 4 tests 통과
- 문서 상대 링크 누락 0개, 스테이징 파일에서 실제 로컬 password/token 및 Wallet 제외 확인
- 기존 .env, Wallet, 모델 캐시, MCP 스크립트 등록 경로 유지


## 머신·출처 기록 (2026-10-16)

Oracle migration vk0003 및 origin_machine_id/origin_machine_label/sources_json 컬럼 적용 확인.
API/worker를 새 코드로 실행했다. 101 tests와 Ruff/mypy 통과. 테스트는 머신 A의 지식을
머신 B가 보충할 때 출처 누적, 이전 revision 불변, 소유자 격리, 잘못된 URL/로컬 출처 거부,
multipart 업로드, MCP 클라이언트 식별을 포함한다. 기존 .env에 이 클라이언트의 랜덤 ID만 추가했다.
기존 기억의 과거 출처는 추정해 채우지 않았다. NoSQL/자동 원본 동기화는 미구현이다.


## 출처 실측 및 로컬 자동 연결 (2026-10-16)

실제 MCP 저장 → READY → 원문 조회에서 작성 클라이언트 ID와 로컬 문서 출처를 확인했다.
Chrome에서 토큰 파일을 읽거나 수동 입력하지 않고 목록/검색을 이용했으며 원문 창에 머신과
위치가 표시되는 것을 검증했다. 데스크톱/모바일, 연결 해제/잘못된 토큰 처리도 통과했다.
자동 연결은 development + loopback bind/peer + localhost Host + 동일 Origin/Fetch-Site +
UI 요청 헤더에 한정한다. API의 일반 Bearer 인증은 유지한다. 102 tests 및 정적 검사 통과.

## 2026-10-16 노트 편집 화면

- 전체 테스트 중 103개 통과 후, 화면 제목 변경에 따른 기존 단언 1개를 수정하고 해당 테스트 통과 확인(총 104개).
- Ruff check/format, mypy, JavaScript 구문 검사 통과.
- 임시 SQLite + 테스트 임베더 + 실제 Chromium: 카테고리, 10개 페이지 이동, 수정 유실 방지, 저장/READY/HUMAN 표시, 검색, 모바일 폭, 로그아웃과 브라우저 저장소 미사용 확인.
- 실제 Oracle vk0004 마이그레이션 적용 및 재시작. 브라우저 자동 연결, 목록, 정확한 원문, 기존 검색을 읽기 전용 검증. 사용자 원문을 UI 시험용으로 변경하지 않음.
- 웹 편집은 선언된 HUMAN 출처를 기록한다. 브라우저 머신 ID는 추측하지 않으며 기존 원문 출처 참조는 유지한다.
- RDF 기능은 제안 문서만 있으며 미구현. 현재 계정의 RDF 권한/네트워크 사용 가능 여부는 검증 전이다.


## 2026-10-16 업무 흐름 RDF / 코드형 노트 보강

- 전용 VK_FLOW_RDF/VK_FLOW 네트워크 생성 및 vk0005 적용. 한국어 트리플의 저장·조회 해시 일치와 롤백 후 잔여 없음 확인.
- 실제 MCP: 업무 흐름 등록 절차 원문 READY → 원문 근거 확인 → 관계 4개 저장 → oracle_rdf READY 조회 성공. Kev graph_extract는 agent_review(0.5916), 에이전트가 명시된 순서를 확인해 저장했다. graph_lookup은 0.6119로 조회했고 실제 검색 결과에 관계가 포함됨.
- 테스트는 원문 근거 누락, 버전 변경/폐기, 타 사용자 격리, 멱등 재요청, 불변 관계 충돌, RDF 직렬화, Kev 구간과 저장 거부 정책, MCP 관계 장애 시 원문 보존을 포함한다. Kev 한국어 정확도 벤치마크를 대체하지 않는다.
- 브라우저: Tab 들여쓰기·Enter 유지, 줄 수 갱신, wrap 옵션, 기본 자동 줄바꿈·모바일 가로 넘침 없음 확인. 기존 편집·저장·검색 검증도 통과.
- 원문만 저장하면 관계가 저절로 생성되는 것은 아니다. MCP 판단 결과에 따라 에이전트가 근거 있는 관계를 제출해야 한다. HTTP/Web 검색은 기존 동작을 유지한다. 임의 SPARQL 및 자동 업무 실행은 제공하지 않는다.

후속 UI 확인: 자동 줄바꿈에서도 논리 줄 번호를 유지하고 접힌 행 높이에 맞춰 정렬한다. 업무 흐름 탭은 실제 Oracle 노트의 5개 노드·4개 간선을 표시했고, 근거 선택/원문 전환/모바일 가로 넘침 없음과 브라우저 오류 없음 확인.
