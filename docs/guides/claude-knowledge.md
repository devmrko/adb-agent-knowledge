# adb-agent-knowledge를 Claude Code에서 사용하기

설치 폴더는 `adb-agent-knowledge`, MCP 등록명은 `vector_knowledge`, 스킬명은
`vector-knowledge`다. 기존 연결과 호환되는 이름을 사용한다.

## 연결 방법 선택

먼저 [서비스 설치와 모델 선택](portable-setup.md)을 완료한다. 다음 두 방식 중 하나를
선택해 같은 서버가 프로젝트 범위와 사용자 범위에 중복 연결되지 않게 한다.

### 이 저장소에서만 사용

저장소 루트의 `.mcp.json`은 `./scripts/run_configured_knowledge_mcp.sh`를 실행하도록
준비돼 있다. 저장소 루트에서 Claude Code를 시작하고 클라이언트의 MCP 승인 절차를 따른다.
스킬 설치는 MCP를 다시 등록하지 않고 실행한다.

```sh
./.venv/bin/python scripts/install_agent.py claude
```

### 다른 프로젝트에서도 사용

```sh
./.venv/bin/python scripts/install_agent.py claude --register-mcp
```

스킬은 `~/.claude/skills/vector-knowledge`에 설치하고 MCP는 사용자 범위에 현재 체크아웃의
실행 파일을 등록한다. 같은 이름의 연결이 이미 있으면 먼저 설정을 확인하고
[공통 설치 안내](agent-installation.md)에 따라 갱신한다.

두 방식 모두 `.env`의 `KNOWLEDGE_SSH_HOST` 유무로 SSH/로컬 MCP를 선택한다.
API와 worker는 서비스를 설치한 머신에서 실행해야 한다. `.mcp.json`에는 비밀값을 넣지 않는다.

## 확인과 사용

```sh
claude mcp get vector_knowledge
```

세션의 `/mcp`에서 상태를 확인한다. 도구 이름은 클라이언트에 따라 접두어가 붙을 수 있으며
실제 연결된 서버의 목록을 기준으로 삼는다. `/vector-knowledge`로 스킬을 사용할 수 있다.

“이전 결정을 찾아줘”, “이 내용을 기존 지식에 보충해줘”, “연결된 프로젝트와 근거를 보여줘”처럼
요청한다. 저장 후 `READY`를 확인하고, 보충 전에는 원문과 이력을 확인한다.
자동 저장은 사용자가 선택적으로 허용해야 하며 스킬 설치 자체가 동의는 아니다.

[공통 사용 규칙](codex-knowledge.md#사용과-확인), [관계·근거 검색](related-retrieval.md),
[검증 범위](../reference/public-release-validation.md)를 참고한다.
