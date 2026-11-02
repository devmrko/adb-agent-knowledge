# 대화형 지식 수집 / Guided knowledge capture

기존 MCP에 질문·답변을 통한 수집을 추가합니다. 새 테이블이나 별도 LLM은 필요하지 않습니다. vk0011까지 적용된 기존 검토(vk_g_review)와 작업 이력(vk_g_operation)을 사용합니다. 관계 기능 설정 WORKFLOW_RDF_ENABLED=true가 필요합니다. 웹의 ‘확인할 내용’ 탭에서 질문·답변·미정 상태를 조회할 수 있습니다. 데이터 저장·수정·답변 반영은 MCP로 진행하며 웹은 조회 전용입니다. 이 기능은 자동 온톨로지 생성기가 아닙니다.

## Codex / Claude 흐름

1. 원문을 저장하고 READY를 확인합니다. 기존 지식·개체를 검색하고 정확한 원문을 읽습니다.
2. `knowledge_capture_get(knowledge_id)`로 검토 버전과 이전 질문을 확인합니다.
3. 중요한 모호함이 있으면 `knowledge_capture_draft`에 원문 revision_id, 현재 expected_version, 요약, 추론(선택), 질문 1~3개를 제출합니다. 질문마다 key/question/reason/quote/options를 지정합니다. quote는 해당 원문의 정확한 인용이어야 합니다.
4. 에이전트가 사용자에게 질문합니다. 예: “직접 게시하는 것은 필수 승인 절차인가요, 현재 담당 방식인가요?”
5. 실제 답변만 `knowledge_capture_answer`로 기록합니다. disposition은 answered/deferred/not_applicable이며, text에는 답변 또는 보류·해당 없음의 이유를 넣습니다. 서버는 실제 인간이 답했는지 증명하지 않으며 인증된 제출자를 기록합니다.
6. 모든 답변 후에도 상태는 NEEDS_RECONCILIATION입니다. 자동으로 사실이나 관계를 게시하지 않습니다. 사용자 답변을 근거로 쓸 경우, 기존 save/revise로 출처를 명시한 지식에 보존하고 READY를 확인한 뒤 해당 원문을 인용해 기존 graph 도구로 반영합니다. 원래 문서에 없던 답변을 그 문서의 인용으로 꾸미지 않습니다.
7. 검토 결과를 반영한 뒤 기존 `knowledge_graph_review`로 완료를 기록합니다. 완료는 에이전트의 검토 확인이며 서버가 의미적 정확성을 보장하는 것은 아닙니다. NONE/RELATIONS는 해당 원문 버전에 연결된 관계 기준입니다. 답변을 별도 지식에 저장했다면 별도의 원문 검토에 해당할 수 있습니다.

명확한 사실은 질문과 별개로 기존 도구로 저장할 수 있습니다. 추론·질문·답변 스냅샷은 벡터 검색이나 게시된 RDF 사실에 자동 포함되지 않습니다. 답변이 없으면 나머지를 처리하고 해당 검토는 열어 둡니다. 질문을 덮어쓰려면 기존 라운드를 먼저 처리 완료해야 합니다. 정정 답변도 새 이력으로 남고 검토를 다시 엽니다.

## 재개·원문 변경

`knowledge_graph_reviews`에서 미완료 원문을 찾고 capture_get으로 이어갑니다. 각 쓰기는 최신 review.version을 요구합니다. 충돌/타임아웃 시 GET으로 확인한 뒤 판단하며 맹목적으로 재시도하지 않습니다. 원문이 바뀌면 이전 질문에 쓸 수 없습니다. capture_get의 revision_id로 과거 답변을 읽고 새 원문과 대조해 재질문/재검토합니다. 과거 질문의 답을 자동 승계하지 않습니다. 보류 질문은 미해결 상태이고 검토 완료를 막습니다.

이력은 기존 knowledge_graph_operation_history와 변경 이력 API에서 확인합니다. 새로운 마이그레이션은 없으며 기존 vk0011 트리거가 변경을 기록합니다. API/worker/MCP 코드를 업데이트하고 MCP 클라이언트를 다시 연결해야 새 도구가 보입니다. 운영 서버 반영은 별도 배포 작업입니다.

## English

This additive agent-led workflow reuses source review rows and append-only operation snapshots; it creates no new tables. It requires graph features and existing migrations through vk0011. The agent reads sources and existing knowledge, submits up to three source-quoted questions, asks the user, and records real answers. Kev may advise routing but never establishes truth or bypasses ownership/version checks.

Tools: `knowledge_capture_get`, `knowledge_capture_draft`, `knowledge_capture_answer`. Answers can be answered, deferred or not_applicable. Deferred questions stay open. Answers remain user assertions, hypotheses remain unverified drafts, and neither is automatically published into vector/RDF fact retrieval. Persist clarification through existing save/revise first if it is to become graph evidence; cite that exact new source. Complete the existing review only after reconciliation. Replacing a question round requires completion of the previous round.

