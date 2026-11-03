# 답변 전에 기억 MCP를 호출하는 훅

에이전트가 MCP 호출을 잊어버리는 것을 줄이기 위한 UserPromptSubmit **동기식 명령 훅**입니다.
지침 문구만 추가하는 것이 아니라 스크립트가 실제 MCP를 호출합니다. 앱 서버에 설치하는 기능이 아니라
Codex·Claude가 실행되는 머신에 설치합니다. 기존 22개 도구 설정은 변경하지 않습니다.

## 실행 흐름

요청 → 훅 → knowledge_decide(Kev) → lookup/agent_review이면 knowledge_recall → 원문 최대 2개 확인 →
결과를 모델 컨텍스트에 주입 → 답변·작업.

Kev skip도 실제 MCP 판단 호출이 끝난 결과입니다. 명시적인 과거 참조는 skip보다 우선합니다.
조회 결과가 없다는 것과 조회 실패를 구분하며, MCP 실패·내부 시간초과에는 요청을 차단합니다.
기억을 읽었다는 사실은 모델이 그 내용을 정확하게 활용했다는 보장이 아닙니다.
이 훅은 저장을 수행하지 않습니다. 확정된 변경 기록은 기존 저장 도구/스킬을 사용합니다.

## 준비

macOS/Linux, Python 3.12+, 설치된 mcp 의존성, 정상 실행되는 stdio MCP 연결이 필요합니다.
현재 Windows용 프로세스 정리는 지원하지 않습니다.
Codex CLI 0.165.0 / Claude Code 2.1.303 환경에서 점검했습니다.
Claude의 onFailure:block 옵션은 2.1.295 이상이 필요합니다.

```sh
cp config/prompt-hook.example.json /원하는/위치/prompt-hook.json
```

JSON의 mcp_command는 실제 MCP 실행 명령 배열로 수정합니다. 기존 원격 SSH launcher도 지정할 수 있습니다.
scope_roots는 **확인된 프로젝트 폴더 → 실제 저장 scope**를 지정합니다.
하위 폴더는 가장 구체적인 등록 경로를 사용하고, 미등록 폴더에서는 global만 조회합니다.
폴더 이름에서 프로젝트 ID를 추측하지 않습니다. 다른 프로젝트에도 쓰려면 명시적으로 매핑을 추가하세요.
토큰·Wallet·비밀번호는 이 JSON에 넣지 않습니다. 기존 MCP 연결의 인증 설정을 재사용합니다.

## 설치 및 활성화

저장소 루트에서 실행합니다.

```sh
./.venv/bin/python scripts/install_memory_hook.py codex --config /절대/경로/prompt-hook.json
./.venv/bin/python scripts/install_memory_hook.py claude --config /절대/경로/prompt-hook.json
```

설치 도구는 ~/.codex/hooks.json 또는 ~/.claude/settings.json에 새 UserPromptSubmit 훅만 추가합니다.
기존 Orca/다른 훅은 유지하며, 수정 전 파일을 옆에 .memory-hook-시각.bak 이름으로 백업합니다.
같은 훅을 재설치하면 중복 생성하지 않습니다.

**Codex는 /hooks에서 새 memory_prompt_hook.py 명령을 검토하고 신뢰해야 실행됩니다.**
설치 도구는 trust hash를 쓰거나 신뢰 검사를 우회하지 않습니다.
신뢰 전에는 설치됐어도 훅이 실행되지 않으므로 강제 조회가 활성화됐다고 판단하면 안 됩니다.
Claude는 새 세션으로 실행해 실제 요청 이벤트를 확인합니다. 이미 실행 중인 앱은 재시작이 필요할 수 있습니다.

## 확인

```sh
printf '%s' '{"hook_event_name":"UserPromptSubmit","prompt":"이전 배포 결정 찾아줘","cwd":"/절대/프로젝트/경로"}' |
  ./.venv/bin/python scripts/memory_prompt_hook.py --config /절대/경로/prompt-hook.json
```

