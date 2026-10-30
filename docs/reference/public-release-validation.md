# 공개 preview 검증 — 2026-10-29

> Historical, dated evidence: this record does not certify the current deployment or repeat earlier live tests. See [current documentation](../README.md).

## 배포본 범위

현재 개발 소스를 별도 폴더로 내보낸 독립 Git 저장소다. 기존 작업 폴더와 운영 서버는
수정하지 않았다. 기존 Git 이력, 환경 파일, Wallet, 데이터, 모델 캐시, 가상환경 및 개인 서버
키 발급/접속 도구를 배포 소스에서 제외했다. 개인 경로와 운영 주소는 일반 예제로 정리했다.
소스 원본 설계 문서는 보존하며 과거 운영 검증 기록은 새 사용자 설치 보장을 의미하지 않는다.

현재 운영 저장소는 Oracle Autonomous Database에 종속된다. 벡터·RDF·SQL Property Graph는
Oracle 구현이다. SQLite 테스트는 대체 운영 DB 지원이 아니다. 선택 가능한 모델 제공자와
선택 가능한 저장 DB를 혼동하지 않는다.

## 확인한 항목

- macOS Apple Silicon, Python 3.12: 새 폴더에서 setup.sh로 독립 가상환경과 .env 생성.
  기존 uv 패키지 다운로드 캐시는 재사용할 수 있으나 기존 가상환경·Wallet·설정은 복사하지 않았다.
- uv.lock을 유지한 knowledge + mcp 의존성 설치 성공. 생성된 .env는 0600이며 Git 제외.
- ruff check/format, mypy(54개 파일), pytest 204개 통과.
- Foundation sdist/wheel 빌드 및 독립 환경 설치 성공. SQLite/Oracle 생성 템플릿 ×
  session/token/mixed 총 6개 조합 검증. 런타임 DB는 모두 SQLite이며 실제 Oracle 검증이 아니다.
- 전역 uv가 없는 환경에서 wheel 검증 실패를 발견해 저장소 uvw를 기본 실행기로 수정 후 통과.
- Gitleaks 8.30.1: 원본 저장소 로컬의 --all 이력 15개 커밋 검사에서 탐지 0건.
  공개 사본의 선택된 소스 검사에서도 탐지 0건. 원격에만 있는 이력, 삭제된 비도달 객체나
  호스팅 서비스 캐시는 검사 범위가 아니다. 자동 검사 통과는 비밀정보 부재의 절대 보장이 아니다.
- 설치된 Python 의존성 80개의 선언된 라이선스 목록을 별도 기록했다.
  모델 및 의존성 전체에 대한 법률 검토를 완료했다는 뜻은 아니다.

## 아직 확인하지 않은 항목

- 새 Oracle ADB/빈 스키마에서 권한·Wallet·전체 migration·RDF·Property Graph 초기화.
- 새 계정에서 실제 모델을 사용한 저장 READY → 검색 → 수정 → 과거 이력 전체 흐름.
- 새 머신에서 Kev/Gemma 최초 다운로드·구동과 CPU/GPU 조합별 자원 요구량.
- Windows/WSL 및 Linux에서 실제 Oracle·모델을 연결하는 신규 설치.
  Ubuntu GitHub Actions의 의존성 설치·자동 테스트·wheel 검증은 아래와 같이 통과했다.

따라서 공개 가능한 preview 소스이며, 새 사용자의 전체 설치를 검증한 정식 릴리스는 아니다.
DB/모델 자격증명을 포함하지 않으며 사용자가 자신의 환경을 준비해야 한다.

## 재현 명령

```sh
./scripts/setup.sh
./uvw run ruff check .
./uvw run ruff format --check .
./uvw run mypy
./uvw run pytest
./uvw build --package devmrko-python-foundation
./uvw run python packages/python-foundation/scripts/verify_wheel.py
```

Oracle 신규 환경의 검증 순서는 [설치 가이드](../guides/portable-setup.md)를 따른다.

## GitHub Ubuntu CI 결과

[verify 40820684727](https://github.com/devmrko/adb-agent-knowledge/actions/runs/40820684727),
소스 커밋 1f32ef2: 2026-10-29 성공. Python 3.12 locked 설치, ruff, mypy, pytest,
Foundation 런타임 smoke, wheel 빌드와 독립 설치 검증을 모두 통과했다.
이 CI는 실제 Oracle ADB나 Kev/Gemma 모델을 실행한 검증은 아니다.

## v2 preview (0.2.0)

2026-10-29: agent/service 선택, 생성 제공자 미생성, 원문 버전·소유권·부분 문서 보호,
기존 서비스 작업 보존·재개와 MCP Kev 연동 테스트를 추가했다. ruff, mypy, 전체 pytest,
Foundation wheel 독립 설치 검증과 웹 JavaScript 문법 검사를 수행했다.
실제 새 Oracle ADB나 모델 품질/속도를 추가 검증한 것은 아니다. 운영 서비스는 변경하지 않았다.