Every mutation requires the current review version and active source revision. Old/retired source writes fail. Historical dialogs remain readable by their owner. Session restart does not lose questions. On conflicts or uncertain outcomes, reread before retrying. The web shows questions and answers read-only; mutations go through MCP. This does not include a web question editor, dynamic domain registry, automated ontology induction, or an unattended agent. No new generation-model installation is required. Live Oracle validation must be reported separately from SQLite tests.


## Public HR example / 공개 HR 예제

`./.venv/bin/python -m scripts.demo_hr_capture` runs a small agent-authored Korean excerpt summary of the [USDA APHIS onboarding guide](https://www.aphis.usda.gov/careers/new-employee/supervisor) against an isolated SQLite database under `.run/hr-onboarding-demo`. It uses the real local CPU embedding model (downloads weights if not cached), opens no listening server, and does not use production Oracle. Each run creates a distinct test item. Optionally pass `--answers-file` with a private JSON mapping of question keys (`adoption`, `ownership`) to `text` and `disposition` (`answered`, `deferred`, `not_applicable`). Never put real user answers in version control.

The extraction and questions are authored examples, not an automatic extraction-quality benchmark. The public source is reference material, never automatically an organization's approved policy. A deferred answer remains unresolved. A JSON report is written to the output directory. The real-embedding run on 2026-11-02 passed source indexing, persisted clarification, unresolved completion guard, two evidenced stage relationships and Korean query retrieval. It did not exercise Kev, native Oracle RDF, or production MCP. See the script for the minimal source summary and provenance.


## 운영 반영 확인 / Production verification — 2026-11-02

운영에 기존 vk0010·vk0011 마이그레이션을 적용하고 API·워커를 재시작했습니다. 새 SSH stdio MCP 세션에서 53개 도구와 HR 초안 1건의 정확한 원문·질문·관계 조회를 확인했습니다. 관계 2개는 oracle_rdf 저장 및 oracle_property_graph 탐색으로 반환됐습니다. 실제 HTTPS 노트 화면에서 ‘HR 테스트 초안’ 카테고리와 ‘확인할 내용’ 탭의 답변·미정 상태를 확인했습니다. 브라우저는 조회 전용이며 입력·변경은 MCP에서 처리합니다.

The initial HR seed was submitted through HTTPS before the user clarified MCP-only data handling. It was not duplicated. Subsequent verification used a fresh stdio MCP connection. The source remains a test draft; ownership/record location is unresolved, not an approved company policy. Existing long-lived MCP clients must reconnect to discover the three new capture tools.

## Semantic relationship gate (agent mode)

Before any graph assert/revise, read the exact source and check this frame:
1. Entities: identify stable business objects and roles; reuse confirmed identities. A document audience is not the eligibility boundary of a business object. Separate the benefit program, enrollment task, applicant role and application conditions.
2. Claim: express one precise subject–predicate–object proposition. A person responsible for meeting an enrollment deadline is not responsible for the entire benefits program. Prefer a specific task object over a vague umbrella object.
3. Applicability: preserve source-stated audience, appointment type, exceptions, preconditions and business time in condition/temporal fields. Do not replace these with a generic demo disclaimer. Read section headings and surrounding sentences, not only a matching quote.
4. Evidence: confirm the quote entails this particular direction, predicate and object. Quote matching, Kev scores and a plausible graph do not establish semantic truth. Preserve all still-valid evidence when revising.
5. Bounds: distinguish facts, hypotheses and unknowns. A new-hire guide does not establish that only new hires receive benefits, nor that all employees are eligible. Missing edges mean unknown, not false. Never fill missing facts with common sense presented as source evidence.
6. Clarify: look up existing knowledge first. If ambiguity changes the meaning, use knowledge_capture_get/draft with at most three source-grounded questions; publish independently clear facts only. Record only actual user answers, preserve answers as source before using them as graph evidence. Silence is not confirmation.
7. Validate: read the stored relation back as a sentence, with its conditions. Check that a reader without the source cannot reasonably infer an unsupported restriction, generalization or responsibility. Correct through history + expected_version_id; mark a review complete only when intended checks are finished and questions resolved.

Example: source tells new hires to meet their own benefits election deadlines.
BAD: New hire → responsible_for → Benefits (ambiguous program ownership).
GOOD: USDA new hire → responsible_for → Meeting own benefits election deadlines.
Condition: advice to new hires; eligibility varies by benefit; does not establish eligibility or exclusion of existing employees. Do not invent an all-employees eligibility edge.

This is agent guidance, not an automatic semantic validator. The server enforces structure, versions and source quotations; the calling agent remains responsible for meaning. Retain unresolved cases instead of forcing a populated graph.
