# 검색 평가 실행

API와 워커를 실행하고 지식이 READY인지 확인한다. `.env`의 기존 API 토큰을 사용한다.
DB에 직접 연결하지 않으며 문서 저장/수정/폐기 작업을 하지 않는다.

```sh
.venv/bin/python -m scripts.evaluate_knowledge .run/search-eval/cases.jsonl --repeats 3
# 임계값 조정은 dev만 보고 수행하고 test는 최종 비교 때 사용
.venv/bin/python -m scripts.evaluate_knowledge .run/search-eval/cases.jsonl --split dev
```

JSONL의 각 줄은 다음 구조이다. 아래 UUID를 실제 문서/현재 revision ID로 바꾼다.

```json
{"id":"q001","search":{"query":"지식 저장 여부는 어떤 모델이 판단하나요?","scopes":["global","project:my-project"]},"expected":[{"knowledge_id":"00000000-0000-0000-0000-000000000001","revision_id":"00000000-0000-0000-0000-000000000002"}],"forbidden":[],"split":"dev","origin":"agent-authored; source inspected; 2026-10-15"}
```

- 원문을 읽고 정답 문서들을 라벨링한다. 같은 문서의 패러프레이즈는 같은 split에 둔다.
- 정답이 없는 질문은 `expected: []`. 다른 프로젝트 필터로 조회하는 음성 사례도 포함한다.
- 폐기 문서/이전 버전은 `forbidden`에 지정할 수 있다. 원문 ID와 revision 쌍을 정확히 넣는다.
  평가를 위해 운영 기억을 폐기하거나 수정하지 않는다. 해당 사례가 없다면 미검증으로 표시한다.
- 실제 사용자 질문과 에이전트가 만든 합성 질문을 origin에 구분한다. 미검토 라벨을 확정 정답으로 취급하지 않는다.
- `search.min_similarity`를 명시하면 해당 기준을 평가한다. 기본값은 서버 설정이다.
- 결과에는 본문/질문/토큰을 저장하지 않고 사례 ID, 결과 문서/버전 ID와 지표를 기록한다.
  개인 데이터 세트와 보고서는 `.run/search-eval/`에만 보관하며 Git에 올리지 않는다.

## 지표 해석

Recall@5/20은 정답 문서 중 반환된 비율이다. Hit@5는 하나 이상 찾은 질문의 비율이다.
MRR@5는 첫 정답의 역순위이며 nDCG@5는 이진 관련성 기준이다. 무응답 질문은 이 지표의
분모에서 제외하고 no_answer_accuracy/false_positive_rate로 따로 보고한다.
forbidden_hit은 상위 20개에 금지 문서/버전이 하나라도 포함된 사례 비율이다.
금지 라벨이 있는 사례만 분모에 포함하며 없으면 지표를 생략한다. 이 수치를 보안 보장으로 해석하지 않는다.

Recall@20은 **현재 유사도 필터 이후 API 결과**로, 원시 1차 검색 후보 recall이 아니다.
지연은 순차 HTTP 요청 왕복이며 임베딩+원격 DB+직렬화를 포함하고 Kev/MCP 비용은 제외한다.
워밍업 1회를 기본 제외하며 첫 워밍업 지연을 별도로 기록한다. warmup=0이면 냉시작이 통계에
포함될 수 있다. 반복 결과는 질문별 평균으로 품질을 계산하며 각 반복을 새 평가 사례로 세지 않는다.
실패한 요청은 빈 결과로 점수화하지 않고 실행 실패로 처리한다. 실패 시 이전 보고서는 유지되므로
반드시 종료 코드와 created_at/dataset_sha256을 확인한다. 비교 실행은 --output으로 파일을 구분한다.

초기 로컬 세트는 6문서 중 확인된 내용으로 작성한 30개 합성 질의이며 실제 사용자 로그가 아니다.
작은 corpus에서는 Recall@5가 쉽게 높아지므로 리랭커 도입 효과의 증거로 사용하지 않는다.
실제 질의 30~100개, 다양한 길이의 문서와 혼동 후보를 확보한 뒤 dev에서 조정하고 test에서 비교한다.
