# 설치와 실행 (macOS / Linux)

먼저 [실행 위치·모델 선택](portable-setup.md)을 확인하세요. Docker는 필수가 아니며 Kev는 기본 판단 계층입니다.

필요 사항: Git, Python 3와 venv/pip, 접속 가능한 기존 Autonomous Database, 압축 해제한 Wallet.
설치 스크립트가 프로젝트 전용 uv와 Python 3.12 환경을 준비한다. Windows/WSL의 신규 Oracle·모델 설치는 아직 검증하지 않았다.

```sh
git clone https://github.com/devmrko/adb-agent-knowledge.git adb-agent-knowledge
cd adb-agent-knowledge
./scripts/setup.sh
```

생성된 `.env`에서 다음 값을 채운다. 기존 `.env`는 설치 시 덮어쓰지 않는다.

```dotenv
USER_NAME=your_database_user
USER_PASSWORD="your_database_password"
WALLET_PASSWORD="your_wallet_download_password"
WALLET_DIR=./secrets/wallet
ORACLE_DSN=your_database_low
```

- Wallet ZIP을 `secrets/wallet/`에 압축 해제하거나 WALLET_DIR에 절대 경로를 지정한다.
- 디렉터리에 `tnsnames.ora`와 `ewallet.pem`이 있어야 한다. DSN은 tnsnames.ora의 서비스 별칭이다.
- DB 비밀번호와 Wallet 다운로드 암호는 다를 수 있다. `#` 등이 포함된 비밀번호는 따옴표로 감싼다.
- DB 계정은 로그인 및 이 앱의 테이블/인덱스/제약조건을 생성할 수 있어야 한다.
- DEV_API_TOKEN은 setup이 새 .env에 생성한다. 이 토큰과 Wallet/.env는 Git에 올리지 않는다.

```sh
./scripts/run_knowledge.sh --migrate
```

첫 실행은 DB 스키마를 생성/업그레이드하고 API와 색인 worker를 함께 실행한다.
이후에는 `./scripts/run_knowledge.sh`. Ctrl-C로 함께 종료한다. 다른 API/worker 인스턴스는
먼저 종료한다. Oracle DDL은 자동 커밋되므로 기존 운영 DB의 migration은 검토 후 수행한다.

- 검색 화면: http://127.0.0.1:8000/knowledge
- API 문서: http://127.0.0.1:8000/docs
- 상태: http://127.0.0.1:8000/actuator/health
- API 인증: `.env` DEV_API_TOKEN을 Bearer token으로 사용
- API_HOST/API_PORT로 주소 설정. 기본은 이 머신에서만 접속 가능한 127.0.0.1.
- 기본 개발 인증은 1명의 developer 계정이다. 다른 머신에서 같은 DB 계정/개발 인증을 사용하면
  같은 개인 지식에 접근한다. 운영 다중 사용자는 ENVIRONMENT=production 및 JWT 설정이 필요하다.


## 모델과 그래프 준비

기본 agent 모드에는 Kev와 임베딩 모델이 필요하며 별도 생성형 모델 설치는 필요하지 않다.
임베딩은 API·워커 머신에서 실행하고 Oracle은 벡터 저장·검색을 담당한다.
[모델 실행 위치](local-models.md)와 [RDF·Property Graph 초기화](oracle-graph-examples.md)를 참고한다.
무인 관계 추출을 위한 선택적 service 모드의 Gemma 구성은 [선택적 service 모드 설치](local-full-setup.md)를 따른다.

## 다음 단계

- [브라우저에서 검색하기](search-ui.md)
- [Codex / Claude 연결하기](agent-installation.md)
- [모델 실행 위치와 Kev 설정](local-models.md)
- [문제가 생겼을 때](knowledge-development.md#장애-복구)
