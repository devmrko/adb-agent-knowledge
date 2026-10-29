# 로컬 모델 설정

임베딩 모델은 `dragonkue/snowflake-arctic-embed-l-v2.0-ko`, 1024차원, 고정 revision이다.
최초 저장/검색 시 모델을 다운로드하므로 인터넷과 디스크 공간이 필요하다. 캐시는 `.cache/huggingface`.
기본 CPU, A10에서는 EMBEDDING_DEVICE=cuda와 호환되는 PyTorch/NVIDIA 환경이 필요하다.
Mac MPS/CUDA 성능은 환경별로 검증한다.

Kev는 조회/저장 여부 점수를 내는 선택적 별도 모델이다. 없어도 에이전트 판단으로 돌아간다.

```sh
./scripts/setup_kev.sh             # 별도 Python 3.13 환경에 고정 커밋 설치
./scripts/run_knowledge.sh --kev    # API + worker + Kev 함께 실행
```

Kev 첫 실행은 모델을 추가 다운로드한다(수 GB, 충분한 메모리 필요). 설치한 Kev가 있으면
KEV_REPO_DIR을 해당 경로로 지정한다. KEV_URL 기본값은 http://127.0.0.1:8009.
Kev는 별도 저장소의 의존성과 라이선스를 따르며 이 저장소에 모델/코드를 복제해 배포하지 않는다.


리랭커는 기본 비활성입니다. [설정과 실험 결과](search-reranking.md)를 참고하세요.

OpenRouter 대신 로컬 Gemma 4를 쓰려면 [Oracle·Kev·Gemma 전체 설치 가이드](local-full-setup.md)를 참고하세요.
