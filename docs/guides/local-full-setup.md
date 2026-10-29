# OpenRouter 없이 전체 기능 설치하기 — Oracle + Kev + Gemma 4

2026-10-19 기준. 개인 개발/내부 사용용 설치 절차다. Oracle은 원격 DB이며, 모델 추론은 로컬에서 수행한다. 인터넷 공개 서버의 HTTPS·인증·자동 재시작 구성을 대신하지 않는다.

## 무엇을 준비하는가

| 역할 | 구성 |
|---|---|
| 지식·원문 버전·벡터·RDF 저장 | 기존 Oracle Autonomous AI Database + Wallet |
| 한국어 임베딩 | snowflake-arctic-embed-l-v2.0-ko, 기존 설정 유지 |
| 저장·조회 경로 판단 | 별도 로컬 Kev |
| 자동 관계 추출·의미 검토 | Ollama + Gemma 4 E2B |
| 접근 | API·웹 화면·Codex/Claude MCP |

Gemma가 Kev나 임베딩 모델을 대체하지 않는다. OpenRouter 키는 필요하지 않으며 로컬 모델 실패 시 클라우드로 자동 전환하지 않는다. 최초 설치에는 모델/패키지 다운로드를 위한 인터넷이 필요하다.

공식 Ollama에는 `gemma4:e2b`가 제공된다. E2B는 유효 파라미터 규모를 뜻하며 모델 전체가 2GB라는 의미가 아니다. 다운로드 크기는 백엔드에 따라 약 4.6~7.5GB로 표시되며 실행 메모리에는 문맥 캐시와 임베딩·Kev가 추가된다. 여유 메모리를 확인하고, 이 구성 전체의 특정 RAM/GPU 최소치를 검증된 수치로 간주하지 않는다.