성공 시 hookSpecificOutput.additionalContext에 Memory check completed와 조회 근거가 나옵니다.
실패 시 decision:block이 반환됩니다. 위 명령은 **스크립트 테스트**이며 앱 활성화 증명은 아닙니다.
실제 Codex·Claude에 이전 기록 질문을 제출하고 다음도 확인하세요.

- ~/.local/state/adb-agent-knowledge/prompt-hook.jsonl에 새 COMPLETE 기록이 생기는가.
- 호출 도구에 knowledge_decide, 필요 시 knowledge_recall/knowledge_get_content가 있는가.
- 실제 답변 컨텍스트에 해당 check_id와 근거가 전달되는가.
- MCP가 실패할 때 답변을 진행하지 않고 차단하는가.

감사 파일에는 실행 ID·시간·상태·도구명만 남깁니다. 프롬프트·본문·검색 결과를 로컬 기억 사본으로 저장하지 않습니다.
필요하면 config의 audit_dir를 지정할 수 있습니다.

## 데이터·실패 처리

현재 요청 최대 4000자만 사용하며 transcript_path나 대화 전체, 파일 내용은 읽지 않습니다.
명백한 비밀정보 패턴이 있으면 원문 대신 고정 문구로 민감 입력 표시를 전달하고 본문 조회를 생략합니다.
패턴 검사는 완전한 비밀정보 탐지기가 아닙니다. 자동 전송을 원치 않는 환경에서는 설치하지 않거나 훅을 제거하세요.
검색 결과는 신뢰할 수 없는 참고 자료로 표시하며, 지시·권한으로 취급하지 않도록 안내합니다.
정확한 원문은 최대 2개, 각 1600자만 주입합니다. 나머지는 ID/다음 offset을 통해 에이전트가 확인해야 합니다.

내부 기본 제한은 35초(설정 범위 1~45초), 호스트 훅 제한은 55초입니다.
스크립트가 처리한 오류는 차단 JSON, 실행 실패는 shell의 exit 2로 처리합니다.
Claude에는 onFailure:block도 설정합니다. 다만 훅 자체가 꺼짐·미신뢰·미지원이면 강제할 수 없습니다.
Codex의 호스트 자체 시간초과·프로세스 강제 종료까지 이 스크립트가 완전히 제어한다고 주장하지 않습니다.
실패를 숨기는 자동 우회는 없으며, 복구 전 사용자가 명시적으로 훅을 해제할 수 있습니다.

## 제거

```sh
./.venv/bin/python scripts/install_memory_hook.py codex --config /절대/경로/prompt-hook.json --remove
./.venv/bin/python scripts/install_memory_hook.py claude --config /절대/경로/prompt-hook.json --remove
```

이 훅만 제거하며 다른 훅/기억 데이터는 그대로 둡니다.

공식 스펙: [Codex Hooks](https://learn.chatgpt.com/docs/hooks),
[Claude Hooks](https://code.claude.com/docs/en/hooks).

## 2026-11-03 실측 상태

- 전체 283개 테스트 통과. 스크립트 직접 실행에서 원격 MCP 판단·기억 조회·원문 확인 성공, 약 4.3초.
- Claude Code 실제 UserPromptSubmit에서 COMPLETE 감사 기록과 4개 읽기 호출을 확인했다.
  별도 Claude 실행은 만료 오류로 끝나 답변에 컨텍스트가 반영되는 단계까지는 확인하지 못했다.
- Codex 실제 시험 응답은 HOOK_MISSING이었다. 새 훅의 trusted_hash가 없음을 확인했다.
  사용자 /hooks 신뢰 승인 후 실제 요청 재검증이 필요하다. 설치만으로 강제 적용 완료가 아니다.
- 새 설정은 기존 Orca 훅을 보존했다. 기록 자동 저장이나 모든 앱 UI에서의 동작은 이 검증 범위에 없다.
