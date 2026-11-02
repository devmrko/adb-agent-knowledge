# 기억 작성 기준 / Memory writing guide

MCP 초기 연결 지침과 memory_save 설명, 공통 스킬에 적용합니다. 저장 형식이나 Oracle SDK 의미는 변경하지 않으며 기존 데이터도 자동 수정하지 않습니다.

## Readable memory writing

Apply this guide to knowledge_save/knowledge_revise, memory_save, index titles and relationship reasons.
- Write in the user's language. Titles must stand alone: name the subject and the action, decision or observed result. Avoid noun piles such as "근거 현재성"; do not truncate titles manually.
- BAD: "원문 버전 변경 시 근거 현재성 확인".
  GOOD, only if actually tested: "[검증 기록] 원문을 수정하자 연결 근거가 ‘재검토 필요’로 표시됐다".
  A policy is different: "원문이 바뀌면 이전 근거를 남기고 다시 확인한다".
- Start the body with one plain-language summary. Then state context, what was done or decided, observed result, date, source and verification limits. Include only known details; unknown actor/environment/date stays unknown.
- Distinguish user-confirmed policy, agent-observed result, hypothesis and demo data. Do not turn one successful test into a general guarantee. Identify the actual author/observer in prose without inventing a human identity or attributing agent text to the SDK.
- Save test/demo records only when useful and authorized. Prefix titles with [검증 기록] or [데모] and use the confirmed test/project scope; do not mix fictional HR/business rules into real policy. No automatic scope migration.
- Explain technical status codes after their plain-language meaning, e.g. "다시 확인해야 함 (REVIEW_REQUIRED)". A valid SDK memory means current/usable, not proven true.
- Relationship reasons must say which observation supports or conflicts with which claim and within what limits. Shared keywords are not evidence. Preserve SDK relation names, direction and lifecycle semantics.
- Before writing, read the title and first sentence as a reader who has not seen this conversation. If the subject, action or result is unclear, rewrite. Existing records require the supported correction/version workflow; this guide does not authorize silent rewrites.

These are calling-agent instructions, not automatic server rewriting or a semantic quality guarantee.
