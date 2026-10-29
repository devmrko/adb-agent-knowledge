# 모델 구성: Kev · 임베딩 · 관계 추출

> v2 기본은 agent 추출: Codex·Claude가 관계를 추출하고 서비스가 검증·저장합니다.
> 아래 별도 생성 모델·자동 추출 워커 설명은 `GRAPH_EXTRACTION_MODE=service`에 해당합니다.
> Kev·임베딩·검색은 유지합니다. [v2 아키텍처](v2-agent-extraction.md).


세 모델의 역할은 서로 다르다. 자동 관계 추출을 쓰려면 MCP 서비스가 호출할 별도 LLM이 필요하다.
서비스 내부 워커가 공통 인터페이스를 통해 모델을 호출한다. Codex·Claude의 모델을 재사용하거나
DB 내부에서 실행하지 않는다. [LLM 호출 구조](llm-providers.md)를 참고한다.

## Kev — 의사결정

기본 실행 모델 `jaredpalmer/kev-4b`는 Qwen3.5-4B-Base 기반 LoRA와 판단 헤드를 사용한다.
문장을 생성하기보다 선택지에 점수를 반환한다. 이 앱은 `/v1/systemone`과 `noul` 질문 유형을
사용해 저장·조회 필요성, 직접 검색·인덱스 탐색·관계 조회 경로를 판단한다.
공식 모델 카드의 언어는 English이다. 한국어 지시문을 사용한다고 한국어 판단 품질이 보장되는
것은 아니므로 실제 요청으로 검증한다. [모델 카드](https://huggingface.co/jaredpalmer/kev-4b)

```sh
./scripts/setup_kev.sh
./scripts/run_knowledge.sh --kev
```

설치 도구는 Kev 소스 커밋을 고정해 별도 Python 3.13 환경을 만든다. 모델은 첫 실행에 별도
다운로드한다. `KEV_REPO_DIR`은 checkout 위치, `KEV_RUN`은 로컬 모델 선택,
`KEV_URL`은 서버 주소(기본 http://127.0.0.1:8009), `KEV_MODEL=kev-latest`는 API 요청 별칭이다.
현재 코드가 모델 가중치까지 자동으로 고정한 오프라인 배포본을 만드는 것은 아니다.

조회 기준값은 기본 0.2, 저장은 0.7 이상이며 중간 구간은 에이전트 검토로 돌린다.
`KEV_*_THRESHOLD`는 잠정 설정이며 정확도의 보장이 아니다. 짧은 요청·맥락만 보내고 비밀정보나
대화 전체를 보내지 않는다. 장애·불확실성은 `agent_review`; 명시적 요청·저장 금지가 우선한다.
Kev는 기본 판단 계층이며 장애 시 에이전트 판단으로 진행할 수 있으나 정상 구동과 동일하지 않다.

원격 Kev는 `KEV_ALLOW_REMOTE=true`, HTTPS `KEV_URL`, 필요 시 `KEV_API_KEY`를 설정한다.
원격 사용 시 `--kev`로 로컬 프로세스를 시작하지 않는다. [설정 예제](portable-setup.md)

## 한국어 임베딩 — 벡터 저장·검색

기본 모델 `dragonkue/snowflake-arctic-embed-l-v2.0-ko`는 Snowflake 모델을 한국어 데이터로
추가 학습한 Sentence Transformer이다. 모델 카드 기준 한국어·영어, 1024차원, 코사인 유사도를
사용한다. [모델 카드](https://huggingface.co/dragonkue/snowflake-arctic-embed-l-v2.0-ko)

`.env.example`의 모델 revision을 고정해 최초 저장/검색 시 다운로드한다. 기본 캐시는
`.cache/huggingface`, 기본 장치는 CPU다. 별도 임베딩 서버 없이 API/worker 프로세스에서
모델을 로드하므로 여러 프로세스의 메모리 사용도 고려한다. `mps` 또는 `cuda`를 선택하려면
해당 PyTorch·하드웨어 호환성을 확인한다. 전체 모델 동시 실행의 최소 메모리를 보장하지 않는다.

앱의 기본 청크는 384토큰, 겹침 48토큰이다. 질의에는 모델의 query prompt를 적용한다.
모델 카드의 최대 문맥 길이와 앱에서 실제 사용하는 청크 크기는 서로 다르다.

원격 OpenAI 호환 `/embeddings`는 `EMBEDDING_PROVIDER=openai`로 선택한다. 이때 청크는
문자 기반이므로 같은 모델명이어도 로컬 프로필과 다를 수 있다. DB는 현재 1024차원이다.
모델·revision·차원·전처리가 다른 벡터를 섞어 비교하지 않는다. 프로필 불일치는 오류를 반환하며
자동 재임베딩·무중단 전환은 미구현이다. 기존 설정을 유지하거나 별도 스키마에서 검증한다.

## 관계 추출용 생성 모델

Ollama/Gemma 또는 OpenRouter 등 호환 API를 선택한다. Kev나 임베딩 모델을 대체하지 않는다.
로컬 예제 태그는 `adb-agent-knowledge-gemma4:e2b`이며 기반 모델은 `config/Gemma4.Modelfile`에
지정돼 있다. Ollama는 별도 앱/서비스로 실행해야 한다. [전체 설치](local-full-setup.md)

리랭커는 추가 선택 모델이며 기본 비활성이다. [설정과 평가](search-reranking.md)
각 모델·런타임의 라이선스는 프로젝트 MIT와 별개다. [외부 구성 요소](../../THIRD_PARTY.md)
