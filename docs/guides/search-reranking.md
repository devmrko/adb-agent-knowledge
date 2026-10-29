# 한국어 리랭커 사용과 비교

현재 6문서 실험에서는 cutoff 0.5가 정답을 과도하게 제외해 기본 활성화하지 않았다.
[실측 결과와 한계](../reference/knowledge-validation.md)를 먼저 확인한다.

기본 검색은 기존 벡터+키워드 RRF이다. 리랭커는 선택 기능이며 기본 비활성이다.
`./scripts/setup.sh`의 knowledge 의존성에 포함된 sentence-transformers를 사용한다.
최초 활성 검색 시 Hugging Face에서 모델을 다운로드한다. 네트워크/디스크/메모리가 필요하며
임베딩 모델 외에 별도 모델이 API 프로세스 메모리에 올라간다.

`.env` 예시:

```dotenv
RERANKER_ENABLED=true
RERANKER_MODEL=dragonkue/bge-reranker-v2-m3-ko
RERANKER_REVISION=2aca5884ecac490192af9ebd86836d9073d826cd
RERANKER_DEVICE=cpu
RERANKER_BATCH_SIZE=4
RERANKER_MAX_LENGTH=512
RERANKER_CANDIDATES=20
RERANKER_MIN_SCORE=0.5
```

Apple Silicon에서는 `mps`, A10에서는 CUDA PyTorch 환경을 갖춘 뒤 `cuda`를 선택할 수 있다.
API를 재시작해야 반영된다. 임베딩/청크/DB schema는 바뀌지 않아 재색인은 필요 없다.
워커에 리랭커를 추가로 로드하지 않는다. `RERANKER_ENABLED=false` 후 재시작하면 기존 검색이다.

## 검색 의미

소유자·scope·active revision 조건을 통과한 RRF 상위 20문서에서 문서당 최대 3청크를
가져와 제목+청크와 질의를 함께 평가한다. 기존 기본 `SEARCH_MIN_SIMILARITY` gate를
리랭커 모드에서는 건너뛰어 약한 후보도 재평가한다. 호출자가 `min_similarity`를 명시하면
리랭커 점수와 함께 적용되는 추가 제약이다. 이 경우 키워드 완전 일치로 우회하지 않는다.

sigmoid 점수가 `RERANKER_MIN_SCORE` 이상인 청크만 남긴다. 문서 점수는 남은 청크의 최댓값,
동점은 RRF 순서로 결정한다. 이후 요청 `top_k`로 제한한다. 결과의 `score_type`은
`reranker_sigmoid`, `score`와 `rerank_score`는 sigmoid 값, `rrf_score`는 1차 순위 점수다.
`reranker` metadata에 모델/커밋/장치/길이/후보 수/기준값이 포함된다.
점수는 보정된 관련성 확률이 아니다. 0.5는 검증된 추천값이 아닌 실험 시작값이다.

긴 제목+질의+청크는 합계 512토큰에서 절단될 수 있다. 장문 평가로 길이를 조정해야 한다.
최대 60쌍(20문서 × 3청크)을 계산하므로 기존 검색보다 느릴 수 있다. 후보 목록에 없는
문서를 복구할 수는 없다. 모델 장애 시 503/RERANKER_UNAVAILABLE를 반환하며 조용히
기존 점수로 대체하지 않는다. 반환 원문과 위치는 리랭커 입력용 제목 접두사를 포함하지 않는다.

## 비교 실행

기존 API와 별도로 8011번 포트에 실험 API를 실행할 수 있다. 운영 DB를 변경하지 않는다.

```sh
env API_PORT=8011 RERANKER_ENABLED=true RERANKER_DEVICE=mps ./scripts/run_knowledge_api.sh
# 다른 터미널
.venv/bin/python -m scripts.evaluate_knowledge .run/search-eval/cases.jsonl --output .run/search-eval/rrf.json
env KNOWLEDGE_API_URL=http://127.0.0.1:8011 .venv/bin/python -m scripts.evaluate_knowledge .run/search-eval/cases.jsonl --output .run/search-eval/reranker.json
```

같은 dataset_sha256/embedding profile, 모델 버전과 반복 횟수를 확인한다. 품질 향상 외에
무응답 정확도와 지연을 비교한다. 기준값 튜닝은 dev에서만 하고 test는 최종 검증에 사용한다.
이번 작은 합성 세트 결과만으로 운영 기본값을 변경하지 않는다.

참고: [한국어 모델 카드](https://huggingface.co/dragonkue/bge-reranker-v2-m3-ko).
이 모델은 질의·문서를 함께 평가하고 raw score에 sigmoid를 적용한다.

### 기준값 분리 실험

`RERANKER_MIN_SCORE=0`인 임시 API에서 평가하면 모든 후보의 점수가 기록된다.
기존 코사인 기준을 추가하지 않은 이 보고서로 dev에서만 기준값을 선택할 수 있다.

```sh
.venv/bin/python -m scripts.tune_reranker .run/search-eval/cases.jsonl .run/search-eval/reranker-ungated-20261015.json
```

사전에 정한 후보 기준값 중 dev Recall@5와 무응답 정확도의 평균이 최대인 것을 고른다.
동점은 낮은 기준값을 택한다. 선택된 값으로 test를 한 번 보고하며 `.env`는 수정하지 않는다.
현재 보고서의 top-20 점수를 오프라인 필터링하는 분석으로 지연을 재측정하지 않는다.
