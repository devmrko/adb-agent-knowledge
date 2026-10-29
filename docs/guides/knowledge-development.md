# 개발과 운영

## 데이터와 인증
기존 `.env`의 USER_NAME/USER_PASSWORD/WALLET_PASSWORD를 사용한다. Wallet 파일은 저장소 밖에 둔다.
DB 비밀번호와 Wallet 암호는 별개다. `.env`는 gitignore 및 파일 모드 600으로 보호한다.
개발 token은 단일 developer 사용자에 매핑된다. 임의 user_id 요청은 거부한다.
실제 다중 사용자는 JWT issuer+subject로 구분하며 production에서는 JWT verifier를 사용한다.
Swagger의 Authorize에 Bearer token을 입력한다. 운영 배포 시 외부 TLS/인증 서버 구성이 필요하다.

## API
| Method | Path | 설명 |
| --- | --- | --- |
| POST | /api/v1/knowledge | title, text 또는 url, knowledge_type, category, tags |
| POST | /api/v1/knowledge/files | multipart file + title, PDF/PPTX/plain/Markdown, memory_kind, scope, idempotency_key |
| GET | /api/v1/knowledge | offset, limit, category |
| GET | /api/v1/knowledge/{id} | 지식 메타데이터 |
| POST | /api/v1/knowledge/search | query, top_k, category, knowledge_type |
| GET | /api/v1/knowledge/{id}/revisions/{revision_id}/content | 전체 추출 원문 |
| GET | /api/v1/jobs/{job_id} | QUEUED/RUNNING/READY/FAILED |
| POST | /api/v1/jobs/{job_id}/retry | FAILED 작업 재시도 |

등록은 202로 job_id를 반환한다. 워커가 실행돼야 READY가 된다. 생성형 요약은 아직 수행하지 않는다.
URL 등록은 URL_ALLOWED_HOSTS에 정확한 호스트가 필요하며 HTTPS 443만 허용한다.
공개 IP를 검증하고 그 IP에 TLS 연결한다. redirect는 거부하며 최종 URL을 직접 등록한다.
텍스트는 UTF-8만 지원한다. 스캔 PDF는 NO_TEXT_OCR_REQUIRED, 암호화 PDF는 지원하지 않는다.
기본 제한은 원본 10MB(PPTX 파일 업로드만 100MB), 추출 텍스트 20만 문자, PDF 500페이지. 불신 PDF의 파싱은 배포 시 제한된 별도 프로세스로 격리할 것을 권장한다.

## 검색
Oracle 정확 cosine 검색 상위 100개와 단순 키워드 포함 검색 상위 100개를 RRF로 결합한다.
키워드는 매칭 필드/용어 개수로 정렬한다. Oracle Text/BM25 구현으로 표시하지 않는다.
사용자/category/type/memory_kind/scope/ACTIVE 상태/profile/활성 revision 조건은 후보 검색에 적용한다.
청크 기준 후보를 지식 단위로 묶으므로 top_k보다 적은 지식이 반환될 수 있다.
RRF score는 관련성 확률이 아니다. min_similarity(기본 SEARCH_MIN_SIMILARITY=0.28)보다 낮고 모든 질의어 일치도 아닌 청크는 제외한다. 0.28은 잠정값이며 실제 데이터로 보정해야 한다.

## 모델과 A10
모델 revision은 40자리 commit SHA로 고정한다. 변경 시 profile이 달라지므로 기존 데이터 재처리가 필요하다.
현재 Oracle DDL은 1024차원 전용. 차원이 다른 모델은 별도 마이그레이션이 필요하다.
개발은 EMBEDDING_DEVICE=cpu. MPS와 CUDA는 같은 설정 인터페이스지만 아직 별도 실측이 필요하다.
A10에서는 EMBEDDING_DEVICE=cuda로 설정하고 NVIDIA 드라이버/PyTorch CUDA 호환성을 검증한다.
CUDA는 BF16, CPU는 기본 정밀도. 질의는 모델의 query prompt를 사용한다.
API와 worker가 각각 모델을 적재하므로 운영 확장 시 단일 추론 서비스로 분리할 수 있다.

