# 다른 머신에 같은 지식·메모리 정책 적용하기

Git에는 공통 정책·스킬·설치 도구만 있습니다. 기존 머신의 `.env`, Wallet, 개인 메모리 본문, DB 지식 ID, 로컬 백업은 포함하지 않습니다. DB의 지식은 동일 서비스와 동일 사용자 신원으로 연결해 공유합니다. 각 머신의 파일은 원본 위치이며 자동 복사되지 않습니다.

## 1. 체크아웃과 서비스 연결

```sh
git clone https://github.com/devmrko/adb-agent-knowledge.git
cd adb-agent-knowledge
```

기존 체크아웃은 로컬 변경을 보존한 뒤 `git pull --ff-only`로 갱신합니다.

**기존 API에 접속만 할 머신**은 DB Wallet이나 별도 worker가 필요하지 않습니다.

```sh
./uvw sync --locked --python 3.12 --extra knowledge --extra mcp
```

이 체크아웃의 `.env`에 다음 값을 직접 설정합니다. 토큰은 Git이나 채팅에 넣지 않습니다.

```dotenv
KNOWLEDGE_API_URL=https://your-knowledge-api.example.com
KNOWLEDGE_API_TOKEN=your-api-token
KNOWLEDGE_MACHINE_ID=unique-stable-machine-id
KNOWLEDGE_MACHINE_LABEL=개발 노트북
```

API 서버가 다른 머신에 있다면 `127.0.0.1`은 그 서버를 가리키지 않습니다. 신뢰할 수 있는 HTTPS 주소 또는 사용자가 구성한 localhost 터널을 사용합니다. 이 절차는 서버를 인터넷에 공개하지 않습니다. 머신마다 다른 ID를 정하고 재시작·체크아웃 이동 시 유지합니다. 기존 머신의 `.env` 전체를 복사하지 않습니다.

**이 머신에서 API도 실행할 경우** [빠른 시작](quickstart.md)대로 DB/Wallet을 구성합니다. 같은 DB를 여러 worker가 처리하면 모두 같은 코드 버전으로 맞춥니다. 운영 환경에서는 같은 인증 사용자로 접속해야 같은 지식이 보입니다. 프로젝트 scope는 권한 경계가 아닙니다.

## 2. Codex와 Claude 스킬/MCP 연결

```sh
./.venv/bin/python scripts/install_agent.py codex --overwrite --register-mcp
./.venv/bin/python scripts/install_agent.py claude --overwrite --register-mcp
```

Codex 기본은 `~/.agents/skills/vector-knowledge`입니다. 현재 클라이언트가 `~/.codex/skills`를 쓰면 첫 명령에 `--destination ~/.codex/skills/vector-knowledge`를 붙입니다. 이미 Claude에 같은 이름의 MCP가 등록되어 있으면 기존 연결을 확인하여 이 체크아웃의 `scripts/run_configured_knowledge_mcp.sh`를 사용하도록 갱신합니다. 사용자 범위와 프로젝트 범위의 중복 연결은 피합니다. [설치 안내](agent-installation.md)를 참고합니다.

## 3. 글로벌·프로젝트 지침 검색과 적용

표준 Python만으로 실행됩니다. 먼저 변경 예정 목록을 확인합니다.

```sh
python3 scripts/configure_agent_memory.py --root "$HOME/devkit"
```

`--root`는 여러 번 지정할 수 있습니다. 생략하면 홈 전체를 검색합니다. 글로벌 대상은 기본 `~/.codex/AGENTS.md`, `~/.claude/CLAUDE.md`이며 테스트/별도 홈에는 `--home`을 사용합니다.

이 사용자가 선택적 자동 저장과 Claude의 별도 로컬 자동 메모리 해제를 원하는 경우:

```sh
python3 scripts/configure_agent_memory.py \
  --root "$HOME/devkit" \
  --allow-auto-save \
  --disable-claude-auto-memory \
  --apply
```

