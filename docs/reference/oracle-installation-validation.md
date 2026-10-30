# Oracle 설치·모델 설치 실검증 — 2026-10-30

## 실행 환경과 경계

- 기존 테스트용 Autonomous AI Database 안에 새 전용 스키마를 생성했다. 운영 업무 스키마는 변경하지 않았다.
- Oracle product version_full: 23.26.4.1.0. 테스트 계정은 DATA tablespace 256MB quota와
  CREATE SESSION/TABLE/TRIGGER/VIEW/SEQUENCE/PROCEDURE/TYPE/PROPERTY GRAPH 권한을 사용했다.
- macOS 26.7.1 arm64, API Python 3.12.15, 별도 Kev Python 3.13.16.
- DB 서비스/계정만 준비했으며 앱 테이블·트리거·RDF·Property Graph는 저장소의 migration/초기화 코드를 실행해 생성했다.
- Wallet·ADMIN 암호·테스트 계정 암호·실제 DB 서비스 주소는 공개 저장소에 포함하지 않는다.

## 통과한 실제 Oracle 검사

1. 빈 스키마 → vk0010까지 Alembic 실행, 기존 행을 하나 기록한 뒤 vk0011 업그레이드.
2. 기존 행 보존 및 과거 감사 이력의 소급 미생성 확인.
3. 감사 트리거 16개 ENABLED, USER_ERRORS의 트리거 컴파일 오류 0개.
4. 새 감사 대상 5개 테이블의 변경 전후 스냅샷과 outbox 기록 확인.
5. vk_g_operation UPDATE/DELETE 거절, 트랜잭션 rollback 시 원본·감사·outbox 변경 함께 취소.
6. prepare_knowledge_rdf로 VK_FLOW/VK_SHARED/VK_NAV 준비. 재실행 시 기존 그래프 보존.
7. setup_property_graph --apply로 View/Property Graph 생성 및 GRAPH_TABLE 실행.
8. 실제 한국어 로컬 임베딩으로 가상 원문 저장 → worker READY → 벡터·키워드 검색.
9. 가상 Cafesto 개체·관계·별칭·검토 이력 등록, 검색에서 oracle_rdf와 oracle_property_graph 경로 확인.
10. 다른 합성 사용자의 원문 검색·감사 조회에서 데이터가 노출되지 않음 확인.

마지막에는 새 공개 CLI 자체로 migration부터 그래프·모델 검증까지 다시 실행해 통과했다.
아래 값은 실행 예시이며 자신의 테스트 계정/경로로 바꾼다.

```sh
./.venv/bin/python -m scripts.validate_oracle_installation \
  --env-file .run/oracle-test.env --expected-schema AK_TEST_01 --apply --graphs --models
```

## 설치 스크립트 검증

```sh
./scripts/setup.sh --with-models --verify-models
```

이 한 명령 전체가 macOS arm64에서 통과했다. API의 locked 의존성과 고정 커밋 Kev의 별도
가상환경을 설치하고, 임베딩 문서/질의 1024차원 출력 및 Kev noul 응답을 실제 확인했다.
검증용 Kev는 임시 포트에서 실행 후 종료했다. 기존 .env는 보존했다.

Kev 소스/환경은 이 체크아웃의 .tools/kev에 새로 준비했다. uv 다운로드 캐시와 기존 모델
가중치 캐시는 재사용했다. 모든 패키지·가중치를 인터넷에서 처음 내려받는 clean-room 설치나
오프라인 설치 성공을 의미하지 않는다. 실제 운영 동시 프로세스의 최대 메모리·처리량을 측정한 것도 아니다.

## 자동 검사

Ruff check/format, mypy(62개 소스), pytest 262개를 통과했다. 설치 계획의 무변경,
OS 거절·설치 실패 전파·명시적 테스트 스키마 보호를 추가 검증했다.

## 남은 검증

- 새 ADB 서비스 자체의 생성·전체 계정 정책, Linux/Windows/WSL에서 이번 통합 설치기의 실제 모델 실행.
- 운영 JWT/HTTPS/브라우저 전체 경로. API 검증은 TestClient와 합성 인증 주체를 사용했다.
- Kev의 한국어 판단 정확도·대규모 검색 품질·GPU 성능·전체 동시 운영 RAM 최소치.
- 선택적 service 모드 생성형 LLM/Ollama/Gemma 설치. 기본 agent 모드에는 요구되지 않는다.

테스트 스키마와 가상 원문은 재확인을 위해 남겼다. 운영 DB migration이나 운영 서비스 배포를
수행한 것으로 해석하지 않는다. [OS·설치 안내](../guides/runtime-installation.md).

## English summary

Verified on macOS arm64 against a new isolated schema in an existing Oracle ADB (23.26.4.1.0), using
repository Alembic/RDF/Property Graph entrypoints. Confirmed 16 enabled audit triggers with no compilation
errors, additive preservation, row snapshots/outbox rollback, append-only operation history, real Korean
embeddings and source READY/search, RDF/Property Graph retrieval, identity/review writes and owner isolation.
The public validation CLI repeated the checks successfully. No production schema was modified.

The integrated setup command installed a separate pinned Kev environment and passed actual embedding and
Kev inference checks. Existing download/model caches were reused. Fresh database-service provisioning,
other operating systems, production JWT/HTTPS/browser behavior, model quality and load limits are not
certified. Runtime OS support is documented separately; this is not an all-platform guarantee.