## 장애 복구
FAILED는 사용자 API로 재시도한다. 프로세스가 죽어 RUNNING이면 모든 worker를 중지한 뒤:

```sh
./uvw run --extra knowledge python -m scripts.recover_knowledge_jobs --workers-stopped --job-id <id>
```

살아 있는 worker와 동시에 복구하면 중복 처리가 발생할 수 있으므로 자동 timeout 복구는 제공하지 않는다.

## 로컬 테스트와 Oracle
자동 테스트의 SQLite는 빠른 격리 테스트용이며 실제 Oracle의 VECTOR 성능을 대체하지 않는다.
`alembic.ini`와 vk_alembic_version은 템플릿의 example migration과 분리돼 있다.
원본 예제와 Foundation tests는 packages/python-foundation/에 격리해 유지한다. 운영 DB 마이그레이션은 별도 승인/배포 절차로 실행한다.

## 기억 관리 (vk0002)
- memory_kind: DOCUMENT, FACT, PREFERENCE, DECISION, PROCEDURE, EPISODE. 기존 knowledge_type과 독립적이다.
- scope: global, project:<key>, thread:<key>, agent:<key>. key는 영문 소문자·숫자·점·밑줄·하이픈이다.
  global은 공개 범위가 아니라 **인증된 사용자 내 전역**이다. scopes 생략 시 사용자 내 모든 범위를 조회한다.
- 저장에 idempotency_key를 지정하면 같은 사용자/입력의 재요청은 기존 ID와 현재 작업 상태를 반환한다.
  동일 키로 내용이 다르면 409. 키를 생략한 서로 다른 요청의 의미 중복은 자동 병합하지 않는다.
- POST /api/v1/knowledge/{id}/revisions: text, expected_revision_id(이력의 최신 revision), change_note.
  새 색인이 READY가 되기 전에는 기존 active 원문을 제공한다. 오래된 expected ID는 409다.
- POST /api/v1/knowledge/{id}/retire: reason, superseded_by(선택). 물리 삭제 없이 검색에서 제외한다.
  대체 항목은 같은 사용자·범위의 ACTIVE 항목이어야 한다.
- POST /api/v1/knowledge/{id}/restore: reason(선택). 폐기 상태 해제 및 대체 관계를 초기화한다.
- GET /api/v1/knowledge/{id}/history: revision과 추가 전용 변경 이벤트 목록.
- POST /api/v1/knowledge/context: 검색 조건 + max_chars. 출처 ID/위치가 포함된 발췌 카드.
  max_chars는 발췌 본문 합계에 적용하며 JSON 메타데이터·토큰 수는 포함하지 않는다. 생성 요약은 아니다.
- 목록은 memory_kind/scope/include_retired, 검색은 memory_kinds/scopes/include_retired/min_similarity를 지원한다.

PPTX는 실제 슬라이드 순서와 노트 관계를 따라 추출하며 청크 location.page는 슬라이드 번호,
source_part는 body/notes다. 기존 데이터는 source_part=null일 수 있다. 이미지 OCR은 지원하지 않는다.
원문은 발표자 노트 구분자와 form feed 슬라이드 경계를 포함한다. ZIP 해제 크기는 100MB,
읽는 XML 항목 10MB, 슬라이드 500개, ZIP 항목 10000개 제한이다.

마이그레이션은 API/worker를 중지하고 RUNNING 작업이 없을 때 적용한다.
`./uvw run --extra knowledge --extra mcp alembic -c alembic.ini upgrade head`
Oracle DDL은 자동 커밋이므로 중간 실패 시 상태를 확인하고 수동 복구해야 한다.
이력 삭제를 막기 위해 vk0002 자동 downgrade는 제공하지 않는다.