- 기본 실행은 파일을 변경하지 않습니다. `--apply`만 쓰면 자동 저장 허용이나 Claude 자동 메모리 해제를 새로 설정하지 않습니다.
- `--allow-auto-save`는 현재 사용자의 명시적 선택입니다. 생략한 정책은 별도 승인 없이 자동 저장 권한을 부여하지 않습니다. 재실행 시 원하는 옵션을 동일하게 지정합니다.
- `--disable-claude-auto-memory`는 기존 JSON 설정을 유지하면서 `autoMemoryEnabled=false`만 설정합니다. MCP를 통한 승인된 저장은 유지됩니다.
- 프로젝트의 AGENTS.md/AGENTS.override.md/CLAUDE.md/CLAUDE.local.md 및 템플릿을 찾고, 표시된 관리 블록만 추가·갱신합니다. 기존 규칙과 변경 사항을 보존합니다. 같은 옵션 재실행은 멱등입니다.
- Git 내부·의존성·캐시·시스템 폴더 및 symlink는 제외합니다. 권한 때문에 읽지 못한 폴더는 `unreadable`로 반환합니다. 검색 루트를 좁혀 외부 라이브러리 체크아웃 수정을 피할 수 있습니다.
- 관리 블록 밖의 오래된 저장/조회 지침은 자동 삭제하지 않고 `warnings`로 표시합니다. 충돌하는 정책은 원문을 읽고 통합합니다. 앱의 내장 메모리 기능을 강제로 모두 대체하는 도구는 아닙니다.
- `memory_files_for_manual_migration`에 기존 메모리 파일을 나열하지만 본문은 출력·업로드·수정하지 않습니다.

변경 전 로컬 백업과 manifest를 `~/.local/state/vector-knowledge/policy-backups/<id>/`에 저장하고 경로를 출력합니다. 백업은 복구용이며 에이전트의 메모리 검색 대상이 아닙니다. Git에 올리지 않습니다. 복원은 본인이 생성한 manifest만 사용합니다.

```sh
python3 scripts/configure_agent_memory.py --restore /path/to/manifest.json
python3 scripts/configure_agent_memory.py --restore /path/to/manifest.json --apply
```

적용 후 수정된 파일이나 손상된 백업은 자동 복원을 거부합니다. 새로 만든 지침 파일은 내용이 적용 직후와 같을 때만 제거하며 기존 파일은 원본으로 복원합니다. 관련 프로젝트의 커밋·push는 수행하지 않습니다.

## 4. 기존 메모리를 DB 참조로 전환

새 세션의 Codex 또는 Claude에 다음 작업을 요청합니다.

> configure_agent_memory.py의 memory_files_for_manual_migration과 warnings를 확인해 줘.
> 기존 프로젝트 규칙·원본 설계 문서는 유지하고, 실제 메모리만 같은 사용자/프로젝트 scope로 검색해 비교해 줘.
> 같은 사실은 원문·최신 이력을 읽고 보완하고, 별개 사실만 새로 저장해 줘.
> 과거 에이전트의 관찰은 현재 확정된 사용자 선호로 바꾸지 말고 출처와 미검증 상태를 남겨 줘.
> 저장 READY와 정확한 DB 본문 보존을 확인한 항목만 로컬 지식/인덱스 참조로 바꿔 줘.
> DB 연결 실패나 충돌 시 로컬 원문을 유지하고 미완료 항목을 알려줘.

지식 ID와 인덱스 ID는 연결한 DB에서 실제 반환된 값을 사용합니다. 이전 머신의 프로젝트 scope와 동일 프로젝트인지 확인하고, 경로 이름이 비슷하다는 이유로 합치지 않습니다. 파일 출처에는 실제 머신 ID와 경로·버전을 기록합니다. 비밀번호·Wallet·전체 대화·불필요한 개인정보·원본 비공개 문서를 자동으로 일괄 업로드하지 않습니다.

## 5. 확인

새 세션에서 `knowledge_client_info`로 머신 ID를 확인하고, 알려진 지식을 `knowledge_recall`로 조회한 뒤 정확한 revision 내용을 확인합니다. 쓰기 테스트를 위해 불필요한 샘플 지식을 만들 필요는 없습니다. API에 연결되지 않으면 저장/검색 성공을 주장하지 않습니다. 다른 머신에서 실제 적용됐다는 보장은 그 머신에서 이 절차를 실행한 뒤에만 할 수 있습니다.
