# Python Foundation · 내부 의존 패키지

Vector Knowledge가 사용하는 공통 인증·DB·웹 계층이다. 서비스 사용자는 이 디렉터리를 직접 실행할 필요가 없다.
루트 `./scripts/setup.sh`가 uv workspace를 통해 함께 설치한다.

- `src/python_foundation/`: 공통 라이브러리. import 이름과 wheel 이름은 유지한다.
- `example_app/`, `alembic/`: Foundation 자체 검증용 Project 예제. 지식 저장소 DB와 별개이다.
- `tests/`, `scripts/`: Foundation 계약 검증. 루트 테스트 명령에 포함된다.
- `docs/`: 기반 템플릿 설계와 사용 자료.

저장소 루트에서:

```sh
./uvw build --package devmrko-python-foundation
./uvw run --no-sync python packages/python-foundation/scripts/verify_wheel.py --uv .tools/uv/bin/uv
./uvw run --no-sync python packages/python-foundation/scripts/smoke_runtime.py
```

[서비스 README](../../README.md) · [기반 설계](docs/design/foundation.md) · [원본 프로젝트](https://github.com/devmrko/python-foundation)
