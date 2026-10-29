"""Check local Gemma JSON extraction with synthetic Korean text; never writes knowledge."""

from knowledge_app.graph_auto_contracts import AutoGraphSettings
from knowledge_app.graph_auto_extractor import HTTPExtractor
from knowledge_app.settings import ROOT


def main() -> None:
    config = AutoGraphSettings(_env_file=ROOT / "config/gemma-local.env")
    if config.allow_remote or config.url != "http://127.0.0.1:11434/v1" or config.api_key.get_secret_value():
        raise SystemExit("Local profile overridden by environment; refusing nonlocal/credentialed check")
    extractor = HTTPExtractor(config)
    samples = [
        (
            "Cafesto 프로젝트의 UX를 개선했다. Cafesto 프로젝트는 TypeScript Foundation 템플릿을 복사해 생성했다.",
            {"created_from"},
        ),
        ("에이전트가 save/revise를 결정한다. 실제 Oracle/MCP/브라우저에서 확인했다.", set()),
        ("Cafesto API는 Oracle Database를 사용한다.", {"uses"}),
    ]
    print("Known limitation: UX part_of recall is not guaranteed; review policy required.")
    for index, (source, expected) in enumerate(samples, 1):
        try:
            result = extractor.extract(source, [])
        except Exception as error:
            raise SystemExit(
                f"Local Gemma check {index} failed ({type(error).__name__}). Check Ollama/model/context resources; no cloud fallback."
            ) from None
        found = {r.predicate for r in result.relations}
        if found != expected or any(r.quote not in source for r in result.relations):
            raise SystemExit(
                f"Local Gemma check {index}: quality check failed; do not enable unattended extraction yet"
            )
        print(f"PASS synthetic Korean sample {index}: {len(result.relations)} relations")
    print(
        "PASS local extraction + semantic review. This small smoke test is not a corpus quality evaluation."
    )


if __name__ == "__main__":
    main()
