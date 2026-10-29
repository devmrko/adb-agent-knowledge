# 서비스 중심 저장소 구조

루트는 vector-knowledge 실행 프로젝트(uv package=false), Foundation은 로컬 workspace dependency로 분리한다.
공개 배포 Foundation wheel의 이름/버전/import/API는 유지한다. 기존 실행 scripts와 MCP 경로도 유지한다.
knowledge_app는 서비스 코드, migrations와 alembic.ini는 VK 전용 migration이다.
Foundation src/example_app/alembic/tests/scripts/docs는 packages/python-foundation 아래에 모은다.
root tests에는 knowledge 테스트만 남기고 pytest 설정에서 두 테스트 트리를 모두 실행한다.
uv.lock은 workspace 전체 하나로 고정한다. root uv sync가 로컬 Foundation을 editable 설치한다.
DB 테이블명/마이그레이션 ID/vk_alembic_version은 변경하지 않고 migration 파일 경로만 바꾼다.
실제 DB migration은 이번 구조 변경으로 실행하지 않는다. 기존 .env/Wallet/캐시/스킬 등록은 보존한다.

검증: 전체 tests/ruff/mypy, Foundation runtime 계약, Foundation wheel 소비 6조합,
새 디렉터리에서 checkout 설치 및 서비스 기동, README 상대 링크, git 업로드 secret 제외.
