# 개인 지식 검색 API — 개발 설계

상태: 구현 기준 초안, 2026-10-15. Python Foundation을 보존하고 knowledge_app 소비 앱을 추가한다.

## 범위
텍스트/Markdown, 텍스트 PDF, 공개 HTTPS URL 입력. 사용자별 목록/원문/관련 청크 검색.
답변 생성과 자동 요약은 선택 확장으로 남긴다. 스캔 PDF는 OCR이 필요하다는 오류를 반환한다.
기존 Autonomous DB 사용. 접속 정보가 제공되기 전 SQLite는 테스트 전용이다.
개발은 Apple Silicon CPU/MPS, 배포는 A10 CUDA; 동일 SentenceTransformer 모델 사용.
첫 후보 dragonkue/snowflake-arctic-embed-l-v2.0-ko, 1024차원. 모델 revision을 프로필에 포함한다.

## 계층과 인증
FastAPI Router -> KnowledgeService -> Repository. Foundation의 Actor, Security, UoW, 오류 응답 재사용.
소유자는 issuer+subject의 SHA256으로 결정하며 요청 user_id는 받지 않는다.
개발 인증은 명시적으로 설정한 로컬 Bearer 토큰 하나; production에서는 기존 JWT verifier 필수.

## 데이터 모델
VK_ITEM(id, owner_id, title, knowledge_type, category, tags, active_revision_id, created_at).
VK_REVISION(id, owner_id, item_id, content_text, summary_text nullable, source_type,
 source_url, filename, mime_type, original_data BLOB, created_at).
VK_JOB(id, owner_id, revision_id, status, stage, error_code, created_at, started_at).
VK_CHUNK(id, owner_id, revision_id, chunk_no, text, page_no, char_start, char_end,
 profile_id, embedding VECTOR(1024,FLOAT32)).
각 부모는 (owner_id,id) UNIQUE, 자식 복합 FK로 교차 사용자 연결 방지.
카테고리/사용자 태그는 초기 단순 속성; 다중 계층 분류 UI가 필요할 때 정규화한다.
프로필은 모델명/revision/dimension/청크 설정/프롬프트 규칙 해시로 식별한다.

## 처리
원본과 QUEUED 작업을 같은 트랜잭션에 저장. 별도 CLI worker가 조건부 UPDATE로 claim.
프로세스 종료로 RUNNING에 남은 작업은 명시적 retry로 복구(작업이 실제 중지된 후).
추출/임베딩 완료 후 청크 저장+active revision 전환+READY를 하나의 트랜잭션으로 수행.
외부 추론 중 DB 트랜잭션을 유지하지 않는다. BackgroundTasks는 사용하지 않는다.
파일 크기와 추출 문자 수 제한. URL은 명시적 호스트 allowlist + 공개 IP 검증,
검증 IP에 연결하고 원래 호스트로 TLS 검증; redirect 거부. 원본 HTML은 실행하지 않는다.

## 검색
문서와 질의는 같은 모델/revision/profile을 사용. Oracle은 사용자/profile 제한 후
VECTOR_DISTANCE COSINE으로 정확 검색. 첫 버전은 ANN 인덱스 없이 정확도 기준 확보.
SQLite 테스트 경로는 Python cosine. 키워드 후보와 벡터 후보는 RRF로 결합.
청크를 지식별 묶고 revision_id, 원문 위치, 전체 원문 API를 반환한다.
사용자/유형/category 필터는 후보 검색에 적용. 점수는 확률이 아니다.

## 운영/제약
Oracle DDL 마이그레이션은 사용자 접속 설정 확인 후 새 VK_ 테이블만 생성한다.
원본은 초기 BLOB 저장, Object Storage로 옮길 인터페이스는 추후 확장.
단일 worker부터 시작; 자동 lease recovery, 자동 요약, OCR, 삭제/수정 API는 후속 범위.
DB/모델 연결을 실제 검증하지 않은 상태에서는 통합 검증 완료로 보고하지 않는다.

## 검증
Foundation 전체 회귀 검사 + 두 사용자 간 목록/상세/원문/검색/작업 격리,
작업 실패/재시도, PDF/HTML 추출, URL 사설주소 거부, 모델 프로필 불일치 차단.
Oracle SQL 컴파일 검사와 실제 DB 접속 후 등록→worker→검색 흐름을 구분해 보고한다.
