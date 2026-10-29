# 자기 Oracle ADB로 시작하기

Docker 없이 macOS/Linux에서 실행한다. Windows는 WSL을 사용한다.
이 저장소는 ADB를 자동 생성하거나 관리자의 권한을 부여하지 않는다.

## 1. 실행 위치 선택

| 구성 | 랩탑에서 실행 | 별도 서버에서 실행 |
|---|---|---|
| 가벼운 클라이언트 | MCP 클라이언트 | 지식 API/worker, Kev, 임베딩, 관계 추출 |
| 원격 모델 | 지식 API/worker/MCP | Kev, 임베딩, 관계 추출 |
| 로컬 모델 | 지식 API/worker/MCP 및 선택한 모델 | Oracle ADB만 원격 |

기본 판단 제공자는 Kev이다. 원격 Kev도 동일한 /v1/systemone 계약을 사용한다.
DecisionProvider 인터페이스로 다른 판단기를 구현할 수 있지만 현재 배포된 구현체는 Kev 하나다.
모델을 로컬에서 실행하면 Docker 유무와 무관하게 CPU/GPU와 메모리를 사용한다.

## 2. 설치와 DB 설정

```sh
./scripts/setup.sh
```

생성된 .env에서 USER_NAME, USER_PASSWORD, WALLET_PASSWORD, WALLET_DIR,
ORACLE_DSN을 입력한다. 비밀번호는 서로 다를 수 있다. Wallet 준비와 개발/운영 인증은
[기본 설치](quickstart.md)를 따른다. 기존 .env는 덮어쓰지 않는다.

## 3. 모델 연결 선택

### 기본: 로컬 한국어 임베딩 + Kev

.env.example의 EMBEDDING_PROVIDER=local, 고정 EMBEDDING_REVISION을 유지한다.

```sh
./scripts/setup_kev.sh
```

이후 서비스 실행 시 --kev를 추가한다. 이미 Kev가 실행 중이면 중복 실행하지 않는다.

### 원격 임베딩 + 원격 Kev

자신이 운영하거나 사용을 허가받은 endpoint를 입력한다. 예시 주소는 실제 서비스가 아니다.

```dotenv
EMBEDDING_PROVIDER=openai
EMBEDDING_URL=https://models.example.com/v1
EMBEDDING_API_KEY="your_embedding_key"
EMBEDDING_MODEL=your-1024-dimensional-model
EMBEDDING_REVISION=immutable-model-version
EMBEDDING_QUERY_PREFIX=""
KEV_PROVIDER=kev
KEV_URL=https://kev.example.com
KEV_ALLOW_REMOTE=true
KEV_API_KEY="your_kev_key"
```

임베딩은 /embeddings, Kev는 /v1/systemone을 호출한다. 채팅 completions endpoint는
임베딩/Kev를 대신하지 않는다. Kev 서버 앞의 TLS와 키 인증은 운영자가 구성해야 한다.
원격 제공자에는 색인 대상 원문 청크·질의 또는 판단용 짧은 텍스트가 전송된다.
HTTP는 loopback에만 허용한다. 환경 프록시와 redirect는 사용하지 않는다.

현재 Oracle 벡터 열은 **1024차원**이다. 임의의 차원은 지원하지 않는다.
원격 임베딩은 입력 순서를 검증하고 정규화한다. 모델의 query prefix 요구 사항을 확인한다.
서버가 prefix를 자동 적용한다면 중복 적용하지 않는다. 원격 청크는 문자 기준이며 기본 512자,
64자 겹침이다. 제공자의 토큰 한도와 한국어 품질을 별도로 검증한다.
API/worker에는 반드시 동일한 임베딩 설정을 사용한다.

**모델 변경은 기존 벡터와 호환되지 않는다.** 로컬/원격 청크 방식도 다르므로 같은 모델명이어도
프로필이 다르다. 모델 버전·차원·전처리의 프로필을 저장하며 다른 프로필끼리 비교하지 않는다.
현재 자동 재임베딩/무중단 전환 도구는 없다. 기존 설정을 유지하거나 별도 빈 스키마에서
시작한다. URL만 바꾸어도 같은 모델과 전처리를 제공한다는 운영자 보장이 필요하다.

## 4. 점검과 초기화

```sh
./.venv/bin/python -m scripts.doctor
./.venv/bin/python -m alembic -c alembic.ini upgrade head
./.venv/bin/python -m scripts.doctor --db
./.venv/bin/python -m scripts.prepare_knowledge_rdf
```

RDF 초기화 성공 후 WORKFLOW_RDF_ENABLED=true로 설정한다. SQL Property Graph는
[설치 안내](unified-graph-retrieval.md)를 따른다. doctor는 읽기 전용이며 모델을 실행하거나
다운로드하지 않는다. --db는 접속·벡터 연산·기존 활성 벡터 프로필을 확인한다.
모델 응답 속도, RDF 권한, 추출 품질까지 검증한 것으로 해석하지 않는다.

관계 자동 추출에는 별도의 모델이 필요하다. [Ollama/Gemma 설치](local-full-setup.md) 또는
[호환 API 설정](automatic-graph.md)을 따른다. Kev는 관계를 추출하는 생성 모델이 아니다.

```sh
./scripts/run_knowledge.sh --kev  # 로컬 Kev를 함께 시작
# 원격 또는 이미 실행 중인 Kev: ./scripts/run_knowledge.sh
```

웹: http://127.0.0.1:8000/knowledge . 서버 공개는 HTTPS와 운영 인증을 구성한 후 진행한다.
기본 개발 인증은 개인용이며 사용자 간 격리가 필요한 운영 설정을 대신하지 않는다.

## 5. Codex / Claude 연결

```sh
./.venv/bin/python scripts/install_agent.py codex --register-mcp
./.venv/bin/python scripts/install_agent.py claude --register-mcp
```

등록 후 새 세션에서 확인한다. [공통 스킬과 설치](agent-installation.md)를 따른다.
루트 .mcp.json은 .env에 KNOWLEDGE_SSH_HOST가 있으면 SSH MCP, 없으면 로컬 MCP 어댑터를 사용한다.
직접 등록하는 예시는 config/mcp.example.json이다. 원격 SSH MCP는 .env에 자신의
KNOWLEDGE_SSH_HOST와 KNOWLEDGE_REMOTE_DIR(절대 경로)을 입력하고
scripts/run_remote_knowledge_mcp.sh를 등록한다. SSH 클라이언트마다 고유 머신 ID를 유지한다.

## 출시 검증 상태

단위/통합 테스트와 mock provider 테스트는 실제 새 ADB에서의 설치 검증을 대체하지 않는다.
새 계정의 ADB 권한·Wallet, 원격 모델, RDF 초기화, 저장 READY → 검색 → 수정 → 이력 확인을
실행한 뒤 해당 환경을 지원 환경으로 기록한다. 이 공개 사본은 개인 배포 정보와 기존 Git 이력을 제외한 독립 배포본이다.
검증 상태는 [공개 준비 검증](../reference/public-release-validation.md)에 기록한다. 자동 재임베딩은 미구현이다.
