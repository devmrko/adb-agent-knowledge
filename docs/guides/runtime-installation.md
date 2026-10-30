# OS별 설치와 실제 모델 점검

Kev는 Jev-style 판단 모델이다. 이 프로젝트는 Kev-4B, 별도 한국어 임베딩 모델, 기본 agent 모드의
Codex/Claude를 사용한다. OS를 가리지 않는 완성형 바이너리를 배포하는 것은 아니다.

## 한 번에 설치

macOS 또는 Linux/WSL에서 Git과 python3/venv를 준비하고 저장소 루트에서 실행한다.
설치기는 프로젝트 전용 uv와 API Python 3.12, 별도 Kev Python 3.13 환경을 준비한다.
시스템 Python 패키지나 GPU 드라이버를 변경하지 않으며 기존 .env를 덮어쓰지 않는다.

```sh
./scripts/setup.sh --with-models --verify-models
```

1. OS와 Git을 확인한다. Windows 네이티브는 조기에 WSL 안내와 함께 중단한다.
2. uv.lock으로 API/MCP/임베딩 라이브러리를 설치하고 새 .env만 생성한다.
3. 고정 소스 커밋의 Kev를 .tools/kev에 별도 설치한다.
4. 설정된 임베딩 제공자로 가상 한국어 문서와 질의를 실제 임베딩하고 1024차원을 확인한다.
5. 별도 임시 포트에서 로컬 Kev를 시작하고 noul 응답을 확인한 뒤 테스트 프로세스를 종료한다.

최초 검증은 모델 가중치를 다운로드하므로 인터넷·디스크·메모리와 시간이 필요하다. 설치 검증에
개인 지식·DB 자격증명을 모델로 보내지 않는다. Kev와 임베딩은 순서대로 검사하여 모델 점검
프로세스가 동시에 메모리를 점유하지 않게 한다. 실제 API/worker 동시 운영 메모리 보장은 아니다.
가중치 캐시가 있으면 재사용하며 CPU 속도·한국어 정확도 벤치마크를 대체하지 않는다.

```sh
./scripts/setup.sh --with-models --verify-models --plan  # 변경·다운로드 없이 명령 확인
./scripts/setup.sh --with-models                      # 환경만 설치; 추론 미검증
./scripts/setup.sh                                    # API/MCP 환경만 설치
./scripts/setup.sh --verify-models                    # 설정된 임베딩·실행 중인 Kev endpoint 점검
```

원격 모델을 사용할 때는 with-models를 생략하고 .env에 두 endpoint와 필요한 키를 설정한 뒤
verify-models를 실행한다. 잘못된 endpoint·모델 로드 실패를 설치 성공으로 표시하지 않는다.
임베딩은 EMBEDDING_PROVIDER/DEVICE를 따르며 GPU로 임의 전환하지 않는다. KEV_DEVICE는
기본 auto이며 cpu/cuda/mps를 명시할 수 있다. 장치를 명시했는데 사용할 수 없으면 실패한다.

## OS와 하드웨어 범위

| 환경 | 구현 경로 | 검증·제한 |
|---|---|---|
| macOS Apple Silicon | Kev MLX, 임베딩 CPU(선택 MPS) | 이 머신의 설치·모델 점검 결과는 검증 기록 참고. 전체 동시 운영의 RAM 최소치 보장 없음 |
| Linux + NVIDIA | Kev PyTorch/CUDA, 임베딩 CPU 또는 CUDA | NVIDIA 드라이버와 호환 wheel 필요. 새 통합 설치기의 Linux 모델 실행은 아직 미검증 |
| Linux CPU/ARM 또는 Intel Mac | 가능한 PyTorch wheel과 CPU 경로 | 버전별 wheel 가용성·메모리·지연 미검증. 호환되지 않으면 원격 모델 사용 |
| Windows WSL2 | Linux 설치 경로 | GPU 전달·실제 모델 실행 미검증. Windows 네이티브 지원을 뜻하지 않음 |
| Windows 네이티브 | POSIX 셸/.venv/bin/프로세스 그룹 런처 미지원 | WSL2 Ubuntu 안에서 clone 및 실행하거나 서버의 MCP/API 사용 |
| AMD/ROCm 등 | upstream 지원 가능성과 별개 | 이 저장소의 고정 의존성·모델 조합은 미검증 |

PyTorch의 OS 지원만으로 이 저장소 전체의 지원을 주장하지 않는다. 네트워크·Oracle Wallet·
모델 캐시·GPU 드라이버도 환경별로 확인해야 한다. 원격 서버에 API/worker와 모델을 두면
에이전트 머신에는 해당 모델을 설치하지 않아도 된다.

근거: [고정 Kev 의존성](https://github.com/jaredpalmer/kev/blob/dd375f27fd61486c52204205e10a0d2e10f3b34a/pyproject.toml),
[고정 Kev 서버](https://github.com/jaredpalmer/kev/blob/dd375f27fd61486c52204205e10a0d2e10f3b34a/kev/serve.py),
[PyTorch 설치 안내](https://pytorch.org/get-started/locally/).

## DB 초기화는 저장소 코드가 수행한다

DB 서비스와 접속 계정·Wallet을 준비하고 .env에 입력한다. 아래 명령이 테이블·이력·감사
트리거를 migration으로 생성한다. 관리자 콘솔에서 앱 테이블 SQL을 별도로 실행하지 않는다.

```sh
./scripts/run_knowledge.sh --migrate --kev
```

RDF/Property Graph도 저장소의 초기화 도구를 사용한다. [Oracle 예제](oracle-graph-examples.md).
모델 설치가 DB 생성·계정 생성·권한 부여까지 의미하지는 않는다.

## 분리된 테스트 스키마에서 전체 검증

테스트 DB/계정을 별도로 준비하고 .env.example을 .run/oracle-test.env로 복사해 접속 정보를
입력한다. 파일 접근 권한을 600으로 제한하고 Git에 추가하지 않는다. ADMIN은 검증 계정으로
거절한다. 사용자명과 expected-schema가 다르면 실행하지 않는다. 테스트 계정에 필요한
테이블/트리거/View/Property Graph 및 RDF 생성 권한은 관리자가 준비한다.

```sh
./.venv/bin/python -m scripts.validate_oracle_installation \
  --env-file .run/oracle-test.env --expected-schema AK_TEST_01 --apply --graphs --models
```

이 명령은 저장소의 Alembic → RDF 준비 → Property Graph 생성 경로를 사용한다. 16개 감사
트리거·변경 전후·롤백·이력 수정 방지를 확인하고, models 옵션에서는 실제 설정 임베딩과
가상 Cafesto 문서/관계로 저장·검색·식별·검토·사용자 격리를 검사한다. HTTP 테스트 클라이언트의
합성 인증 주체를 사용하므로 운영 JWT/HTTPS 검증은 아니다. Kev는 별도 모델 점검 명령 대상이다.

apply를 생략하면 계획만 표시한다. models는 graphs를 요구하며 가상 원문과 이력이 테스트
스키마에 남는다. 감사 DML probe만 롤백한다. 기존 데이터 삭제·사용자 삭제는 하지 않는다.
