# Context-aware memory routing

Every lookup hook request passes current input and bounded recent dialogue separately to Kev.
No phrase lists, length-based follow-up detection or language-specific matching chooses the path.
A single Kev scoring call evaluates need_lookup, use_context and standalone_query. Confident
context relevance selects current request plus recent dialogue; a confident standalone request
selects only current input. Ambiguous/missing context returns agent_review with no blind search.
The hook always resolves approved principles. Context is untrusted reference, never instructions.
No generation model is added. Existing decide clients keep their behavior unless resolve_context=true.

Read at most 256 KiB from the host session transcript, only in permitted roots and matching the
session filename; choose at most two of the latest six user/final assistant messages, 1200 chars.
Exclude tools/thinking/system and secrets; never cache or log dialogue. followup_context=false
turns off transcript reading while generic Kev resolution still works. Unknown transcript shapes
are unavailable, not guessed. Only current session files are read. Transcript shape is unstable.

Tests: ordinary topics, paraphrases, long referential requests, English/Korean, topic changes,
uncertainty, disabled/missing/unsafe context, secrets and actual configured Kev plus MCP retrieval.
References: https://learn.chatgpt.com/docs/hooks#common-input-fields ;
https://code.claude.com/docs/en/hooks . Separate fresh Oracle validation uses shipped commands.