- [Google Gemma 4 설명](https://ai.google.dev/gemma/docs/core)
- [공식 Ollama Gemma 4 E2B](https://ollama.com/library/gemma4:e2b)
- [Ollama 설치](https://ollama.com/download)
- [OpenAI 호환 API·문맥 크기 설정](https://docs.ollama.com/api/openai-compatibility)

## 1. 프로그램 설치와 DB 접속 설정

```sh
git clone https://github.com/devmrko/adb-agent-knowledge.git
cd adb-agent-knowledge
./scripts/setup.sh
```

기존 체크아웃은 같은 디렉터리에서 진행한다. 설치 스크립트는 기존 `.env`를 덮어쓰지 않는다. `.env`에 다음 값만 실제 접속 정보로 입력한다. 토큰과 비밀번호는 출력하거나 Git에 넣지 않는다.

```dotenv
USER_NAME=your_user
USER_PASSWORD="your_db_password"
WALLET_PASSWORD="your_wallet_password"
WALLET_DIR=./secrets/wallet
ORACLE_DSN=your_service_low
```

Wallet 파일을 지정한 디렉터리에 준비한다. DB 계정은 앱 테이블 및 RDF 초기화에 필요한 권한이 있어야 한다. 권한 오류를 만나면 DB 관리자에게 필요한 권한을 확인한다. 앱이 관리자 비밀번호를 요구하거나 임의로 권한을 부여하지 않는다.

```sh
./.venv/bin/python -m scripts.check_knowledge_db
```

`Connection: OK`와 벡터 연산 성공을 확인한다.

## 2. 테이블과 RDF 초기화

기존 서버의 업데이트라면 API·워커를 먼저 정상 종료하고 진행한다. 실행 중인 임베딩 작업을 확인한다. Oracle DDL은 자동 커밋되므로 기존 운영 DB 변경 전에는 복구 절차를 준비한다.

```sh
./.venv/bin/python -m alembic -c alembic.ini upgrade head
./.venv/bin/python -m scripts.prepare_knowledge_rdf
```

RDF 준비 도구는 `VK_FLOW_RDF` 네트워크와 `VK_FLOW`, `VK_SHARED`, `VK_NAV` 그래프를 준비한다. 정상적인 기존 그래프는 유지한다. 일부만 만들어진 네트워크는 삭제·교체하지 않고 중단하여 상태 확인을 요구한다.

## 3. Ollama와 로컬 Gemma 준비

운영체제에 맞는 공식 Ollama를 설치하고 서버를 실행한다. 이미 앱이나 서비스로 실행 중이면 `ollama serve`를 중복 실행하지 않는다.

```sh
ollama serve
```

별도 터미널에서 이 저장소 디렉터리로 이동한 뒤:

```sh
ollama pull gemma4:e2b-it-qat
ollama create vector-knowledge-gemma4:e2b -f config/Gemma4.Modelfile
```

전용 모델 이름에는 문맥 크기 32768 설정을 적용한다. 서버는 loopback `127.0.0.1:11434`에서 사용한다. `-cloud` 모델을 선택하지 않는다. 모델 태그는 갱신될 수 있으므로 배포 시 `ollama list`와 `ollama show vector-knowledge-gemma4:e2b`로 설치 모델과 설정을 기록한다.

검증은 실제 저장된 지식 대신 한국어 가상 문장만 보내며 DB에 쓰지 않는다.

```sh
./.venv/bin/python -m scripts.check_local_graph
```

Cafesto 소속·생성 기반 관계를 추출하고 단순 도구 나열에서 관계를 만들지 않는지 확인한다. 실패하면 그대로 자동 추출을 켜지 말고 모델 지원·실행 메모리·문맥 설정을 확인한다. 이 검사는 작은 smoke test이며 실자료 전체의 정확성을 보증하지 않는다.

## 4. 로컬 프로필 적용

검증 후 `.env`의 그래프 관련 설정만 바꾼다. DB 접속 정보와 기존 토큰은 보존한다.

```sh
./.venv/bin/python -m scripts.configure_local_graph
./.venv/bin/python -m scripts.configure_local_graph --apply
```

적용되는 핵심 설정:

```dotenv
WORKFLOW_RDF_ENABLED=true
GRAPH_AUTO_ENABLED=true
GRAPH_AUTO_URL=http://127.0.0.1:11434/v1
GRAPH_AUTO_MODEL=vector-knowledge-gemma4:e2b
GRAPH_AUTO_ALLOW_REMOTE=false
GRAPH_AUTO_API_KEY=
GRAPH_AUTO_POLICY=auto_verified
GRAPH_AUTO_TIMEOUT_SECONDS=120
GRAPH_AUTO_MAX_CHARS=12000
GRAPH_AUTO_REASONING_EFFORT=none
```

빈 `GRAPH_AUTO_API_KEY`가 기존 OpenRouter 키 대신 사용된다. 원격 endpoint는 허용하지 않는다. `auto_verified`는 검토를 통과한 관계를 자동 연결하므로 잘못된 관계는 화면에서 수정·해제한다. 초기 실자료 평가를 수동으로 하고 싶으면 `GRAPH_AUTO_POLICY=review`로 바꿀 수 있다.

12000자를 넘는 원문은 조용히 자르지 않고 `SOURCE_TOO_LONG`으로 남는다. 긴 문서의 자동 분할 추출은 아직 없다. timeout도 무작정 늘리기보다 처리 속도·문맥·작업 lease를 함께 검토한다. 모델을 변경하면 기존 지식도 새 모델 기준의 추출 작업 대상이 된다.

## 5. Kev 설치와 서비스 실행

```sh
./scripts/setup_kev.sh
./scripts/run_knowledge.sh --kev
```

Kev는 고정 커밋의 별도 저장소와 Python 환경을 사용하며 첫 실행 때 모델을 다운로드한다. 기존 설치가 있으면 `.env`의 `KEV_REPO_DIR`로 지정할 수 있다. 이미 Kev를 별도 실행 중이면 중복 기동하지 않고 `./scripts/run_knowledge.sh`만 실행한다.

Kev가 응답하지 않으면 에이전트 판단/보완 경로를 사용하며, 그것을 Kev 정상 동작으로 보지는 않는다. A10에서는 NVIDIA 드라이버·PyTorch CUDA 호환성과 동시 모델 메모리를 별도 검증하고 `EMBEDDING_DEVICE=cuda`를 설정한다. 현재 A10 전체 구성의 실측 완료를 주장하지 않는다.

Ollama는 이 실행 스크립트의 관리 대상이 아니므로 별도 앱/서비스로 유지해야 한다. API·워커·Kev의 상시 재시작 구성은 별도 운영 작업이다.

## 6. 확인과 에이전트 연결

- 웹: `http://127.0.0.1:8000/knowledge`
- DB 연결을 포함한 API 상태: `http://127.0.0.1:8000/actuator/health`
- 지식 연결 → 추출 처리 내역: 모델 이름·작업 오류·자동 반영 결과 확인
- 관계 있는 지식만: 실제 활성 RDF 연결이 있는 노트 확인

```sh
./.venv/bin/python scripts/install_agent.py codex --register-mcp
./.venv/bin/python scripts/install_agent.py claude --register-mcp
```

새 클라이언트 세션에서 `knowledge_graph_extraction_schema`로 로컬 모델과 정책을 확인한다. 저장은 `READY`, 관계는 실제 자동 반영 성공을 확인한다. 기존 지식의 누락 요약/출처 RDF 보완이 필요하면 실행 중인 API에 대해 다음을 실행한다.

```sh
./.venv/bin/python -m scripts.backfill_navigation
```

이 명령은 자동 관계 추출 명령과 다르다. 자동 관계 워커는 기존 활성 원문도 발견한다. 건너뜀·실패·이전 기록의 재처리는 노트의 ‘추출’ 또는 MCP `knowledge_graph_extract`로 요청한다.

## 검증 범위

이 문서와 로컬 프로필·적용/검증 도구를 제공한다. 문서를 작성한 머신에는 Ollama가 설치되지 않아 **Gemma 4 실제 추론 속도·한국어 관계 품질·완전한 새 머신 설치는 아직 검증하지 않았다.** 현재 실행 중인 서비스의 OpenRouter 설정은 자동으로 바꾸지 않았다. 로컬 프로필을 적용하고 위 검사를 통과한 환경에서 운영 전환한다.
