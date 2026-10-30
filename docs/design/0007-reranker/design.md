# 선택적 한국어 리랭커

> 설계 당시의 결정·계획을 보존한 기록입니다. 현재 기본값·설치·지원 범위는 [현재 매뉴얼](../../README.md)을 기준으로 확인하세요. 이 문서의 계획이나 과거 검증은 현재 구현·배포 보장이 아닙니다.

목표: 기존 RRF 검색과 동일한 corpus/질의로 재정렬의 품질과 비용을 비교한다.
기본 RERANKER_ENABLED=false로 기존 검색을 보존한다. 운영 활성화는 측정 후 결정한다.
모델은 dragonkue/bge-reranker-v2-m3-ko의 커밋을 고정하고 trust_remote_code=false로 로딩한다.
추가 dependency 없이 sentence-transformers CrossEncoder를 쓴다. 기본 cpu, mps/cuda 선택 가능.

소유자/scope/active revision 필터를 적용한 RRF 후보에서 상위 20개 문서, 문서당 최대 3개
청크를 뽑는다. DB 세션을 닫은 뒤 질의와 (제목+청크) 쌍을 로컬 모델로 점수화한다.
기존 기본 cosine 0.28 gate는 리랭커 모드에서는 적용하지 않는다. 명시적 min_similarity만
후단 추가 제약으로 적용한다. sigmoid 점수 임계값(잠정 0.5) 미만 청크를 제외하고,
문서 점수=max(청크 점수), 동점은 원래 RRF 순서. 마지막에 top_k로 제한한다.
청크 인용에는 실제 원문/위치만 반환한다. model 입력은 최대 512토큰, 긴 쌍은 절단된다.

score_type=reranker_sigmoid, rrf_score, rerank_score 및 모델/버전/입력 길이/후보 수/임계값
metadata를 반환한다. sigmoid를 확률로 해석하지 않는다. 모델 로딩/추론/잘못된 점수는
RERANKER_UNAVAILABLE로 실패하며 조용히 다른 검색으로 바꾸지 않는다. 비활성 시 모델을
로드하지 않는다. embedding profile/DB schema/기존 벡터는 바뀌지 않는다.

실서비스 8000을 유지하고 임시 포트 API로 동일 Oracle corpus를 읽기 전용 평가한다.
6문서 기준선의 한계를 명시하며 큰 corpus/장문/실제 질의로 추가 검증 전 기본 활성화하지 않는다.
